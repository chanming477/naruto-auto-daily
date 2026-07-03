"""ui.resource_status_panel — 资源状态面板(模板目录)。

职责(单一):
    显示 ``resources/templates/<state>/`` 各 GameState 目录的模板数量。

设计要点:
    - 只读:不修改任何模板文件、不创建目录
    - 数据来源: ``ConfigManager.app.game_state.templates_dir`` 解析为
      ``<project_root>/resources/templates``
    - 检查每个 GameState(除 UNKNOWN 之外):HOME / POPUP / LOADING
    - 显示:模板数量 + 「已加载 / 缺失」状态
    - 启动时同步扫描;提供 ``refresh()`` 槽供外部触发重新扫描

公开 API:
    ResourceStatusPanel(project_root: Path, templates_dir: str, parent=None)
        .refresh() -> None
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.resource_status_panel requires PySide6",
    ) from _exc

if TYPE_CHECKING:
    pass

from state.game_state import GameState


class ResourceStatusPanel(QtWidgets.QGroupBox):
    """模板资源状态面板。"""

    #: 扫描完成时发出,参数 = ``{state_value: count}``
    scan_completed = QtCore.Signal(dict)

    def __init__(
        self,
        project_root: Path,
        templates_dir: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("资源状态", parent)
        self._project_root = Path(project_root).resolve()
        self._templates_dir = self._project_root / templates_dir
        self._build_ui()
        self.refresh()

    # ----- public ----------------------------------------------------

    def refresh(self) -> None:
        """重新扫描 templates 目录,更新 UI。"""
        # 状态文件后缀(图片模板)
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        counts: dict[str, int] = {}
        for state in GameState:
            if state == GameState.UNKNOWN:
                continue  # UNKNOWN 是 fallback,不参与模板匹配
            state_dir = self._templates_dir / state.value
            if not state_dir.is_dir():
                counts[state.value] = 0
                continue
            try:
                n = sum(1 for p in state_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
            except OSError:
                n = 0
            counts[state.value] = n
        self._update_ui(counts)
        self.scan_completed.emit(counts)

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        # 状态行:每行一个 GameState
        self._rows: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel]] = {}
        for state in GameState:
            if state == GameState.UNKNOWN:
                continue
            row = QtWidgets.QHBoxLayout()
            name_lbl = QtWidgets.QLabel(f"{state.value} 模板:", self)
            status_lbl = QtWidgets.QLabel("—", self)
            row.addWidget(name_lbl)
            row.addWidget(status_lbl, stretch=1)
            row.addStretch(2)
            layout.addLayout(row)
            self._rows[state.value] = (name_lbl, status_lbl)
        # 刷新按钮
        btn_row = QtWidgets.QHBoxLayout()
        self._btn_refresh = QtWidgets.QPushButton("刷新", self)
        self._btn_refresh.clicked.connect(self.refresh)
        btn_row.addStretch(1)
        btn_row.addWidget(self._btn_refresh)
        layout.addLayout(btn_row)

    def _update_ui(self, counts: dict[str, int]) -> None:
        for state_value, (name_lbl, status_lbl) in self._rows.items():
            n = counts.get(state_value, 0)
            if n == 0:
                status_lbl.setText("✗ 缺失")
                status_lbl.setStyleSheet("color: #c0392b;")  # 红
            else:
                status_lbl.setText(f"✓ 已加载 ({n} 张)")
                status_lbl.setStyleSheet("color: #27ae60;")  # 绿
