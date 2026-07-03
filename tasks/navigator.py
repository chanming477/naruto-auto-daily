"""tasks.navigator — 轻量级 Pipeline 状态机 Runner(借鉴 MaaFramework Pipeline JSON 思路)。

设计目标:
    让业务任务能像写 JSON pipeline 一样,用 Python 表达"识别 → 动作 → next 链"。

核心抽象:
    - **Node**: 单个 pipeline 节点
        - recognition: TemplateMatch(多模板 + ROI)
        - action: Click / Swipe / Key / Noop
        - next: 节点 ID 列表(状态机跳转)
        - ``[JumpBack]xxx`` 前缀表示"失败时跳回原 next 链"
        - timeout: 超时毫秒(0=不限)
        - on_error: 识别失败时的 fallback 节点
    - **Pipeline**: 节点字典
    - **Navigator**: 状态机 runner

借鉴自 narutomobile(MaaFramework 体系)的 pipeline JSON:
    {
        "liveness_award_in_center_enter": {
            "recognition": "TemplateMatch",
            "template": "shared/check_in_daily_award.png",
            "roi": [37, 172, 130, 47],
            "next": [
                "liveness_award_box_1_done",
                "get_liveness_award_box_1"
            ],
            "post_delay": 300
        }
    }

与现有架构的关系:
    - **复用** device.adb_client.ADBClient (截图/点击/滑动/按键)
    - **复用** recognition.template_matcher.TemplateMatcher (模板匹配)
    - **复用** tasks.common_actions.CommonActions (go_home / close_popup 等通用)
    - **不重写** PageRecognizer / GameStateMachine / TaskEngine

分辨率:
    模板/ROI 默认基于 1920x1080(平板,narutomobile 默认)。
    模拟器实际分辨率不同时,Navigator 自动按比例缩放 ROI/坐标。
    推荐用户把 MuMu 模拟器调成 1920x1080(README 明确推荐),避免缩放误差。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

import cv2
import numpy as np
from loguru import logger

from recognition.template_matcher import MatchResult, TemplateMatcher


# ============================================================
# OCR 引擎(懒加载)
# ============================================================
#
# 用 rapidocr-onnxruntime: 纯 Python 包,无需装 Tesseract 二进制,
# 模型首次启动时自动下载到 ~/.rapidocr/。支持中英文。
#
# 我们只 lazy load,避免 import 期就下载/加载模型;第一次真正 OCR
# 才触发。加载失败(网络/磁盘)就回退到 NoopAction 流程,业务 task 仍能跑。


_OCR_ENGINE = None
_OCR_LOCK = None  # 留作将来并发锁


@dataclass(frozen=True)
class OCRMatch:
    """OCR 节点识别结果(对齐 MatchResult 接口)。

    Attributes:
        x: 命中文字框左上角 x。
        y: 命中文字框左上角 y。
        width: 命中文字框宽度。
        height: 命中文字框高度。
        confidence: 置信度 [0.0, 1.0]。
        text: 实际识别到的文字。
        template_name: 对应的 expected 文字(便于日志溯源)。
    """

    x: int
    y: int
    width: int
    height: int
    confidence: float
    text: str
    template_name: str

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


def _get_ocr_engine():
    """Lazy load rapidocr 引擎。失败返 None(调用方走 fallback)。"""
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
        return _OCR_ENGINE
    except Exception as exc:
        logger.bind(component="navigator").warning(
            "rapidocr init failed (fall back to template only): {}", exc,
        )
        return None

if TYPE_CHECKING:
    from device.adb_client import ADBClient

__all__ = [
    "Node",
    "Pipeline",
    "Navigator",
    "JumpBackError",
    "PipelineTimeout",
    "RecognitionError",
    "ClickAction",
    "SwipeAction",
    "KeyAction",
    "NoopAction",
    "OCRAction",
    "OCRMatch",
]


# ============================================================
# 异常
# ============================================================


class JumpBackError(Exception):
    """[JumpBack] 触发,跳回原 next 链。"""


class PipelineTimeout(Exception):
    """Pipeline 整体超时(连续 max_total_iterations 次识别失败)。"""


class RecognitionError(Exception):
    """单节点识别失败(无 next 可用)。"""


# ============================================================
# 动作:Click / Swipe / Key / Noop
# ============================================================


@dataclass(frozen=True)
class ClickAction:
    """点击匹配中心点(可选 target_offset 微调)。"""
    x_offset: int = 0
    y_offset: int = 0


@dataclass(frozen=True)
class SwipeAction:
    """滑动(用于找模板)。"""
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int = 300


@dataclass(frozen=True)
class KeyAction:
    """按 Android 键(BACK/HOME/3/4)。"""
    key: str | int  # 字符串名或 KeyCode


@dataclass(frozen=True)
class NoopAction:
    """不做动作(只识别)。"""
    pass


@dataclass(frozen=True)
class OCRAction:
    """OCR 节点动作。

    用于 narutomobile JSON 里 ``"recognition": "OCR"`` 等价场景。
    OCR 引擎(rapidocr)懒加载;识别 ``node.ocr_expected`` 中的任一文字,
    命中后 ``action: Click`` 命中区域中心,未命中则视为识别失败。

    字段:
        x_offset / y_offset: 点击坐标相对命中 box 中心的微调。
        case_sensitive: 是否大小写敏感(默认 False,中文不受影响)。
    """
    x_offset: int = 0
    y_offset: int = 0
    case_sensitive: bool = False


# ============================================================
# Node — 借鉴 MaaFramework pipeline 节点 schema
# ============================================================


@dataclass
class Node:
    """单个 pipeline 节点。

    字段语义对齐 MaaFramework Pipeline:
        name: 节点名(必须唯一)
        templates: 模板路径(支持多个,取 best match)
        roi: (x, y, w, h),None=全图
        threshold: 匹配阈值,默认 0.85
        action: 识别到后的动作(Click/Swipe/Key/Noop 或 None)
        next: 命中后跳转的 next 节点名列表
        on_error: 识别失败时跳转的节点名列表(类似 MaaFramework on_error)
        jumpback_targets: 标记为 [JumpBack] 的 next 节点 — 失败时回退到原 next 链
        post_delay: 动作后等待毫秒
        pre_delay: 动作前等待毫秒
        timeout_ms: 节点超时(>0 时多次重试)
        max_hit: 最大重试次数(默认 1)
        green_mask: 仅用绿色通道做模板匹配(用于红点/红角标遮挡或变色的图标)
        ocr_expected: OCR 期望文字列表(替代 narutomobile 的 OCR expected)
        ocr_roi: OCR 识别 ROI(可与 roi 不同,只用于裁剪 OCR 输入)
        ocr_threshold: OCR 置信度阈值(默认 0.5)
    """

    name: str
    templates: list[Path] = field(default_factory=list)
    roi: tuple[int, int, int, int] | None = None
    threshold: float = 0.85
    action: Any = None  # ClickAction / SwipeAction / KeyAction / NoopAction / OCRAction / None
    next: list[str] = field(default_factory=list)
    on_error: list[str] = field(default_factory=list)
    post_delay_ms: int = 200
    pre_delay_ms: int = 0
    max_hit: int = 1
    focus: str = ""  # 日志描述
    green_mask: bool = False  # P9-GRP: 绿色通道匹配(替换 narutomobile JSON 的 green_mask: true)
    # P9-OCR: OCR 节点配置(替代 narutomobile 的 "recognition": "OCR")
    # 优先级:有 ocr_expected 时优先走 OCR,templates 失效
    ocr_expected: list[str] = field(default_factory=list)
    ocr_roi: tuple[int, int, int, int] | None = None
    ocr_threshold: float = 0.5

    def is_jumpback(self, node_name: str) -> bool:
        """node_name 是否带 [JumpBack] 前缀。"""
        return node_name.startswith("[JumpBack]")


def strip_jumpback(node_name: str) -> str:
    """去掉 [JumpBack] 前缀。"""
    if node_name.startswith("[JumpBack]"):
        return node_name[len("[JumpBack]"):]
    return node_name


# ============================================================
# Pipeline — 节点字典 + 入口
# ============================================================


class Pipeline:
    """Pipeline 节点集合。

    用法:
        pipe = Pipeline(entry="start")
        pipe.add(Node(name="start", action=ClickAction(), next=["check_main"]))
        pipe.add(Node(name="check_main", templates=[...], action=NoopAction(), next=["sign"]))
    """

    def __init__(self, entry: str):
        self.entry = entry
        self._nodes: dict[str, Node] = {}

    def add(self, node: Node) -> None:
        if node.name in self._nodes:
            raise ValueError(f"node '{node.name}' already in pipeline")
        self._nodes[node.name] = node

    def get(self, name: str) -> Node | None:
        return self._nodes.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)


# ============================================================
# Navigator — 状态机 Runner
# ============================================================


@dataclass
class RunResult:
    """单次 Pipeline 运行结果。"""
    success: bool
    last_node: str
    total_iterations: int
    error: str = ""
    history: list[str] = field(default_factory=list)


class Navigator:
    """Pipeline 状态机 runner。

    用法:
        nav = Navigator(adb_client, project_root)
        result = nav.run(pipe, max_total_iterations=50)
    """

    def __init__(
        self,
        adb_client: "ADBClient",
        project_root: Path,
        *,
        templates_root: Path | None = None,
        default_threshold: float = 0.85,
        capture_screenshot: Callable[[], np.ndarray | None] | None = None,
        ref_width: int = 1920,
        ref_height: int = 1080,
    ):
        """初始化。

        Args:
            adb_client: ADB 句柄
            project_root: 项目根目录
            templates_root: 动作模板根目录(默认 project_root/resources/templates/actions)
            default_threshold: 匹配阈值
            capture_screenshot: 可选外部截图函数(None 时用 adb.screenshot)
            ref_width: 参考分辨率宽(模板基于此分辨率)
            ref_height: 参考分辨率高
        """
        self._adb = adb_client
        self._project_root = Path(project_root).resolve()
        self._templates_root = (templates_root or self._project_root / "resources" / "templates" / "actions").resolve()
        self._matcher = TemplateMatcher()
        self._default_threshold = default_threshold
        self._capture = capture_screenshot
        self._logger = logger.bind(component="navigator")
        # 参考分辨率(模板基于此大小)
        self._ref_width = ref_width
        self._ref_height = ref_height
        # 缩放比例: ref -> 实际屏幕(用于把点击坐标缩放回屏幕坐标)
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._offset_x = 0
        self._offset_y = 0

    def set_resolution_scale(self, src_w: int, src_h: int, dst_w: int, dst_h: int) -> None:
        """设置参考 → 实际屏幕的缩放比例。

        模板基于 src_w x src_h,实际屏幕是 dst_w x dst_h。
        P7-REAL: 屏幕会被 resize 到 src_w x src_h 后再做匹配(模板保持原大小),
        匹配结果的坐标再缩放回 dst_w x dst_h。

        如果 src == dst,scale=1.0。
        """
        if src_w == dst_w and src_h == dst_h:
            self._scale_x = 1.0
            self._scale_y = 1.0
        else:
            self._scale_x = dst_w / src_w
            self._scale_y = dst_h / src_h
        self._logger.info(
            "Navigator: ref {}x{} -> screen {}x{} (scale={:.3f} x {:.3f})",
            src_w, src_h, dst_w, dst_h, self._scale_x, self._scale_y,
        )

    # ----- 公共只读属性(P3 修复 2026-07-02)-------------------------
    # 之前 ``PipelineRunner`` 通过 ``nav._scale_x`` / ``nav._scale_y`` 访问私有
    # 属性。私有 API 重构时可能改名,会静默破坏。改用公共 @property 暴露。

    @property
    def scale_x(self) -> float:
        """参考 → 实际屏幕的 X 缩放比例(默认 1.0)。"""
        return self._scale_x

    @property
    def scale_y(self) -> float:
        """参考 → 实际屏幕的 Y 缩放比例(默认 1.0)。"""
        return self._scale_y

    @property
    def ref_width(self) -> int:
        """参考分辨率宽(模板基于此大小)。"""
        return self._ref_width

    @property
    def ref_height(self) -> int:
        """参考分辨率高(模板基于此大小)。"""
        return self._ref_height

    def set_offset(self, x: int, y: int) -> None:
        """设置 ROI 偏移(模拟器窗口不是从 0,0 开始时用)。"""
        self._offset_x = x
        self._offset_y = y

    # ----- 公开 API: 运行 pipeline -------------------------------------

    def run(
        self,
        pipeline: Pipeline,
        *,
        max_total_iterations: int = 100,
        max_idle_iterations: int = 5,
    ) -> RunResult:
        """运行 pipeline 状态机。

        Args:
            pipeline: Pipeline 实例
            max_total_iterations: 全局最大循环次数(防死循环)
            max_idle_iterations: 连续多少个节点无进展后放弃

        Returns:
            RunResult(success, last_node, total_iterations, error, history)
        """
        history: list[str] = []
        iterations = 0
        idle_count = 0
        current = pipeline.entry
        last_node = current
        try:
            while iterations < max_total_iterations:
                iterations += 1
                node = pipeline.get(current)
                if node is None:
                    self._logger.error("node '{}' not in pipeline", current)
                    return RunResult(False, last_node, iterations, f"node '{current}' not found", history)

                last_node = node.name
                history.append(node.name)

                # 1. 执行节点
                next_node, recognized = self._execute_node(node, pipeline)

                if recognized:
                    idle_count = 0
                else:
                    idle_count += 1

                if idle_count >= max_idle_iterations:
                    self._logger.error(
                        "Pipeline stuck: {} consecutive unrecognized nodes, last={}",
                        idle_count, node.name,
                    )
                    return RunResult(
                        False, last_node, iterations,
                        f"stuck after {idle_count} unrecognized nodes",
                        history,
                    )

                # 2. 决定下一个节点
                if next_node is None:
                    # 节点没指定 next(终点)
                    self._logger.success(
                        "Pipeline finished at node '{}' (no next)", node.name,
                    )
                    return RunResult(True, last_node, iterations, "", history)

                current = next_node
        except PipelineTimeout as exc:
            return RunResult(False, last_node, iterations, str(exc), history)
        except Exception as exc:
            self._logger.exception("Pipeline crashed at '{}': {}", current, exc)
            return RunResult(False, last_node, iterations, f"crash: {exc}", history)

        return RunResult(False, last_node, iterations, "max iterations exceeded", history)

    # ----- 内部: 单节点执行 -----------------------------------------

    def _execute_node(self, node: Node, pipeline: Pipeline) -> tuple[str | None, bool]:
        """执行单个节点。返回 (next_node_name, recognized)。"""
        log = self._logger.bind(node=node.name)
        if node.focus:
            log.info("[{}] {}", node.name, node.focus)

        if node.pre_delay_ms > 0:
            time.sleep(node.pre_delay_ms / 1000.0)

        # 1. 识别(如果没 templates,跳过识别直接当"识别成功"走 next)
        if not node.templates:
            # Noop 节点: 直接执行动作
            self._do_action(node)
            if node.post_delay_ms > 0:
                time.sleep(node.post_delay_ms / 1000.0)
            return self._next_or_finish(node, recognized=True), True

        # 多次识别尝试 — P1-1 增强: 跟踪所有尝试中的 best result 用于失败诊断
        best_result: MatchResult | None = None
        best_screen: np.ndarray | None = None
        for attempt in range(1, node.max_hit + 1):
            screen = self._capture_screen()
            if screen is None:
                log.warning("screenshot failed on attempt {}/{}", attempt, node.max_hit)
                if attempt < node.max_hit:
                    time.sleep(0.3)
                    continue
                return self._on_recognition_failed(node, best_result, best_screen), False

            # P7-REAL: 把屏幕 resize 到参考分辨率(1920x1080),模板保持原大小
            # 避免模板缩放后内容失真
            screen_resized = self._resize_screen_to_ref(screen)
            result = self._match_in_roi(node, screen_resized)
            if result is not None:
                # 把 result 坐标缩放回原始屏幕
                result = self._unscale_result(result, screen.shape)
                log.info(
                    "matched '{}' at ({},{}) conf={:.3f} (attempt {}/{})",
                    result.template_name, result.x, result.y, result.confidence, attempt, node.max_hit,
                )
                # 2. 执行动作
                self._do_action_with_result(node, result)
                if node.post_delay_ms > 0:
                    time.sleep(node.post_delay_ms / 1000.0)
                return self._next_or_finish(node, recognized=True), True

            log.debug("not matched on attempt {}/{}", attempt, node.max_hit)
            if attempt < node.max_hit:
                time.sleep(0.3)

        # 识别失败
        return self._on_recognition_failed(node, best_result, best_screen), False

    def _on_recognition_failed(
        self,
        node: Node,
        best_result: MatchResult | None = None,
        best_screen: np.ndarray | None = None,
    ) -> str | None:
        """识别失败的 fallback。

        P1-1 (2026-06-29): 失败日志增强
            - 报告尝试的模板数
            - 报告 best conf + best template (哪怕没达 threshold 也提示)
            - 报告 ROI 区域
            - 保存失败时的 ROI 截图到 screenshots/failures/ (P2-O2 关联)
        """
        log = self._logger.bind(node=node.name)
        template_names = [t.name for t in node.templates]
        if best_result is not None:
            log.warning(
                "recognition failed for '{}': {} template(s) tried, best={:.3f} ('{}'), roi={}",
                node.name, len(node.templates), best_result.confidence,
                best_result.template_name, node.roi,
            )
            # 保存 ROI 截图便于人工排查
            self._save_failure_screenshot(node, best_screen)
        else:
            log.warning(
                "recognition failed for '{}': {} template(s) tried, no match at all, roi={}",
                node.name, len(node.templates), node.roi,
            )
            # 即使没 best_result 也要存一张屏幕供诊断
            if best_screen is not None:
                self._save_failure_screenshot(node, best_screen)
            else:
                # 重新截一张
                screen = self._capture_screen()
                if screen is not None:
                    self._save_failure_screenshot(node, screen)
        # 优先 on_error
        if node.on_error:
            return self._strip_jumpback_log(node, node.on_error[0], kind="on_error")
        # 否则跳到第一个 next
        if node.next:
            return self._strip_jumpback_log(node, node.next[0], kind="next")
        return None  # 终点

    def _save_failure_screenshot(self, node: Node, screen: np.ndarray | None) -> None:
        """保存识别失败时的 ROI 截图到 screenshots/failures/。

        文件名: {timestamp}_{node_name}.png
        路径: 项目根 / screenshots / failures / {filename}
        """
        if screen is None:
            return
        try:
            from pathlib import Path
            import time as _time

            # 找项目根: navigator 的 project_root
            project_root = getattr(self, "_project_root", None)
            if project_root is None:
                # 退化: 用 cwd
                project_root = Path.cwd()
            else:
                project_root = Path(project_root)

            failures_dir = project_root / "screenshots" / "failures"
            failures_dir.mkdir(parents=True, exist_ok=True)

            ts = _time.strftime("%Y%m%d_%H%M%S")
            safe_node = node.name.replace("/", "_").replace("\\", "_")
            out_path = failures_dir / f"{ts}_{safe_node}.png"

            # 用 cv2.imencode + file.write 避免中文路径/特殊字符问题
            import cv2
            ok, buf = cv2.imencode(".png", screen)
            if ok:
                out_path.write_bytes(buf.tobytes())
                self._logger.bind(node=node.name).debug(
                    "saved failure screenshot: {}", out_path,
                )
        except Exception as exc:  # noqa: BLE001 - 截图保存失败不影响主流程
            self._logger.bind(node=node.name).warning(
                "failed to save failure screenshot: {}", exc,
            )

    def _matcher_match_targets(self, node: Node) -> set[str]:
        """hack: 让 on_error 始终可用(简化实现,不查 names)。"""
        return set()  # noqa - 实际 on_error 直接用名字,不查

    def _next_or_finish(self, node: Node, *, recognized: bool) -> str | None:
        """决定下一个节点:有 next 走第一个 next,没 next 返 None(终点)。"""
        if node.next:
            return self._strip_jumpback_log(node, node.next[0], kind="next")
        return None

    def _strip_jumpback_log(self, node: Node, target: str, *, kind: str) -> str:
        """如果 target 带 ``[JumpBack]`` 前缀,strip 后返回 + 打 debug 日志。

        P1 修复(2026-07-02): 之前 Navigator 直接把 ``[JumpBack]xxx`` 当字面
        节点名传给 ``Pipeline.get``,导致"节点未找到"错误;本函数把
        ``[JumpBack]xxx`` 还原为 ``xxx``。这是最简实现 — 没有实现"失败时
        回退到原 next 链"的完整 JumpBack 语义(Node.jumpback_targets 字段
        尚未定义);当前 task pipeline 也不依赖完整 JumpBack,所以最简版够用。

        Args:
            node: 当前节点(只用于日志)
            target: 跳转目标(可能带 [JumpBack] 前缀)
            kind: "next" 或 "on_error"(用于日志区分)

        Returns:
            去掉 [JumpBack] 前缀的目标名
        """
        if target.startswith("[JumpBack]"):
            stripped = strip_jumpback(target)
            self._logger.bind(node=node.name).debug(
                "JumpBack strip: {} target '{}' -> '{}'",
                kind, target, stripped,
            )
            return stripped
        return target

    def _match_in_roi(self, node: Node, screen: np.ndarray) -> MatchResult | OCRMatch | None:
        """在 ROI 内做模板匹配 或 OCR 识别。

        P7-REAL: 调用方已经 resize screen 到 ref 分辨率,所以 ROI 不用再缩放。

        优先级:
            1. 若 ``node.ocr_expected`` 非空 → 走 OCR(快速失败 fallback 到模板)
            2. 若 ``node.green_mask`` 为 True → 走绿色通道模板匹配
            3. 否则走普通模板匹配
        """
        # 1. OCR 优先
        if node.ocr_expected:
            ocr_result = self._match_ocr(node, screen)
            if ocr_result is not None:
                return ocr_result
            # OCR 未命中 → 如果也有 templates,降级到模板匹配
            if not node.templates:
                return None

        # 2/3. 模板匹配
        if not node.templates:
            return None
        if node.green_mask:
            return self._match_green_channel(node, screen)
        roi = node.roi
        if len(node.templates) == 1:
            return self._matcher.match(
                node.templates[0], screen,
                roi=roi, threshold=node.threshold,
            )
        best: MatchResult | None = None
        for tpl in node.templates:
            r = self._matcher.match(tpl, screen, roi=roi, threshold=node.threshold)
            if r is not None and (best is None or r.confidence > best.confidence):
                best = r
        return best

    def _match_ocr(self, node: Node, screen: np.ndarray) -> OCRMatch | None:
        """P9-OCR: 在 ROI 内 OCR,匹配 expected 文字。

        Args:
            node: 节点(读 ocr_expected / ocr_roi / ocr_threshold)。
            screen: BGR uint8 ndarray(已 resize 到 ref 分辨率)。

        Returns:
            OCRMatch(含中心点坐标,可直接被 OCRAction/ClickAction 用),
            或 None(引擎未就绪 / 未匹配)。
        """
        log = self._logger.bind(node=node.name)
        engine = _get_ocr_engine()
        if engine is None:
            log.warning("OCR engine not ready, skip OCR for this node")
            return None
        roi = node.ocr_roi or node.roi
        # 裁 ROI 出来给 OCR(降负 + 提速)
        if roi is not None:
            from recognition.template_matcher import _normalize_roi
            rx, ry, rw, rh = _normalize_roi(screen, roi)
            crop = screen[ry:ry + rh, rx:rx + rw]
        else:
            crop = screen
            rx, ry = 0, 0
        try:
            result, _elapsed = engine(crop)
        except Exception as exc:
            log.warning("OCR call raised: {}", exc)
            return None
        if not result:
            return None
        # rapidocr 输出: [[box, text, conf], ...]  box=[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        expected_norm = (
            node.ocr_expected if getattr(node, "_case_sensitive", False)
            else [e.lower() for e in node.ocr_expected]
        )
        best: OCRMatch | None = None
        for item in result:
            try:
                box, text, conf = item
            except Exception:
                continue
            text_norm = text if getattr(node, "_case_sensitive", False) else str(text).lower()
            # 子串包含(更宽松,允许"前往" 匹配 "前往追击晓组织")
            if not any(e in text_norm for e in expected_norm):
                continue
            if conf < node.ocr_threshold:
                continue
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            x_min, y_min = min(xs), min(ys)
            x_max, y_max = max(xs), max(ys)
            cand = OCRMatch(
                x=rx + int(x_min),
                y=ry + int(y_min),
                width=int(x_max - x_min),
                height=int(y_max - y_min),
                confidence=float(conf),
                text=str(text),
                template_name=str(text),
            )
            if best is None or cand.confidence > best.confidence:
                best = cand
        if best is not None:
            log.info(
                "OCR matched '{}' at ({},{}) conf={:.3f}",
                best.text, best.x, best.y, best.confidence,
            )
        return best

    def _match_green_channel(
        self, node: Node, screen: np.ndarray,
    ) -> MatchResult | None:
        """P9-GRP: 用绿色通道做模板匹配(用于红点遮挡的图标)。

        屏幕和模板都取 G 通道(``[..., 1]``),再 cv2.matchTemplate。
        与 TemplateMatcher.match 行为等价,但 ROI 内部已 resize 到 ref 分辨率,
        所以不需要二次缩放。
        """
        from recognition.template_matcher import MatchResult, _normalize_roi, load_template
        roi_x, roi_y, roi_w, roi_h = _normalize_roi(screen, node.roi)
        screen_g = screen[..., 1]  # G channel
        roi_view = screen_g[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
        best: MatchResult | None = None
        for tpl_path in node.templates:
            tpl_img = load_template(tpl_path)
            if tpl_img is None or tpl_img.size == 0:
                continue
            tpl_g = tpl_img[..., 1]
            th_h, th_w = tpl_g.shape[:2]
            if th_h > roi_h or th_w > roi_w:
                continue
            score = cv2.matchTemplate(roi_view, tpl_g, cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(score)
            if mv < node.threshold:
                continue
            cand = MatchResult(
                x=roi_x + int(ml[0]),
                y=roi_y + int(ml[1]),
                width=int(th_w),
                height=int(th_h),
                confidence=float(mv),
                template_name=tpl_path.name,
            )
            if best is None or cand.confidence > best.confidence:
                best = cand
        return best

    def _scale_roi(self, roi: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
        """按 self._scale_x/y 缩放 ROI 坐标。"""
        if roi is None:
            return None
        x, y, w, h = roi
        return (
            int(x * self._scale_x) + self._offset_x,
            int(y * self._scale_y) + self._offset_y,
            int(w * self._scale_x),
            int(h * self._scale_y),
        )

    def _resize_screen_to_ref(self, screen: np.ndarray) -> np.ndarray:
        """P7-REAL: 把屏幕 resize 到参考分辨率(1920x1080),让模板保持原大小匹配。

        用 INTER_LANCZOS4(最高质缩放),避免 INTER_LINEAR 在小图标上的模糊。
        如果屏幕已经是参考分辨率,直接返回(性能优化)。
        """
        h, w = screen.shape[:2]
        if w == self._ref_width and h == self._ref_height:
            return screen
        return cv2.resize(
            screen, (self._ref_width, self._ref_height),
            interpolation=cv2.INTER_LANCZOS4,
        )

    def _unscale_result(
        self, result: MatchResult, original_shape
    ) -> MatchResult:
        """P7-REAL: 把匹配结果从参考分辨率缩放回原始屏幕分辨率。

        Args:
            result: 在 resize 后屏幕上的 MatchResult
            original_shape: 原始屏幕的 shape (H, W, 3) 或 (H, W)

        Returns:
            缩放回原分辨率的 MatchResult(center 也同步缩放)
        """
        h, w = original_shape[:2]
        if w == self._ref_width and h == self._ref_height:
            return result
        scale_x = w / self._ref_width
        scale_y = h / self._ref_height
        # 不可变 dataclass, 用 replace
        from dataclasses import replace
        return replace(
            result,
            x=int(result.x * scale_x),
            y=int(result.y * scale_y),
            width=int(result.width * scale_x),
            height=int(result.height * scale_y),
        )

    def _do_action(self, node: Node) -> None:
        """执行节点动作(无 result 版本,用于 Noop 节点)。"""
        self._do_action_with_result(node, None)

    def _do_action_with_result(self, node: Node, result: MatchResult | OCRMatch | None) -> None:
        """执行节点动作,使用 result.center 作为点击坐标。

        支持 ``MatchResult``(模板匹配)和 ``OCRMatch``(OCR 识别)。
        """
        log = self._logger.bind(node=node.name)
        action = node.action
        if action is None or isinstance(action, NoopAction):
            return
        if isinstance(action, (ClickAction, OCRAction)):
            if result is None:
                log.warning(
                    "{} but no match result, skip", type(action).__name__,
                )
                return
            cx, cy = result.center
            cx += action.x_offset
            cy += action.y_offset
            log.info(
                "{} ({}, {}) [matched '{}' conf={:.3f}]",
                type(action).__name__, cx, cy,
                getattr(result, "template_name", "?"),
                result.confidence,
            )
            r = self._adb.tap(cx, cy)
            if not r.success:
                log.warning("tap failed: {}", r.message)
        elif isinstance(action, SwipeAction):
            log.info("swipe ({},{}) -> ({},{})", action.x1, action.y1, action.x2, action.y2)
            r = self._adb.swipe(
                int(action.x1 * self._scale_x) + self._offset_x,
                int(action.y1 * self._scale_y) + self._offset_y,
                int(action.x2 * self._scale_x) + self._offset_x,
                int(action.y2 * self._scale_y) + self._offset_y,
                duration_ms=action.duration_ms,
            )
            if not r.success:
                log.warning("swipe failed: {}", r.message)
        elif isinstance(action, KeyAction):
            log.info("key {}", action.key)
            r = self._adb.keyevent(action.key)
            if not r.success:
                log.warning("keyevent failed: {}", r.message)
        else:
            log.warning("unknown action type: {}", type(action).__name__)

    # ----- 截图 -------------------------------------------------------

    def _capture_screen(self) -> np.ndarray | None:
        """拿一张截图。"""
        if self._capture is not None:
            return self._capture()
        try:
            result = self._adb.screenshot()
            if result.success and isinstance(result.payload, np.ndarray):
                return result.payload
        except Exception as exc:
            self._logger.warning("screenshot failed: {}", exc)
        return None

    # ----- 工厂: 从文件路径构造模板列表 -----------------------------

    def templates(self, *names: str) -> list[Path]:
        """根据短名构造模板绝对路径。

        Args:
            *names: 相对于 templates_root 的文件路径,例如:
                - "shared/award_center_entry.png"
                - "shared/x.png"
                - "liveness/confirm_weekly_award.png"

        Returns:
            绝对路径列表
        """
        out: list[Path] = []
        for n in names:
            p = self._templates_root / n
            if not p.exists():
                # fallback: 在 state 模板目录找(home/popup/loading)
                state_path = self._project_root / "resources" / "templates" / n
                if state_path.exists():
                    p = state_path
                else:
                    self._logger.warning("template not found: {}", p)
                    continue
            out.append(p)
        return out
