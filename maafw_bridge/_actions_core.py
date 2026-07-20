"""maafw_bridge._actions_core — CustomAction 核心逻辑,Direct API 模式 + Agent 模式共用。

**为什么提取这一层**:
    方案 A (Agent 模式迁移) 要求 Python 端把 CustomAction 注册到 MFAAvalonia
    的子进程 (AgentServer),但核心逻辑 (OCR + 点击 + 截屏) 跟 Direct API
    模式**完全一样**。如果直接复制,会维护两份。

    这一层把 ``run()`` 主体抽出来,两个入口都调它:
        - ``maafw_bridge.custom_actions.NonlinearSwipeAction.run()`` (Direct API)
        - ``agent.custom.action.NonlinearSwipeAction.run()`` (Agent 模式)

**接口约定**:
    - 接受 ``context`` (任意 maa context 实例,只需 ``.tasker.controller`` 存在)
    - 接受 ``argv`` (maa custom action 回调参数,见 ``_parse_param``)
    - 返 ``bool`` (True=成功,False=失败,caller 走 [JumpBack] fallback)

**注意**:
    - **不**继承 ``CustomAction`` 或用 ``@AgentServer.custom_action`` 装饰器
    - **不**调 ``resource.register_custom_action()`` (那是 entry 的事)
    - 只暴露 3 个核心函数 + 1 个 param 解析 helper
"""

from __future__ import annotations

import json
import random
import shutil
import time
from pathlib import Path
from typing import Any

try:
    from maa.pipeline import JOCR, JRecognitionType  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    JOCR = None  # type: ignore
    JRecognitionType = None  # type: ignore
    _MAAFW_AVAILABLE = False

from loguru import logger

_LOG = logger.bind(component="maafw.actions_core")


