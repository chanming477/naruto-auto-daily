"""ui.status_panel — 实时状态面板。

职责(单一):
    实时显示运行状态 / 当前任务 / 游戏状态 / 计数 / 运行时间。

设计要点:
    - 数据来源: ``ExecutionContext``(由 MainWindow 持有并引用,本面板**只读**)
    - 通过 QTimer 1 秒轮询刷新(避免复杂的回调链)
    - **不**改 ExecutionContext 的任何字段(只读)
    - 不调任何业务模块

公开 API:
    StatusPanel(ctx: ExecutionContext, parent=None)
        .start_ticking() -> None
        .stop_ticking() -> None
        .update_now() -> None     # 强制刷新一次
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.status_panel requires PySide6",
    ) from _exc

if TYPE_CHECKING:
    from core.base_task import ExecutionContext


class StatusPanel(QtWidgets.QGroupBox):
    """实时状态面板。"""

    def __init__(
        self,
        ctx: "ExecutionContext",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("状态面板", parent)
        self._ctx = ctx
        self._t0 = time.monotonic()
        self._build_ui()
        # 1 秒轮询
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.update_now)
        self.update_now()

    # ----- public ----------------------------------------------------

    def start_ticking(self) -> None:
        """开始轮询刷新。"""
        self._t0 = time.monotonic()
        if not self._timer.isActive():
            self._timer.start()

    def stop_ticking(self) -> None:
        """停止轮询。"""
        self._timer.stop()
        self.update_now()

    def update_now(self) -> None:
        """强制刷新一次显示。"""
        # 当前状态(程序级)
        sm_state = "—"
        try:
            sm_state = self._ctx.state_machine.state
        except Exception:
            pass
        self._lbl_state.setText(sm_state)
        # 当前任务
        self._lbl_task.setText(self._ctx.current_task_id or "—")
        # 游戏状态
        gs = "—"
        last_state = getattr(self._ctx, "last_state", None)
        if last_state is not None:
            gs = getattr(last_state, "value", str(last_state))
        self._lbl_game.setText(gs)
        # 计数
        results = self._ctx.task_results
        success = sum(1 for r in results if getattr(r, "is_success", False))
        fail = sum(1 for r in results if getattr(r, "is_failure", False))
        self._lbl_done.setText(str(success))
        self._lbl_fail.setText(str(fail))
        # 运行时间
        elapsed = time.monotonic() - self._t0
        self._lbl_runtime.setText(self._format_duration(elapsed))

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        # P1-QUAL-02: 去掉之前的 ``getter`` lambda — 占位文本只用于初始化,
        # 真实值由 ``update_now()`` 周期性刷新。这里只存 label 引用 + 初始占位。
        rows: list[tuple[str, QtWidgets.QLabel]] = [
            ("当前状态", QtWidgets.QLabel("—", self)),
            ("当前任务", QtWidgets.QLabel("—", self)),
            ("游戏状态", QtWidgets.QLabel("—", self)),
            ("已完成", QtWidgets.QLabel("0", self)),
            ("失败", QtWidgets.QLabel("0", self)),
            ("运行时间", QtWidgets.QLabel("00:00:00", self)),
        ]
        for row, (name, lbl_val) in enumerate(rows):
            lbl_name = QtWidgets.QLabel(f"{name}:", self)
            lbl_val.setStyleSheet("font-weight: bold;")
            layout.addWidget(lbl_name, row, 0)
            layout.addWidget(lbl_val, row, 1)
        # 引用
        self._lbl_state = rows[0][1]
        self._lbl_task = rows[1][1]
        self._lbl_game = rows[2][1]
        self._lbl_done = rows[3][1]
        self._lbl_fail = rows[4][1]
        self._lbl_runtime = rows[5][1]

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """格式化秒数为 HH:MM:SS。"""
        s = int(seconds)
        h, rem = divmod(s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
