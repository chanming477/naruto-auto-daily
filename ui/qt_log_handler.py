"""ui.qt_log_handler — loguru → Qt signal 桥接。

职责(单一):
    把任何模块的 ``logger.info("...")`` 实时同步到 ``LogPanel``。

设计要点:
    - 用 loguru 的 function sink 接口,接收 ``(message, record)`` 二元组。
    - 从 ``record`` 直接拿 level.name + record.extra,**不解析字符串**。
    - signal 跨线程安全:Qt 自动用 ``QueuedConnection`` 在 UI 线程派发。
    - 不做任何业务:不调任何业务模块、不改任何状态、不读任何 ctx。

公开 API:
    QtLogHandler(parent=None)
        .log_record = Signal(str)
        .level_changed = Signal(str)
        .extra_changed = Signal(dict)
    install(handler) -> int
    uninstall(handler, sink_id) -> None
"""

from __future__ import annotations

from typing import Any

from loguru import logger

try:
    from PySide6 import QtCore
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.qt_log_handler requires PySide6; install via `pip install PySide6`",
    ) from _exc


class QtLogHandler(QtCore.QObject):
    """loguru sink → Qt signal 桥接器。"""

    log_record = QtCore.Signal(str)
    level_changed = QtCore.Signal(str)
    extra_changed = QtCore.Signal(dict)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)

    def write(self, message: Any, record: dict[str, Any] | None = None) -> None:
        """loguru function sink 入口。

        loguru 的 function sink 模式: ``sink(message: Message)``,Message 有
        ``.record`` 属性(完整 dict)。我们兼容两种调用方式:
            - 旧式 ``sink(message: str)`` — record 为 None
            - 新式 ``sink(message: Message)`` — record 从 message.record 拿
        """
        if record is None:
            # 兼容:从 message 对象拿
            record = getattr(message, "record", None) or {}
        try:
            level_obj = record.get("level")
            level = level_obj.name if hasattr(level_obj, "name") else str(level_obj)
        except Exception:
            level = "INFO"
        try:
            extra = record.get("extra") or {}
            # 过滤掉 None 值(避免显示 task_id=None 这种噪声)
            extra = {k: v for k, v in extra.items() if v is not None}
        except Exception:
            extra = {}
        try:
            self.log_record.emit(str(message).rstrip("\n"))
            self.level_changed.emit(level)
            self.extra_changed.emit(extra)
        except RuntimeError:  # Qt 对象已 delete(测试 teardown 时的常见情况)
            pass


def install(handler: QtLogHandler) -> int:
    """把 handler 注册到全局 loguru,返回 sink id(给 uninstall 用)。

    P1-STABLE-01 修复: 用 loguru 的 function sink 模式,让 sink 收到完整
    ``Message`` 对象(record 在 message.record 里)。不再用 format 字符串解析。
    """
    def _sink(message):  # noqa: ANN001 — loguru Message type
        # 兼容:message 是 loguru Message 对象(str() 拿格式化后的文本,record 拿 dict)
        record = getattr(message, "record", None)
        handler.write(message, record=record)

    sink_id = logger.add(
        _sink,
        level="DEBUG",
        enqueue=False,  # 同步派发,信号在主线程被 Qt queued 接管
    )
    return sink_id


def uninstall(handler: QtLogHandler, sink_id: int) -> None:
    """从全局 loguru 卸载 handler。"""
    try:
        logger.remove(sink_id)
    except ValueError:
        pass  # 已被卸载
