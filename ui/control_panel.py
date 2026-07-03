"""ui.control_panel — Start / Stop 控制面板。

职责(单一):
    提供 Start / Stop 按钮 + 当前方案下拉。

设计要点:
    - 不调任何业务模块(由 MainWindow 监听信号后转给 RunWorker / TaskEngine)
    - Start 按钮只在「未运行」时可点;Stop 按钮只在「运行中」时可点(状态联动)
    - 提供信号:
        - ``start_requested(list[str])`` — 参数 = 选中的 task_ids
        - ``stop_requested()``
        - ``scheme_selected(str)`` — 方案下拉变化

公开 API:
    ControlPanel(parent=None)
        .set_running(bool) -> None      # 控制按钮 enable 状态
        .set_available_schemes(list[str])
        .set_current_scheme(name) -> None
        .get_current_scheme() -> str
"""

from __future__ import annotations

from typing import Iterable

try:
    from PySide6 import QtCore, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.control_panel requires PySide6",
    ) from _exc


class ControlPanel(QtWidgets.QGroupBox):
    """控制面板(Start / Stop + 方案下拉)。

    Phase 5: 不实现真正 Pause(只 Start / Stop 避免语义重叠)。
    """

    start_requested = QtCore.Signal(list)  # 参数 = task_ids list
    stop_requested = QtCore.Signal()
    scheme_selected = QtCore.Signal(str)  # 参数 = scheme name

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__("控制面板", parent)
        self._build_ui()
        self.set_running(False)

    # ----- public ----------------------------------------------------

    def set_running(self, running: bool) -> None:
        """切换运行状态(控制按钮 enable)。"""
        self._btn_start.setEnabled(not running)
        self._btn_stop.setEnabled(running)
        # 运行时禁掉方案下拉(避免半途换方案)
        self._scheme_combo.setEnabled(not running)

    def set_available_schemes(self, names: Iterable[str]) -> None:
        """填充方案下拉框。"""
        current = self._scheme_combo.currentText()
        self._scheme_combo.clear()
        for n in names:
            self._scheme_combo.addItem(n)
        if current and current in names:
            self._scheme_combo.setCurrentText(current)

    def set_current_scheme(self, name: str) -> None:
        idx = self._scheme_combo.findText(name)
        if idx >= 0:
            self._scheme_combo.setCurrentIndex(idx)

    def get_current_scheme(self) -> str:
        return self._scheme_combo.currentText()

    def set_selected_task_ids(self, task_ids: list[str]) -> None:
        """Start 按钮点之前,需要先设置要跑的任务列表(由 MainWindow 在调用前注入)。"""
        self._pending_task_ids = list(task_ids)

    def get_pending_task_ids(self) -> list[str]:
        return list(getattr(self, "_pending_task_ids", []))

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)
        # 方案下拉
        layout.addWidget(QtWidgets.QLabel("方案:", self))
        self._scheme_combo = QtWidgets.QComboBox(self)
        self._scheme_combo.setMinimumWidth(120)
        self._scheme_combo.currentTextChanged.connect(self.scheme_selected.emit)
        layout.addWidget(self._scheme_combo)
        layout.addStretch(1)
        # 按钮
        self._btn_start = QtWidgets.QPushButton("Start ▶", self)
        self._btn_start.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop = QtWidgets.QPushButton("Stop ■", self)
        self._btn_stop.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        self._btn_stop.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self._btn_start)
        layout.addWidget(self._btn_stop)

    def _on_start(self) -> None:
        task_ids = self.get_pending_task_ids()
        if not task_ids:
            # 没选任务,啥也不做(MainWindow 监听可弹提示)
            return
        self.start_requested.emit(task_ids)