# ============================================================
# Param 解析 — 两种模式共用
# ============================================================
def parse_custom_action_param(argv: Any) -> dict[str, Any]:
    """把 ``argv.custom_action_param`` 安全解析成 dict。

    maafw 5.10.4 在不同入口下 ``custom_action_param`` 可能是:
      - ``dict``(直接给 dict)— 罕见,某些 override path
      - ``str``(JSON 字符串)— C 回调路径(ctypes)实际行为,**主要场景**

    这里两种都兼容,失败返 ``{}`` 让 caller fallback。
    """
    raw = getattr(argv, "custom_action_param", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    # bytes → 先 decode 再 parse
    if isinstance(raw, bytes):
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return {}
    # 其他类型 — 尝试 str(raw) 兜底
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ============================================================
# NonlinearSwipe 核心
# ============================================================
def nonlinear_swipe_run(
    context: Any,
    argv: Any,
    *,
    segments: int = 5,
    noise_px: int = 5,
) -> bool:
    """NonlinearSwipe 核心逻辑 — 5 段直线 swipe + 中段 ±5px noise 模拟人手曲线。

    narutomobile 的 NonlinearSwipe 参数::
        {
          "start_x": int,
          "start_y": int,
          "end_x": int,
          "end_y": int,
          "after_swipe_delay": int (ms)
        }

    Args:
        context: maa context (Direct API 的 Context 或 Agent 的 AgentContext,
                 只需 ``.tasker.controller`` 存在)。
        argv: maa custom action 回调参数对象。
        segments: 分段数 (默认 5,narutomobile 默认)。
        noise_px: 每段加的随机 noise 像素 (默认 5)。

    Returns:
        True = swipe 成功,False = 参数解析失败或 controller 抛异常。
    """
    params = parse_custom_action_param(argv)
    try:
        sx = int(params.get("start_x", 0))
        sy = int(params.get("start_y", 0))
        ex = int(params.get("end_x", 0))
        ey = int(params.get("end_y", 0))
        delay = int(params.get("after_swipe_delay", 100))
    except (TypeError, ValueError, AttributeError) as exc:
        _LOG.warning("NonlinearSwipe param parse failed: {}", exc)
        return False

    ctrl = context.tasker.controller
    # 5 段 swipe:每段从当前 bezier 点到下一个 bezier 点
    # bezier 中点偏移 = (sy→ey 中点的 x 方向 ±noise_px)
    for i in range(1, segments + 1):
        t = i / segments
        # 当前 bezier 插值
        mid_x = sx + (ex - sx) * t
        mid_y = sy + (ey - sy) * t
        # 曲线偏移:中间段往 x 方向偏移 noise
        if 1 <= i < segments:
            mid_x += random.randint(-noise_px, noise_px)
            mid_y += random.randint(-noise_px, noise_px)
        # 当前段起点 = 上一个 bezier 点
        t_prev = (i - 1) / segments
        from_x = sx + (ex - sx) * t_prev
        from_y = sy + (ey - sy) * t_prev
        if 1 <= (i - 1) < segments:
            from_x += random.randint(-noise_px, noise_px)
            from_y += random.randint(-noise_px, noise_px)

        job = ctrl.post_swipe(
            int(from_x),
            int(from_y),
            int(mid_x),
            int(mid_y),
            duration=max(50, delay // segments),
        )
        job.wait()

    # 完成后延迟
    if delay > 0:
        time.sleep(delay / 1000)

    _LOG.debug(
        "NonlinearSwipe done: ({},{}) -> ({},{}) delay={}ms",
        sx,
        sy,
        ex,
        ey,
        delay,
    )
    return True


# ============================================================
# GoIntoEntryByGuide 核心
# ============================================================
# ============================================================
# GoIntoEntryByGuide 核心
# ============================================================
def _screencap_once(ctrl: Any) -> Any:
    """截屏一次,失败返 None。"""
    try:
        job = ctrl.post_screencap()
        image = job.wait().get()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("GoIntoEntryByGuide: screencap failed: {}", exc, exc_info=True)
        return None
    return image


def _ocr_box(
    context: Any,
    image: Any,
    expected: list[str],
    roi: tuple[int, int, int, int],
    threshold: float = 0.3,
) -> Any:
    """OCR 找文字,命中返 RecognitionDetail(box 必有),否则 None。

    支持多 alias(任一命中即返)。竖向排列(``order_by=Vertical``),左侧菜单 tab 适配。
    """
    for name in expected:
        try:
            jocr = JOCR(
                expected=[name],
                roi=list(roi),
                threshold=threshold,
                order_by="Vertical",
            )
            reco = context.run_recognition_direct(
                JRecognitionType.OCR,
                jocr,
                image,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("GoIntoEntryByGuide: OCR failed for '{}': {}", name, exc)
            continue
        if reco is None:
            continue
        if getattr(reco, "hit", False) and getattr(reco, "box", None):
            return reco
    return None


def _click_box(ctrl: Any, reco: Any) -> bool:
    """点 reco.box 中心。"""
    box = getattr(reco, "box", None)
    if box is None:
        return False
    x = box.x + box.w // 2
    y = box.y + box.h // 2
    try:
        ctrl.post_click(x, y).wait()
        return True
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("GoIntoEntryByGuide: click failed at ({}, {}): {}", x, y, exc)
        return False


def _swipe(
    ctrl: Any,
    start: tuple[int, int],
    end: tuple[int, int],
    duration_ms: int = 200,
) -> None:
    """线性 swipe。"""
    try:
        ctrl.post_swipe(start[0], start[1], end[0], end[1], duration_ms).wait()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("GoIntoEntryByGuide: swipe failed: {}", exc)


def _wait_for_freezes(context: Any, ms: int = 300) -> None:
    """等动画结束(narutomobile 用 post_wait_freezes,这里用 sleep 近似)。"""
    time.sleep(ms / 1000)


def go_into_entry_by_guide_run(
    context: Any,
    argv: Any,
    *,
    ocr_threshold: float = 0.3,
    max_top_scroll: int = 10,
    max_search_swipes: int = 20,
) -> bool:
    """GoIntoEntryByGuide 核心逻辑 — 完整版(pipeline 算法移植)。

    算法流程:
        1. 截屏,OCR 查"回流"判定回归账号 → 选不同 ROI
            - 普通:list_roi=(0, 66, 219, 627),swipe y=600→300
            - 回归:list_roi=(209, 88, 200, 580),swipe y=600→300,先点"忍界指引"
        2. 向上滚到顶 — 查"天赋"在最顶端
        3. OCR + 向下 swipe 最多 20 次找 ``entry_name``
        4. 点中 tab → sleep 0.5s
        5. OCR 查"前往"在 ``(834, 539, 287, 149)`` → 点它进 tab 实际内容页

    调用方约束(由 merged.json 节点顺序保证,本 action 不再验证):
        - 前置节点 ``IsInNinjaGuide`` 已确认在忍者指引页
        - 前置节点 ``open_ninja_guide`` 已打开忍者指引
        - 失败时 ``[JumpBack]ninja_guide_to_funtion_retry`` 会重试

    Args:
        context: maa context (Direct API 或 Agent,只需 ``.tasker.controller`` 存在)。
        argv: maa custom action 回调参数对象。
        ocr_threshold: OCR 阈值 (默认 0.3,narutomobile OCR 节点默认)。
        max_top_scroll: 滚到顶时最多循环次数 (默认 10)。
        max_search_swipes: 找 entry_name 时最多 swipe 次数 (默认 20,narutomobile 行为)。

    配置(``custom_action_param``):
        entry_name: ``str | List[str]``   -- 要找的 tab 文字
            单 alias: ``"组织"``
            多 alias: ``["秘境探险","秋境探险"]``(任一命中即可)
    """
    params = parse_custom_action_param(argv)
    raw = params.get("entry_name", "")
    if not raw:
        _LOG.warning("GoIntoEntryByGuide: missing entry_name param")
        return False
    entry_names: list[str] = [raw] if isinstance(raw, str) else list(raw)

    if not _MAAFW_AVAILABLE:
        _LOG.error("GoIntoEntryByGuide: maafw not available")
        return False

    ctrl = context.tasker.controller

    # 1. 截屏 + 判定回归账号
    image = _screencap_once(ctrl)
    if image is None:
        return False

    if _ocr_box(context, image, ["回流"], (0, 0, 195, 285), threshold=ocr_threshold):
        # 回归账号
        start = (300, 600)
        end = (300, 300)
        list_roi: tuple[int, int, int, int] = (209, 88, 200, 580)
        _LOG.debug("GoIntoEntryByGuide: returning player path")
        # 先点"忍界指引"切到主菜单
        reco = _ocr_box(context, image, ["忍界指引"], (0, 600, 212, 120), threshold=ocr_threshold)
        if reco is None:
            _LOG.warning("GoIntoEntryByGuide: returning player — 忍界指引 not found")
            return False
        if not _click_box(ctrl, reco):
            return False
        _wait_for_freezes(context, 300)
    else:
        # 普通账号
        start = (70, 600)
        end = (70, 300)
        list_roi = (0, 66, 219, 627)
        _LOG.debug("GoIntoEntryByGuide: normal player path")

    # 2. 向上滚到顶(查"天赋"在 list_roi 顶端)
    image = _screencap_once(ctrl)
    if image is None:
        return False
    for attempt in range(max_top_scroll):
        if _ocr_box(context, image, ["天赋"], list_roi, threshold=ocr_threshold):
            _LOG.debug("GoIntoEntryByGuide: reached top (天赋 found), attempt={}", attempt)
            break
        _swipe(ctrl, end, start)  # end→start = 向上滚(手指向上滑,内容向下走,看到上方)
        _wait_for_freezes(context, 100)
        image = _screencap_once(ctrl)
        if image is None:
            return False
    else:
        _LOG.warning("GoIntoEntryByGuide: failed to scroll to top after {} attempts", max_top_scroll)

    # 3. OCR + 向下 swipe 找 entry_name(最多 20 次)
    reco = None
    for attempt in range(max_search_swipes):
        reco = _ocr_box(context, image, entry_names, list_roi, threshold=ocr_threshold)
        if reco is not None:
            _LOG.info(
                "GoIntoEntryByGuide: found '{}' on attempt={} box=({},{},{},{})",
                entry_names, attempt, reco.box.x, reco.box.y, reco.box.w, reco.box.h,
            )
            break
        _swipe(ctrl, start, end)  # start→end = 向下滚
        _wait_for_freezes(context, 100)
        image = _screencap_once(ctrl)
        if image is None:
            return False
    if reco is None:
        _LOG.warning(
            "GoIntoEntryByGuide: '{}' not found in ninja guide menu after {} swipes",
            entry_names, max_search_swipes,
        )
        return False

    # 4. 点中 tab
    if not _click_box(ctrl, reco):
        return False
    time.sleep(0.5)

    # 5. 点"前往"按钮(切到 tab 实际内容页)
    image = _screencap_once(ctrl)
    if image is None:
        return False
    qian_reco = _ocr_box(context, image, ["前往"], (834, 539, 287, 149), threshold=ocr_threshold)
    if qian_reco is None:
        _LOG.warning("GoIntoEntryByGuide: 前往 button not found after clicking tab")
        return False
    if not _click_box(ctrl, qian_reco):
        return False

    _LOG.info("GoIntoEntryByGuide: success, clicked 前往")
    return True


# ============================================================
# CleanLogs 核心 — 维护性 task,清理日志 / debug 截图 / 备份 log
# ============================================================
def _find_project_root() -> Path:
    """从 ``_actions_core`` 自身位置往上找含 ``maafw_bridge/`` 的目录。

    跟 ``agent/main.py::_find_project_root`` 是同一逻辑(支持两种部署):
        - 源码 dev: ``D:\\火影自动日常\\maafw_bridge\\_actions_core.py`` → 1 层
        - 部署 (理论上不会,因为 agent/main.py 的 _find_project_root 会先匹配上,Python
          不会同时跑两个 copy):``frontend/MFAAvalonia/maafw_bridge/_actions_core.py`` → 2 层

    找不到时 fallback 到当前工作目录(让 caller 拿到合理路径而不是直接报错)。
    """
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / "maafw_bridge").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    # fallback: cwd
    return Path.cwd()


def _purge_path(p: Path) -> int:
    """删文件或目录,返回释放字节数。失败静默(返回 0)。"""
    try:
        if p.is_file() or p.is_symlink():
            sz = p.stat().st_size
            p.unlink()
            return sz
        if p.is_dir():
            sz = sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
            shutil.rmtree(p, ignore_errors=True)
            return sz
    except (OSError, PermissionError) as exc:
        _LOG.warning("CleanLogs: failed to purge {}: {}", p, exc)
    return 0


def clean_logs_run(
    context: Any,
    argv: Any,
    *,
    keep_sessions: int = 3,
) -> bool:
    """CleanLogs 核心 — 清理 logs/ 旧 session debug + MFAAvalonia/debug/ 备份。

    策略 (``keep_sessions`` 默认 3,跟用户确认):
        1. ``logs/`` 下找所有 ``YYYYMMDD_HHMMSS/`` 格式 session 目录,按名字降序排
        2. 保留前 ``keep_sessions`` 个 session 完整内容
        3. 其余 session 只删 ``debug/`` 子目录(自动截图),保留 text log
        4. ``frontend/MFAAvalonia/debug/``:
           - 删所有 ``maafw.bak.*.log`` 备份
           - 删 ``on_error/`` 整个目录(报错时自动落的截图)
           - 保留 ``maafw.log`` 当前 log

    Args:
        context: maa context(不直接使用,但接口要求)。
        argv: maa custom action 回调参数,支持 ``custom_action_param``:
            - ``keep_sessions`` (int,默认走函数参数):保留几个最近 session
        keep_sessions: 函数默认参数。argv 存在 ``keep_sessions`` 时优先用 argv
            (action 配置文件是生产入口,函数参数只是单测/内部调用回退)。

    Returns:
        True=执行完成(部分失败也返 True,因为清理是 best-effort)。
    """
    # 解析参数
    params = parse_custom_action_param(argv)
    try:
        ks = int(params.get("keep_sessions", keep_sessions))
    except (TypeError, ValueError):
        ks = keep_sessions
    if ks < 0:
        ks = 0

    project_root = _find_project_root()
    logs_dir = project_root / "logs"
    maafw_debug = project_root / "debug"

    total_freed = 0
    detail: list[str] = []

    # 1. logs/ 旧 session 清理
    if logs_dir.is_dir():
        session_pattern = lambda d: (
            d.is_dir()
            and len(d.name) == 15
            and d.name[8] == "_"
            and d.name[:8].isdigit()
            and d.name[9:].isdigit()
        )
        sessions = sorted(
            (d for d in logs_dir.iterdir() if session_pattern(d)),
            key=lambda d: d.name,
            reverse=True,
        )
        # 保留前 ks 个完整,其余只删 debug/
        for i, session in enumerate(sessions):
            if i < ks:
                continue
            debug_subdir = session / "debug"
            if debug_subdir.is_dir():
                freed = _purge_path(debug_subdir)
                total_freed += freed
                detail.append(f"{session.name}/debug -{freed/1024/1024:.1f}MB")

    # 2. MFAAvalonia/debug/ 清理
    if maafw_debug.is_dir():
        for f in maafw_debug.iterdir():
            if not f.is_file():
                continue
            # 删所有 maafw.bak.*.log 备份
            if f.name.startswith("maafw.bak.") and f.name.endswith(".log"):
                freed = _purge_path(f)
                total_freed += freed
                detail.append(f"maafw.bak -{freed/1024/1024:.1f}MB")
        # 删 on_error/ 目录
        on_error = maafw_debug / "on_error"
        if on_error.is_dir():
            freed = _purge_path(on_error)
            total_freed += freed
            detail.append(f"on_error/ -{freed/1024/1024:.1f}MB")

    _LOG.info(
        "CleanLogs done: keep_sessions={} freed={}B ({:.1f}MB) details=[{}]",
        ks, total_freed, total_freed / 1024 / 1024,
        "; ".join(detail) or "(nothing to clean)",
    )
    return True
