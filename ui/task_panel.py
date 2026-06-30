"""ui.task_panel — 任务勾选面板。

职责(单一):
    从 ``ConfigManager.tasks`` 加载任务列表,显示任务勾选框 + 名称 + 描述 + 预计耗时。

设计要点:
    - 数据来源: ``ConfigManager.app.config_dir / task_registry.yaml`` (Phase 1 资产)
    - **不**写死任务列表(由 ConfigManager 动态加载)
    - 不调任何业务模块(只读 ConfigManager 的 tasks 字段)
    - 提供信号 ``selection_changed(list[str])``,MainWindow 监听后传给 RunWorker

公开 API:
    TaskPanel(config_manager: ConfigManager, parent=None)
        .get_selected_task_ids() -> list[str]
        .selection_changed = Signal(list)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.task_panel requires PySide6; install via `pip install PySide6`",
    ) from _exc

if TYPE_CHECKING:
    from core.config_manager import ConfigManager


class TaskPanel(QtWidgets.QGroupBox):
    """任务选择面板。"""

    #: 用户勾选变化时发出,参数 = 当前勾选的 task_id 列表(按 display_order 升序)。
    selection_changed = QtCore.Signal(list)

    def __init__(
        self,
        config_manager: "ConfigManager",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("任务面板", parent)
        self._cfg = config_manager
        self._build_ui()
        self._load_tasks()

    # ----- public ----------------------------------------------------

    def get_selected_task_ids(self) -> list[str]:
        """返回当前勾选的 task_id 列表(按 display_order 升序)。"""
        selected: list[tuple[int, str]] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                # UserRole 存 display_order(int)
                order = item.data(QtCore.Qt.UserRole) or 0
                selected.append((order, item.data(QtCore.Qt.UserRole + 1)))
        selected.sort(key=lambda t: t[0])
        return [tid for _, tid in selected]

    def set_selected(self, task_ids: list[str]) -> None:
        """根据 task_ids 列表设置勾选状态(其它都取消)。"""
        target = set(task_ids)
        for i in range(self._list.count()):
            item = self._list.item(i)
            tid = item.data(QtCore.Qt.UserRole + 1)
            item.setCheckState(
                QtCore.Qt.Checked if tid in target else QtCore.Qt.Unchecked,
            )
        self._emit_selection_changed()

    def reload(self) -> None:
        """重新从 ConfigManager 加载任务列表(用于配置变更后刷新)。"""
        self._list.clear()
        self._load_tasks()

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        # 任务列表
        self._list = QtWidgets.QListWidget(self)
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list, stretch=1)
        # 底部按钮
        btn_row = QtWidgets.QHBoxLayout()
        self._btn_all = QtWidgets.QPushButton("全选", self)
        self._btn_none = QtWidgets.QPushButton("全不选", self)
        self._btn_all.clicked.connect(lambda: self._set_all(QtCore.Qt.Checked))
        self._btn_none.clicked.connect(lambda: self._set_all(QtCore.Qt.Unchecked))
        btn_row.addWidget(self._btn_all)
        btn_row.addWidget(self._btn_none)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _load_tasks(self) -> None:
        """从 ConfigManager.tasks 加载任务,按 display_order 升序。"""
        tasks_dict = self._cfg.tasks.tasks
        if not tasks_dict:
            placeholder = QtWidgets.QListWidgetItem(
                "(task_registry.yaml 中没有任务)",
                self._list,
            )
            placeholder.setFlags(QtCore.Qt.NoItemFlags)
            self._list.addItem(placeholder)
            return
        sorted_ids = sorted(
            tasks_dict.keys(),
            key=lambda tid: (tasks_dict[tid].display_order, tid),
        )
        for tid in sorted_ids:
            entry = tasks_dict[tid]
            # 注意:TaskEntry 没有 name 字段(Phase 1 schema),title 用 task_id
            label = self._format_label(tid, entry.description, entry.estimated_time_sec)
            item = QtWidgets.QListWidgetItem(label, self._list)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(
                QtCore.Qt.Checked if entry.enabled else QtCore.Qt.Unchecked,
            )
            # 存 display_order(int) + task_id(str) 到 UserRole / UserRole+1
            item.setData(QtCore.Qt.UserRole, int(entry.display_order))
            item.setData(QtCore.Qt.UserRole + 1, tid)
            # disabled 任务灰显
            if not entry.enabled:
                item.setForeground(QtCore.Qt.gray)
            self._list.addItem(item)

    @staticmethod
    def _format_label(task_id: str, description: str, eta_sec: int) -> str:
        """格式化单行任务显示。

        Args:
            task_id: 任务 ID(必显)。
            description: 任务描述(可选)。
            eta_sec: 预计耗时秒数(可选)。
        """
        meta_parts: list[str] = []
        if eta_sec > 0:
            meta_parts.append(f"~{eta_sec}s")
        if description:
            meta_parts.append(description)
        if meta_parts:
            return f"{task_id}    {' | '.join(meta_parts)}"
        return task_id

    def _on_item_changed(self, _item: QtWidgets.QListWidgetItem) -> None:
        self._emit_selection_changed()

    def _emit_selection_changed(self) -> None:
        self.selection_changed.emit(self.get_selected_task_ids())

    def _set_all(self, state: QtCore.Qt.CheckState) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if not (item.flags() & QtCore.Qt.ItemIsUserCheckable):
                continue
            item.setCheckState(state)
        self._emit_selection_changed()
