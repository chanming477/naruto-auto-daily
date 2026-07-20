"""agent.custom.utils — CustomAction / CustomRecognition 内部用的工具函数。

主要给 agent 模式下 ``reco.py`` 的真实现 (IsInNinjaGuide / IsCounterOverflow)
用,目前 reco.py 是占位,所以 utils.py 大部分也暂时空着。

TODO (2026-07-15): reco.py 真实现时,把 fast_ocr / click / save_screenshot 用上。
"""

from __future__ import annotations

from typing import Any

try:
    from maa.pipeline import JOCR, JRecognitionType  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    JOCR = None  # type: ignore
    JRecognitionType = None  # type: ignore
    _MAAFW_AVAILABLE = False

import numpy as np

from agent.utils.logger import get_agent_logger

_log = get_agent_logger()


def save_screenshot(context: Any) -> np.ndarray | None:
    """截屏返回 numpy array (BGR)。

    Args:
        context: maa context (Agent 模式下是 AgentContext)。

    Returns:
        numpy ndarray 或 None (截屏失败时)。
    """
    try:
        ctrl = context.tasker.controller
        job = ctrl.post_screencap()
        image = job.wait().get()
    except Exception as exc:  # noqa: BLE001
        _log.warning("screencap failed: {}", exc)
        return None
    return image


def fast_ocr(context: Any, image: np.ndarray, expected: list[str], roi: tuple[int, int, int, int] | None = None) -> Any:
    """快速 OCR — 在 image 的 roi 内找 expected 文字。

    Args:
        context: maa context。
        image: 截屏 numpy array (BGR)。
        expected: 要找的文字列表 (任一命中即可)。
        roi: (x, y, w, h) — 限定搜索区域,None 表示全图。

    Returns:
        RecognitionDetail 或 None (没命中)。
    """
    if not _MAAFW_AVAILABLE:
        _log.error("fast_ocr: maafw not available")
        return None
    jocr_kwargs: dict[str, Any] = {"expected": expected, "order_by": "Vertical"}
    if roi is not None:
        jocr_kwargs["roi"] = roi
    try:
        reco = context.run_recognition_direct(
            JRecognitionType.OCR,
            JOCR(**jocr_kwargs),
            image,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("OCR call failed: {}", exc)
        return None
    return reco


def click(context: Any, x: int, y: int) -> bool:
    """在 (x, y) 处点击。

    Returns:
        True = 成功,False = 异常。
    """
    try:
        ctrl = context.tasker.controller
        ctrl.post_click(x, y).wait()
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("click failed at ({}, {}): {}", x, y, exc)
        return False


def send_notification(title: str, message: str) -> None:
    """发送 Windows 桌面通知。

    任务完成/异常时调用, 通知用户任务状态。
    非 Windows 系统 / 未安装 notify-py 时静默跳过。

    Args:
        title: 通知标题
        message: 通知正文
    """
    try:
        from notifypy import Notify
        n = Notify()
        n.title = title
        n.message = message
        n.send()
        _log.debug("Notification sent: {} - {}", title, message)
    except ImportError:
        _log.debug("notify-py not installed, skip notification")
    except Exception as exc:  # noqa: BLE001
        _log.warning("send_notification failed: {}", exc)
