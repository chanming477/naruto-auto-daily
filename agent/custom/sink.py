"""agent.custom.sink — TaskerEventSink 注册 (Agent 模式)。

AspectRatioChecker: 任务启动时检测模拟器分辨率是否为 16:9,
如果不是则停止任务。

来源: MaaAutoNaruto v1.3.41 ``agent/custom/sink.py``。

2026-07-21 update: 删 NotificationSink (弹窗通知), 用户不需要桌面通知。
"""

from __future__ import annotations

from typing import Any

try:
    from maa.agent.agent_server import AgentServer  # type: ignore
    from maa.tasker import Tasker, TaskerEventSink  # type: ignore
    from maa.event_sink import NotificationType  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    AgentServer = None  # type: ignore
    Tasker = None  # type: ignore
    TaskerEventSink = None  # type: ignore
    NotificationType = None  # type: ignore
    _MAAFW_AVAILABLE = False

from agent.utils.logger import get_agent_logger

_log = get_agent_logger()

# 目标宽高比 16:9, ±2% 容差
_TARGET_RATIO = 16.0 / 9.0
_TOLERANCE = 0.02


def _calc_ratio(width: int, height: int) -> float:
    """计算宽高比 (始终 = 长边/短边)。"""
    w, h = float(width), float(height)
    return max(w, h) / min(w, h) if min(w, h) > 0 else 0.0


def _is_16x9(width: int, height: int) -> bool:
    """检查是否 ≈16:9。"""
    if width <= 0 or height <= 0:
        return False
    ratio = _calc_ratio(width, height)
    return abs(ratio - _TARGET_RATIO) <= _TARGET_RATIO * _TOLERANCE


if _MAAFW_AVAILABLE and AgentServer is not None:

    @AgentServer.tasker_sink()
    class AspectRatioChecker(TaskerEventSink):
        """任务启动时检查分辨率。

        在每次任务开始时检测模拟器分辨率是否为 16:9。
        如果不是则调用 tasker.post_stop() 停止任务。
        """

        def on_tasker_task(  # type: ignore[override]
            self,
            tasker: Any,
            noti_type: Any,
            detail: Any,
        ) -> None:
            # 只在任务启动时检查
            if noti_type != NotificationType.Starting:
                return

            # 忽略停止事件
            entry = getattr(detail, "entry", "")
            if entry == "MaaTaskerPostStop":
                return

            _log.debug(
                "AspectRatioChecker: task={} entry={}",
                getattr(detail, "task_id", "?"),
                entry,
            )

            ctrl = tasker.controller
            if ctrl is None:
                _log.error("AspectRatioChecker: 无法获取 controller")
                return

            # 取当前截图
            try:
                img = ctrl.cached_image
                if img is None:
                    job = ctrl.post_screencap()
                    img = job.wait().get()
            except Exception as exc:
                _log.error("AspectRatioChecker: 截图失败: {}", exc)
                return

            if img is None:
                _log.error("AspectRatioChecker: 截图为空")
                return

            height, width = img.shape[:2]
            if not _is_16x9(width, height):
                actual = _calc_ratio(width, height)
                _log.error(
                    "AspectRatioChecker: 分辨率不匹配! "
                    "当前={}x{} (比例={:.4f}), "
                    "需要 16:9 (如 1920x1080)。停止任务。",
                    width, height, actual,
                )
                tasker.post_stop()
            else:
                _log.debug(
                    "AspectRatioChecker: 通过 {}x{} (16:9)",
                    width, height,
                )


    _log.info("Agent 模式 tasker sink 已注册: AspectRatioChecker")
