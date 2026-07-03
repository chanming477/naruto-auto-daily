"""recognition.template_matcher — **[主视觉识别]** OpenCV 模板匹配封装。

职责:
    在给定截图(``numpy.ndarray``, BGR uint8)上按 ROI 区域搜索模板,
    返回最佳/全部匹配,或判断是否存在。

⚠️ 模块辨识警告(2026-06-30 工程治理):
    本模块与同级目录 ``recognition/`` 和 ``recognizer/`` 命名近似但语义不同:
        - ``recognition.template_matcher`` (本模块):**单图 → 单模板匹配**(ROI 区域,Node)
        - ``recognizer.page_recognizer``:**单图 → 多个 GameState 模板循环**(页面级)
    调用者请明确选哪个模块,不要 import 错了:
        任务/task 用 ``recognition.template_matcher``(节点级匹配)。
        状态识别/页面级用 ``recognizer.page_recognizer``(整体页面)。
    未来改名计划(Phase 10): ``recognizer/`` → ``page_detector/``。

公开 API:
    TemplateMatcher
        .match(template, screen, *, roi=None, threshold=None) -> MatchResult | None
        .match_all(template, screen, *, roi=None, threshold=None, max_results=10) -> list[MatchResult]
        .exists(template, screen, *, roi=None, threshold=None) -> bool

模板来源支持:
    - 单文件: ``Path("foo.png")``
    - 多模板目录: ``Path("foo_dir/")`` 或 ``Path("foo_dir")`` —— 目录下所有 PNG 都会被尝试,
      最终取所有模板中置信度最高者(单 best)或全部保留(多结果)。

ROI 格式: ``(x, y, w, h)`` 元组,坐标相对于 ``screen`` 原点。
    - ``None``: 全图搜索。
    - 部分越界会自动 clip 到 ``screen`` 范围。
    - 退化的 ROI(width<=0 或 height<=0)会被视为 None。

阈值:
    - 默认从 ``ConfigManager.app.template_matching.default_threshold`` 读取
      (Phase 2 默认 0.85)。
    - 调用方可单次覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence

import cv2
import numpy as np

if TYPE_CHECKING:
    from core.config_manager import ConfigManager, TemplateMatchingConfig

__all__ = ["TemplateMatcher", "MatchResult", "load_template"]


@dataclass(frozen=True)
class MatchResult:
    """单次模板匹配的位置结果。

    Attributes:
        x: 命中区域左上角 x(相对 screen 原点,非 ROI 原点)。
        y: 命中区域左上角 y。
        width: 命中区域宽度(=模板宽度)。
        height: 命中区域高度(=模板高度)。
        confidence: 归一化相关系数 [0.0, 1.0]。
        template_name: 命中的模板文件名,便于日志溯源。
    """

    x: int
    y: int
    width: int
    height: int
    confidence: float
    template_name: str

    @property
    def center(self) -> tuple[int, int]:
        """命中区域中心点坐标。"""
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": round(self.confidence, 4),
            "template_name": self.template_name,
            "center": self.center,
        }


def _normalize_roi(
    screen: np.ndarray,
    roi: Sequence[int] | None,
) -> tuple[int, int, int, int]:
    """将 ROI 规范化到 ``screen`` 范围内。

    Args:
        screen: 待搜索图像。
        roi: ``(x, y, w, h)`` 或 ``None``。

    Returns:
        ``(x, y, w, h)``,保证 ``w > 0`` 且 ``h > 0``,且位于 ``screen`` 范围内。
        退化的 ROI(width<=0 或 height<=0)或 clip 后完全越界的 ROI 会被视为 None,返回整张图。
    """
    img_h, img_w = screen.shape[:2]
    full = (0, 0, int(img_w), int(img_h))
    if roi is None:
        return full
    x, y, w, h = (int(v) for v in roi)
    if w <= 0 or h <= 0:
        return full
    x0 = max(0, min(x, img_w))
    y0 = max(0, min(y, img_h))
    x1 = max(x0, min(x + w, img_w))
    y1 = max(y0, min(y + h, img_h))
    rw, rh = x1 - x0, y1 - y0
    if rw <= 0 or rh <= 0:  # clip 后完全越界(P1-STABLE-04)
        return full
    return (x0, y0, rw, rh)


def _coerce_paths(template: Path | str | Iterable[Path | str]) -> list[Path]:
    """把单路径/目录路径/路径列表统一成 ``list[Path]``。"""
    if isinstance(template, (str, Path)):
        return [Path(template)]
    return [Path(p) for p in template]


def load_template(path: Path) -> np.ndarray | None:
    """加载单张模板图,失败返回 ``None``。

    P7-REAL: 用 ``cv2.imdecode`` 而非 ``cv2.imread``,因为某些 narutomobile
    模板(iCCP chunks 不规范)会让 headless cv2 报 can't open/read file,但
    imdecode 不受此影响。

    Args:
        path: PNG/JPG 文件路径。

    Returns:
        BGR uint8 ndarray,或 None(文件不存在 / OpenCV 读取失败)。
    """
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = f.read()
        if not data:
            return None
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            # P7-REAL fallback: cv2.imdecode 也失败时,用 PIL 读再转 BGR
            try:
                from PIL import Image
                pil = Image.open(path).convert("RGB")
                rgb = np.array(pil, dtype=np.uint8)
                img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            except Exception:
                return None
        return img
    except Exception:
        return None


def _expand_template_paths(paths: Sequence[Path]) -> list[Path]:
    """把每个 Path 展开:若是目录则收集目录下所有 PNG/JPG;若是文件则保留。"""
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and child.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    out.append(child)
        elif p.is_file():
            out.append(p)
        else:
            # P6-REAL-02: 不存在的路径 silent skip (用 DEBUG 级别 log,不影响 INFO 用户),
            # 但显式 corrupt/权限错误用 import 一致的 logger 提示
            try:
                from loguru import logger as _lg
                _lg.bind(component="template_matcher").debug(
                    "template path not found or inaccessible: {}", p,
                )
            except Exception:
                pass
            continue
    return out


# ============================================================
# Manager
# ============================================================


class TemplateMatcher:
    """基于 OpenCV ``matchTemplate`` (TM_CCOEFF_NORMED) 的模板匹配器。

    所有公共方法都对输入做防御性检查:
        - ``screen`` 为 None / 空 / 维度 < 2 → 返回 None / 空列表 / False
        - 所有模板路径都不存在或加载失败 → 同上(模板目录为空,不抛错)
        - 模板尺寸 > ROI 尺寸 → 该模板跳过,继续尝试其他模板
    """

    def __init__(self, config: "ConfigManager | TemplateMatchingConfig | None" = None) -> None:
        """初始化。

        Args:
            config: 可以传完整的 ConfigManager,也可以只传 TemplateMatchingConfig;
                None 时使用 0.85 默认阈值。
        """
        if config is None:
            self._default_threshold: float = 0.85
        elif hasattr(config, "template_matching"):
            self._default_threshold = float(
                getattr(config.template_matching, "default_threshold", 0.85)
            )
        elif hasattr(config, "default_threshold"):
            self._default_threshold = float(config.default_threshold)
        else:
            self._default_threshold = 0.85
        # P6-REAL-02: 记录「corrupt/不可读」模板,首次 warning 后不再刷屏
        self._warned_corrupt: set[str] = set()

    # ----- public --------------------------------------------------------

    def match(
        self,
        template: Path | str | Iterable[Path | str],
        screen: np.ndarray | None,
        *,
        roi: Sequence[int] | None = None,
        threshold: float | None = None,
    ) -> MatchResult | None:
        """在 ``screen`` 上搜索 ``template``,返回最佳匹配。

        Args:
            template: 单路径 / 目录路径 / 路径列表。
            screen: BGR 截图 (H, W, 3) uint8。
            roi: 可选 ROI ``(x, y, w, h)``,None 表示全图。
            threshold: 单次阈值覆盖;None 用构造时配置的默认值。

        Returns:
            最佳 ``MatchResult``,或 ``None`` 表示未匹配 / 模板为空 / 输入非法。
        """
        if not self._validate_screen(screen):
            return None
        thr = self._resolve_threshold(threshold)
        roi_xywh = _normalize_roi(screen, roi)
        roi_x, roi_y, roi_w, roi_h = roi_xywh
        roi_view = screen[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

        best: MatchResult | None = None
        for tpl_path in _expand_template_paths(_coerce_paths(template)):
            tpl_img = load_template(tpl_path)
            if tpl_img is None or tpl_img.size == 0:
                # P6-REAL-02: silent skip 时给一次 warning,后续不刷屏
                key = str(tpl_path)
                if key not in self._warned_corrupt:
                    try:
                        from loguru import logger as _lg
                        _lg.bind(component="template_matcher").warning(
                            "template skipped: cannot load or empty: {}", key,
                        )
                    except Exception:
                        pass
                    self._warned_corrupt.add(key)
                continue
            th_h, th_w = tpl_img.shape[:2]
            if th_h > roi_h or th_w > roi_w:
                # 模板比 ROI 还大,本轮跳过
                continue
            score_map = cv2.matchTemplate(roi_view, tpl_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(score_map)
            if max_val < thr:
                continue
            cand = MatchResult(
                x=roi_x + int(max_loc[0]),
                y=roi_y + int(max_loc[1]),
                width=int(th_w),
                height=int(th_h),
                confidence=float(max_val),
                template_name=tpl_path.name,
            )
            if best is None or cand.confidence > best.confidence:
                best = cand
        return best

    def match_all(
        self,
        template: Path | str | Iterable[Path | str],
        screen: np.ndarray | None,
        *,
        roi: Sequence[int] | None = None,
        threshold: float | None = None,
        max_results: int = 10,
    ) -> list[MatchResult]:
        """在 ``screen`` 上搜索 ``template``,返回所有匹配(按置信度降序)。

        Args:
            template: 同 ``match``。
            screen: 同 ``match``。
            roi: 同 ``match``。
            threshold: 同 ``match``。
            max_results: 最多返回的结果数(防爆)。

        Returns:
            ``MatchResult`` 列表,空列表表示无匹配。
        """
        if not self._validate_screen(screen):
            return []
        thr = self._resolve_threshold(threshold)
        roi_xywh = _normalize_roi(screen, roi)
        roi_x, roi_y, roi_w, roi_h = roi_xywh
        roi_view = screen[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

        results: list[MatchResult] = []
        for tpl_path in _expand_template_paths(_coerce_paths(template)):
            tpl_img = load_template(tpl_path)
            if tpl_img is None or tpl_img.size == 0:
                continue
            th_h, th_w = tpl_img.shape[:2]
            if th_h > roi_h or th_w > roi_w:
                continue
            score_map = cv2.matchTemplate(roi_view, tpl_img, cv2.TM_CCOEFF_NORMED)
            # 阈值化:对整个 score_map 一次性找所有 ≥ thr 的位置
            ys, xs = np.where(score_map >= thr)
            for x, y in zip(xs.tolist(), ys.tolist()):
                results.append(
                    MatchResult(
                        x=roi_x + int(x),
                        y=roi_y + int(y),
                        width=int(th_w),
                        height=int(th_h),
                        confidence=float(score_map[y, x]),
                        template_name=tpl_path.name,
                    )
                )

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[: max(0, int(max_results))]

    def exists(
        self,
        template: Path | str | Iterable[Path | str],
        screen: np.ndarray | None,
        *,
        roi: Sequence[int] | None = None,
        threshold: float | None = None,
    ) -> bool:
        """``match()`` 的便捷布尔包装:存在任意 ≥ 阈值的匹配则返回 True。"""
        return self.match(template, screen, roi=roi, threshold=threshold) is not None

    # ----- internals -----------------------------------------------------

    @staticmethod
    def _validate_screen(screen: np.ndarray | None) -> bool:
        """screen 是否可用于模板匹配。"""
        if screen is None:
            return False
        if not isinstance(screen, np.ndarray):
            return False
        if screen.size == 0 or screen.ndim < 2:
            return False
        if screen.shape[0] < 1 or screen.shape[1] < 1:
            return False
        return True

    def _resolve_threshold(self, override: float | None) -> float:
        """把调用方传入的 threshold 与构造时的默认值合并。"""
        if override is None:
            return self._default_threshold
        v = float(override)
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"threshold must be in [0.0, 1.0], got {v}")
        return v