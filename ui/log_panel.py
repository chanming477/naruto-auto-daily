"""ui.log_panel — 实时日志面板。

职责(单一):
    接收 ``QtLogHandler`` 的信号,显示在 ``QTextEdit`` 上。

设计要点:
    - 数据来源: Qt signal(由 ``QtLogHandler`` 桥接自 loguru),**不**直接调任何业务模块
    - 支持: 级别过滤(INFO/WARNING/ERROR/ALL)+ 自动滚动开关 + 清空按钮
    - 显示 run_id / task_id / elapsed_ms(从 extra 字段抓)
    - 不阻塞 UI:用 ``append`` 增量追加(不调 ``setHtml`` 全量刷新)
    - 控制内存:最多保留 5000 行(超过滚动丢弃旧行)

公开 API:
    LogPanel(parent=None)
        .on_log_record(message: str) -> None
        .on_level_changed(level: str) -> None
        .on_extra_changed(extra: dict) -> None
        .clear() -> None
"""

from __future__ import annotations

from collections import deque
from typing import Any

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.log_panel requires PySide6",
    ) from _exc


# 日志级别到颜色的映射
_LEVEL_COLOR: dict[str, str] = {
    "TRACE": "#7f8c8d",
    "DEBUG": "#7f8c8d",
    "INFO": "#2c3e50",
    "SUCCESS": "#27ae60",
    "WARNING": "#e67e22",
    "ERROR": "#c0392b",
    "CRITICAL": "#8e44ad",
}


class LogPanel(QtWidgets.QGroupBox):
    """实时日志面板。"""

    #: 日志行最大保留数(超过滚动丢旧行,防内存膨胀)
    MAX_LINES = 5000

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("日志面板", parent)
        # 缓冲(在信号回调里用,主线程渲染前先 append 到 deque)
        self._buffer: deque[str] = deque(maxlen=self.MAX_LINES)
        self._current_level: str = "ALL"  # 用户选择的过滤级别
        self._current_extra: dict[str, Any] = {}  # 最新一条的 extra
        self._build_ui()

    # ----- public ----------------------------------------------------

    def on_log_record(self, message: str) -> None:
        """Qt signal 槽:接收一条原始 loguru 消息。

        P1-BUG-01: 不再解析 message 字符串拿 level — 由 ``on_level_changed`` 提前存。
        """
        if not self._should_show():
            return
        # 渲染(把尾部换行去掉,append 一次)
        line = message.rstrip("\n")
        if self._current_extra:
            extra_str = "  ".join(
                f"{k}={v}" for k, v in self._current_extra.items() if v is not None
            )
            if extra_str:
                line = f"{line}  | {extra_str}"
        self._buffer.append(line)
        # 渲染
        self._append_colored_line(line)

    def on_level_changed(self, level: str) -> None:
        """Qt signal 槽:实际日志级别(用于过滤判断)。"""
        self._last_level = level

    def on_extra_changed(self, extra: dict[str, Any]) -> None:
        """Qt signal 槽:bind 字段。"""
        self._current_extra = dict(extra) if extra else {}

    def clear(self) -> None:
        """清空日志。"""
        self._buffer.clear()
        self._text.clear()

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        # 顶部控制
        ctrl = QtWidgets.QHBoxLayout()
        ctrl.addWidget(QtWidgets.QLabel("级别:", self))
        self._level_combo = QtWidgets.QComboBox(self)
        self._level_combo.addItems(["ALL", "INFO", "WARNING", "ERROR"])
        self._level_combo.setCurrentText("ALL")
        self._level_combo.currentTextChanged.connect(self._on_filter_changed)
        ctrl.addWidget(self._level_combo)
        self._auto_scroll = QtWidgets.QCheckBox("自动滚动", self)
        self._auto_scroll.setChecked(True)
        ctrl.addWidget(self._auto_scroll)
        ctrl.addStretch(1)
        self._btn_clear = QtWidgets.QPushButton("清空", self)
        self._btn_clear.clicked.connect(self.clear)
        ctrl.addWidget(self._btn_clear)
        layout.addLayout(ctrl)
        # 文本框
        self._text = QtWidgets.QPlainTextEdit(self)
        self._text.setReadOnly(True)
        # P0-STABLE-01: 用 Qt 内置的 setMaximumBlockCount 自动限制行数,
        # 避免之前 cursor.deleteChar() 只删一个字符的 bug。
        self._text.setMaximumBlockCount(self.MAX_LINES)
        # 等宽字体
        font = QtGui.QFont("Consolas, Courier New, monospace")
        font.setStyleHint(QtGui.QFont.Monospace)
        self._text.setFont(font)
        # 暗色背景
        self._text.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
        )
        layout.addWidget(self._text, stretch=1)
        # 当前最新级别(过滤判断用)
        self._last_level = "INFO"

    def _on_filter_changed(self, level: str) -> None:
        self._current_level = level

    def _should_show(self, level: str | None = None) -> bool:
        """根据当前过滤级别 + 消息级别判断是否显示。

        P1-BUG-01: 不再解析 message 字符串(由 QtLogHandler 传 level 参数)。
        """
        if self._current_level == "ALL":
            return True
        target = level or self._last_level
        # 过滤:WARNING 包含 ERROR;INFO 包含 INFO+SUCCESS
        priority = {
            "TRACE": 0, "DEBUG": 1, "INFO": 2, "SUCCESS": 3,
            "WARNING": 4, "ERROR": 5, "CRITICAL": 6,
        }
        cur = priority.get(self._current_level, 2)
        msg = priority.get(target, 2)
        return msg >= cur

    def _append_colored_line(self, line: str) -> None:
        """追加一行带颜色。

        P0-STABLE-01 修复: 之前用 cursor.deleteChar() 只删 1 字符,语义错。
        现在靠 ``QPlainTextEdit.setMaximumBlockCount(MAX_LINES)`` 自动丢旧行,
        本方法只做 insertHtml + 颜色,不再手动清理。
        """
        level = self._last_level
        color = _LEVEL_COLOR.get(level, "#d4d4d4")
        cursor = self._text.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        # 把 line 中的 '<' '>' 转义防 HTML 注入
        safe = (
            line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )
        cursor.insertHtml(f'<span style="color: {color};">{safe}</span><br/>')
        if self._auto_scroll.isChecked():
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())
