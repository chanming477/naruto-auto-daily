"""ui.main_window — 主窗口(QMainWindow)+ 启动入口。

职责(单一):
    装配各 Panel + 管理信号连接 + 菜单 + 状态栏。

设计要点:
    - 不写业务逻辑(由 RunWorker + TaskEngine 负责)
    - 启动入口: ``python -m ui.main_window`` 或 ``python main.py --gui``
    - 装配:
        - ConfigManager(读 task_registry / app_config)
        - ExecutionContext(window_manager / screenshot_manager / state_machine
          / state_machine 在 Phase 4 已经存在)
        - CommonActions + TaskEngine(Phase 3 资产)
        - SchemeManager(schemes/ 目录)
        - 5 个 Panel(任务 / 资源 / 状态 / 日志 / 控制)
    - RunWorker + QThread 异步跑任务

公开 API:
    MainWindow(project_root=None, parent=None)
        .show() -> None
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.main_window requires PySide6",
    ) from _exc

if TYPE_CHECKING:
    from core.base_task import ExecutionContext
    from tasks.task_engine import TaskEngine

from ui.config_dialog import ConfigDialog
from ui.control_panel import ControlPanel
from ui.log_panel import LogPanel
from ui.qt_log_handler import QtLogHandler, install as install_log_handler
from ui.resource_status_panel import ResourceStatusPanel
from ui.run_worker import RunWorker
from ui.scheme_manager import SchemeManager
from ui.status_panel import StatusPanel
from ui.task_panel import TaskPanel


class MainWindow(QtWidgets.QMainWindow):
    """Phase 5 主窗口。"""

    def __init__(
        self,
        project_root: Path | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_root = Path(project_root).resolve() if project_root else Path.cwd()
        # 配置
        from core.config_manager import ConfigManager

        self._cfg = ConfigManager(self._project_root, auto_load=True)
        # 方案
        self._schemes = SchemeManager(self._project_root / "schemes")
        # ExecutionContext(window_manager / screenshot_manager / state_machine 必传,
        # 业务 Phase 1 资产;这里用 MagicMock 跑得起 GUI 但不能真截图)
        from unittest.mock import MagicMock
        from core.base_task import ExecutionContext
        from core.state_machine import build_default_state_machine

        self._ctx = ExecutionContext(
            config=self._cfg,
            window_manager=MagicMock(),
            screenshot_manager=MagicMock(),
            state_machine=build_default_state_machine("IDLE", log_transitions=False),
        )
        # CommonActions + TaskEngine(Phase 3 资产)
        from device.adb_client import ADBClient
        from device.types import ActionResult
        from recognition.template_matcher import TemplateMatcher
        from recognizer.page_recognizer import PageRecognizer
        from state.game_state import GameState
        from state_machine.game_state_machine import GameStateMachine
        from tasks.common_actions import CommonActions
        from tasks.task_engine import TaskEngine

        # ADB client(用 MagicMock fallback,Phase 5 demo 不连真 ADB)
        self._adb = MagicMock(spec=ADBClient)
        self._adb.screenshot.return_value = ActionResult(
            True, "mock screenshot", None,
        )
        self._adb.keyevent.return_value = ActionResult(True, "mock", None)
        self._adb.tap.return_value = ActionResult(True, "mock", None)
        # Recognizer / game_sm
        matcher = TemplateMatcher(self._cfg)
        templates_root = self._project_root / self._cfg.app.game_state.templates_dir
        self._recognizer = PageRecognizer(templates_root, matcher=matcher)
        self._game_sm = GameStateMachine(initial=GameState.UNKNOWN)
        # CommonActions
        self._common = CommonActions(
            adb_client=self._adb,
            recognizer=self._recognizer,
            game_sm=self._game_sm,
            config=self._cfg,
            project_root=self._project_root,
        )
        # TaskEngine
        self._engine = TaskEngine(self._ctx, common_actions=self._common)
        # Worker / Thread(初始不启动)
        self._thread: QtCore.QThread | None = None
        self._worker: RunWorker | None = None
        # QtLogHandler
        self._log_handler = QtLogHandler()
        self._log_sink_id = install_log_handler(self._log_handler)
        # UI 装配
        self.setWindowTitle("Naruto Auto Daily — 桌面客户端 (Phase 5)")
        self.resize(900, 700)
        self._build_ui()
        self._wire_signals()
        self._populate_schemes()
        # 状态栏
        self._status_lbl = QtWidgets.QLabel("Ready | run_id: —", self)
        self.statusBar().addPermanentWidget(self._status_lbl)

    # ----- public ----------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt convention)
        """关窗时清理 worker thread + log handler。

        P1-STABLE-02 修复: 旧版 2 秒超时过短,subprocess 线程可能没退出,
        留下僵尸线程(QThread + loguru sink)。改为:
            1. engine.stop()  触发 abort flag
            2. thread.quit()  通知退出事件循环
            3. wait(5000)     给足 5 秒
            4. 仍未结束 → loguru warning + 继续(不让用户卡住)
        """
        from loguru import logger
        try:
            if self._thread is not None and self._thread.isRunning():
                # 1) 通知 engine 停止(转发到 Scheduler.is_aborted)
                try:
                    self._engine.stop()
                except Exception as exc:
                    logger.warning("closeEvent: engine.stop() raised: {}", exc)
                # 2) 通知 thread 退出
                self._thread.quit()
                # 3) 等最多 5 秒
                if not self._thread.wait(5000):
                    logger.warning(
                        "closeEvent: QThread 未在 5s 内退出,可能留有 zombie 线程 "
                        "(task_id={} / run_id={})",
                        getattr(self._ctx, "current_task_id", "?"),
                        self._ctx.run_id,
                    )
        except Exception as exc:
            logger.warning("closeEvent: 清理 worker thread 异常: {}", exc)
        try:
            from ui.qt_log_handler import uninstall
            uninstall(self._log_handler, self._log_sink_id)
        except Exception as exc:
            logger.warning("closeEvent: 卸载 log handler 异常: {}", exc)
        super().closeEvent(event)

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        """5 个 panel 用 QVBoxLayout 垂直堆叠。"""
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        # 任务面板
        self._task_panel = TaskPanel(self._cfg, self)
        # 资源状态(模板)
        self._resource_panel = ResourceStatusPanel(
            self._project_root,
            self._cfg.app.game_state.templates_dir,
            self,
        )
        # 状态面板
        self._status_panel = StatusPanel(self._ctx, self)
        # 日志面板
        self._log_panel = LogPanel(self)
        # 控制面板
        self._control_panel = ControlPanel(self)
        layout.addWidget(self._task_panel)
        layout.addWidget(self._resource_panel)
        layout.addWidget(self._status_panel)
        layout.addWidget(self._log_panel, stretch=1)
        layout.addWidget(self._control_panel)
        # 菜单
        self._build_menu()

    def _build_menu(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")
        act_reload_schemes = file_menu.addAction("重新加载方案")
        act_reload_schemes.triggered.connect(self._populate_schemes)
        file_menu.addSeparator()
        act_quit = file_menu.addAction("&Exit")
        act_quit.triggered.connect(self.close)
        cfg_menu = mb.addMenu("&Config")
        act_edit_cfg = cfg_menu.addAction("&Edit Config...")
        act_edit_cfg.triggered.connect(self._on_edit_config)
        help_menu = mb.addMenu("&Help")
        act_about = help_menu.addAction("&About")
        act_about.triggered.connect(self._on_about)

    def _wire_signals(self) -> None:
        # QtLogHandler → LogPanel
        self._log_handler.log_record.connect(self._log_panel.on_log_record)
        self._log_handler.level_changed.connect(self._log_panel.on_level_changed)
        self._log_handler.extra_changed.connect(self._log_panel.on_extra_changed)
        # TaskPanel 选择变化 → ControlPanel pending task_ids
        self._task_panel.selection_changed.connect(
            self._control_panel.set_selected_task_ids,
        )
        # 初始化时先 push 一次(避免 Start 按钮不响应)
        self._control_panel.set_selected_task_ids(
            self._task_panel.get_selected_task_ids(),
        )
        # ControlPanel → MainWindow
        self._control_panel.start_requested.connect(self._on_start)
        self._control_panel.stop_requested.connect(self._on_stop)
        self._control_panel.scheme_selected.connect(self._on_scheme_selected)

    def _populate_schemes(self) -> None:
        """填充方案下拉 + 选 daily(如果存在)。"""
        names = self._schemes.list_schemes()
        self._control_panel.set_available_schemes(names)
        if "daily" in names:
            self._control_panel.set_current_scheme("daily")
            self._on_scheme_selected("daily")

    def _on_scheme_selected(self, name: str) -> None:
        """方案选择:加载 task_ids,同步到 TaskPanel 勾选。"""
        try:
            task_ids = self._schemes.load(name) or []
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, "加载方案失败", f"方案 '{name}' 加载失败:\n{exc}",
            )
            return
        self._task_panel.set_selected(task_ids)
        # log
        from loguru import logger
        logger.info(f"scheme selected: {name} ({len(task_ids)} task(s))")

    def _on_start(self, task_ids: list[str]) -> None:
        """启动 worker thread。"""
        if self._thread is not None and self._thread.isRunning():
            return  # 已经在跑
        # 1) 准备 worker + thread
        self._thread = QtCore.QThread(self)
        self._worker = RunWorker(self._engine, task_ids)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.progress.connect(self._on_worker_progress)
        # 2) 状态:running
        self._control_panel.set_running(True)
        self._status_panel.start_ticking()
        self._status_lbl.setText(f"Running | run_id: {self._ctx.run_id}")
        from loguru import logger
        logger.info(f"RunWorker started: tasks={task_ids}")
        # 3) 启动
        self._thread.start()

    def _on_stop(self) -> None:
        """停止:转发到 TaskEngine.stop(),worker 看到 abort flag 自动退出。"""
        if self._engine is not None:
            self._engine.stop()
        from loguru import logger
        logger.warning("Stop requested; waiting for worker to exit")

    def _on_worker_finished(self, report) -> None:
        """worker 跑完。"""
        self._status_panel.stop_ticking()
        self._control_panel.set_running(False)
        from loguru import logger
        logger.success(
            "RunWorker finished: total={} success={} fail={} aborted={}",
            report.total_count, report.success_count, report.fail_count, report.aborted,
        )
        self._status_lbl.setText(
            f"Done | run_id: {self._ctx.run_id} | total={report.total_count} "
            f"success={report.success_count} fail={report.fail_count}",
        )
        # 清理 thread
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._worker = None
        self._thread = None

    def _on_worker_error(self, msg: str) -> None:
        self._status_panel.stop_ticking()
        self._control_panel.set_running(False)
        from loguru import logger
        logger.error("RunWorker error: {}", msg)
        self._status_lbl.setText(f"Error | {msg}")

    def _on_worker_progress(self, task_id: str, result) -> None:
        from loguru import logger
        # result.status 可能是 TaskStatus 枚举(MagicMock 时是 str) — 都支持
        status_val = getattr(result.status, "value", result.status)
        logger.info(f"task done: {task_id} status={status_val}")

    def _on_edit_config(self) -> None:
        dlg = ConfigDialog(self._cfg, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            from loguru import logger
            logger.success("Config saved and reloaded")
            # 任务面板可能变了(用户改了 task_registry 不太可能,reload 一下)
            self._task_panel.reload()
            self._resource_panel.refresh()

    def _on_about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            "About",
            "Naruto Auto Daily\n"
            "Phase 5 桌面客户端 (PySide6)\n\n"
            "Phase 1-4 业务逻辑不变,仅展示和交互。",
        )


def main(argv: list[str] | None = None) -> int:
    """主入口: ``python -m ui.main_window`` 或 ``python main.py --gui``。"""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv or sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
