"""test_phase5_pipeline.py — Phase 5 端到端测试(用 pytest-qt)。

覆盖:
- MainWindow 启动成功(无 ADB / 无崩溃)
- TaskPanel 从 task_registry.yaml 加载任务
- ResourceStatusPanel 检测 templates 状态
- SchemeManager 增删改查
- ConfigDialog 往返
- LogPanel 接收 Qt signal
- RunWorker 启动 + finished signal
- 完整流程: GUI 启动 → 加载方案 → 启动 worker → 接收日志 → 任务结束
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 跳过整个文件如果 PySide6 不可用
pytest.importorskip("PySide6", reason="PySide6 not installed")

from PySide6 import QtCore, QtWidgets

from ui.config_dialog import ConfigDialog
from ui.control_panel import ControlPanel
from ui.log_panel import LogPanel
from ui.main_window import MainWindow
from ui.qt_log_handler import QtLogHandler, install, uninstall
from ui.resource_status_panel import ResourceStatusPanel
from ui.run_worker import RunWorker
from ui.scheme_manager import SchemeManager
from ui.status_panel import StatusPanel
from ui.task_panel import TaskPanel


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def project_with_daily_signin(tmp_path: Path) -> Path:
    """最小可用项目根,带 task_registry.yaml + app_config.yaml + daily_signin 任务。"""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "app_config.yaml").write_text(
        "app: {}\n"
        "logger:\n  console_level: WARNING\n  file_level: DEBUG\n  log_dir: logs\n"
        "  rotation_mb: 50\n  retention_days: 30\n  compression: true\n"
        "  auto_screenshot_on_error: true\n"
        "scheduler:\n  stop_on_failure: false\n  inter_task_delay_sec: 0.0\n"
        "  startup_warmup_sec: 0\n  task_timeout_sec: 30\n  heartbeat_interval_sec: 30\n"
        "state_machine:\n  initial_state: IDLE\n  failure_state: FAILED\n"
        "  success_state: COMPLETED\n  log_transitions: false\n"
        "screenshot:\n  output_dir: screenshots\n  backend: win32_print_window\n"
        "  to_grayscale: false\n  max_empty_retries: 3\n  retry_delay_ms: 200\n"
        "adb:\n  adb_path: ''\n  default_serial: ''\n  command_timeout_sec: 5\n  retry_count: 1\n"
        "template_matching:\n  default_threshold: 0.85\n  multi_scale: false\n"
        "  multi_scale_range: [0.95, 1.0, 1.05]\n"
        "game_state:\n  initial_state: UNKNOWN\n  templates_dir: resources/templates\n"
        "  recovery_probe_max: 3\n"
        "retry:\n  max_attempts: 3\n  delay_seconds: 0.0\n  exponential_backoff: false\n"
        "  max_delay_seconds: 1.0\n  retryable_exceptions: []\n"
        "recovery:\n  max_unknown_retries: 2\n  max_popup_retries: 2\n"
        "  max_loading_seconds: 5.0\n  adb_reconnect_attempts: 2\n"
        "logging_ext: {}\n",
        encoding="utf-8",
    )
    (cfg_dir / "device_config.yaml").write_text(
        "active_profile: default\nprofiles:\n  default:\n    match_mode: title_contains\n"
        "    match_keywords: []\n    process_blacklist: []\n    require_visible: true\n"
        "    require_not_minimized: true\n    expected_width: 0\n    expected_height: 0\n",
        encoding="utf-8",
    )
    (cfg_dir / "task_registry.yaml").write_text(
        "tasks:\n  daily_signin:\n"
        "    task_class: 'tasks.daily_signin_task.DailySigninTask'\n"
        "    enabled: true\n    display_order: 1\n    category: daily\n"
        "    description: 'Phase 5 E2E 任务'\n    estimated_time_sec: 5\n"
        "    retry_on_failure: false\n    max_retries: 0\n    config_options: {}\n",
        encoding="utf-8",
    )
    # templates 目录(空 → ResourceStatusPanel 应显示「缺失」)
    for s in ("HOME", "POPUP", "LOADING"):
        (tmp_path / "resources" / "templates" / s).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def templates_with_some(project_with_daily_signin: Path) -> Path:
    """加一个 HOME 模板(测试「已加载」路径)。"""
    home_dir = project_with_daily_signin / "resources" / "templates" / "HOME"
    (home_dir / "test_template.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return project_with_daily_signin


# ============================================================
# MainWindow 启动
# ============================================================


def test_phase5_main_window_starts_without_adb(qtbot, project_with_daily_signin):
    """MainWindow 能创建 + 显示 + 关闭,无 ADB 也能跑。"""
    win = MainWindow(project_with_daily_signin)
    qtbot.addWidget(win)
    win.show()
    # 不崩
    assert win.isVisible()
    win.close()


def test_phase5_main_window_has_all_panels(qtbot, project_with_daily_signin):
    """MainWindow 含 5 个 panel(task / resource / status / log / control)。"""
    win = MainWindow(project_with_daily_signin)
    qtbot.addWidget(win)
    assert hasattr(win, "_task_panel")
    assert hasattr(win, "_resource_panel")
    assert hasattr(win, "_status_panel")
    assert hasattr(win, "_log_panel")
    assert hasattr(win, "_control_panel")
    win.close()


# ============================================================
# TaskPanel
# ============================================================


def test_phase5_task_panel_loads_daily_signin(qtbot, project_with_daily_signin):
    """TaskPanel 从 task_registry.yaml 加载 daily_signin。"""
    from core.config_manager import ConfigManager
    cfg = ConfigManager(project_with_daily_signin, auto_load=True)
    panel = TaskPanel(cfg)
    qtbot.addWidget(panel)
    ids = panel.get_selected_task_ids()
    assert "daily_signin" in ids
    panel.close()


def test_phase5_task_panel_set_selected_changes_state(qtbot, project_with_daily_signin):
    """set_selected 改勾选状态。"""
    from core.config_manager import ConfigManager
    cfg = ConfigManager(project_with_daily_signin, auto_load=True)
    panel = TaskPanel(cfg)
    qtbot.addWidget(panel)
    panel.set_selected([])
    assert panel.get_selected_task_ids() == []
    panel.set_selected(["daily_signin"])
    assert "daily_signin" in panel.get_selected_task_ids()
    panel.close()


def test_phase5_task_panel_select_all_deselect_all(qtbot, project_with_daily_signin):
    """全选 / 全不选。"""
    from core.config_manager import ConfigManager
    cfg = ConfigManager(project_with_daily_signin, auto_load=True)
    panel = TaskPanel(cfg)
    qtbot.addWidget(panel)
    panel._set_all(QtCore.Qt.Checked)
    assert len(panel.get_selected_task_ids()) >= 1
    panel._set_all(QtCore.Qt.Unchecked)
    assert panel.get_selected_task_ids() == []
    panel.close()


# ============================================================
# ResourceStatusPanel
# ============================================================


def test_phase5_resource_panel_shows_missing_when_no_templates(qtbot, project_with_daily_signin):
    """模板目录存在但空 → 显示「缺失」。"""
    panel = ResourceStatusPanel(project_with_daily_signin, "resources/templates")
    qtbot.addWidget(panel)
    counts = {"HOME": 0, "POPUP": 0, "LOADING": 0}
    panel._update_ui(counts)
    for state_value, (_, status_lbl) in panel._rows.items():
        assert "缺失" in status_lbl.text()
    panel.close()


def test_phase5_resource_panel_shows_loaded_when_templates_exist(
    qtbot, templates_with_some: Path,
):
    """HOME 有 1 个模板 → 显示「已加载 (1 张)」。"""
    panel = ResourceStatusPanel(templates_with_some, "resources/templates")
    qtbot.addWidget(panel)
    # refresh 已经自动跑过
    home_status = panel._rows["HOME"][1].text()
    assert "已加载" in home_status
    assert "1" in home_status
    panel.close()


# ============================================================
# SchemeManager 端到端
# ============================================================


def test_phase5_scheme_workflow_through_main_window(
    qtbot, project_with_daily_signin,
):
    """选方案 → 同步 task_ids 到 TaskPanel。"""
    win = MainWindow(project_with_daily_signin)
    qtbot.addWidget(win)
    # 模拟选 daily
    win._on_scheme_selected("daily")
    assert "daily_signin" in win._task_panel.get_selected_task_ids()
    win.close()


# ============================================================
# ConfigDialog 端到端
# ============================================================


def test_phase5_config_dialog_round_trip(qtbot, project_with_daily_signin):
    """打开 ConfigDialog → 改值 → 关 → cfg 持久化。"""
    from core.config_manager import ConfigManager
    cfg = ConfigManager(project_with_daily_signin, auto_load=True)
    dlg = ConfigDialog(cfg)
    qtbot.addWidget(dlg)
    dlg._spin_retry_max.setValue(10)
    dlg._on_accept()
    # 新建 cfg(模拟 reload)
    cfg2 = ConfigManager(project_with_daily_signin, auto_load=True)
    assert cfg2.app.retry.max_attempts == 10


# ============================================================
# LogPanel
# ============================================================


def test_phase5_log_panel_receives_qt_signal(qtbot):
    """LogPanel.on_log_record 收到信号 → 文本框出现内容。"""
    panel = LogPanel()
    qtbot.addWidget(panel)
    panel.on_log_record("2026-06-24 12:00:00 | INFO    | test:1 | hello world\n")
    # 文本框里应该有 hello world
    text = panel._text.toPlainText()
    assert "hello world" in text
    panel.close()


def test_phase5_log_panel_filters_by_level(qtbot):
    """level=ERROR 时 INFO 不显示(P1-BUG-01: 走 level_changed 信号而非解析字符串)。"""
    panel = LogPanel()
    qtbot.addWidget(panel)
    panel._level_combo.setCurrentText("ERROR")
    # 模拟 QtLogHandler 信号序列(level_changed 先于 log_record)
    panel.on_level_changed("INFO")
    panel.on_log_record("2026-06-24 12:00:00 | INFO    | test:1 | info msg\n")
    panel.on_level_changed("ERROR")
    panel.on_log_record("2026-06-24 12:00:00 | ERROR   | test:2 | error msg\n")
    text = panel._text.toPlainText()
    assert "info msg" not in text
    assert "error msg" in text
    panel.close()


def test_phase5_log_panel_does_not_parse_level_from_message(qtbot):
    """P1-BUG-01 验证:on_log_record 单独调用(无 on_level_changed)不解析字符串,
    默认按 ``_last_level`` 过滤;fallback 是 INFO。
    """
    panel = LogPanel()
    qtbot.addWidget(panel)
    panel._level_combo.setCurrentText("ERROR")
    # 不调 on_level_changed,只用 on_log_record
    panel.on_log_record("2026-06-24 12:00:00 | ERROR   | test:1 | should_be_hidden\n")
    text = panel._text.toPlainText()
    # 因为 _last_level 默认 INFO,ERROR 过滤会让它隐藏
    assert "should_be_hidden" not in text
    panel.close()


def test_phase5_log_panel_clear_empties_text(qtbot):
    """clear 清空文本。"""
    panel = LogPanel()
    qtbot.addWidget(panel)
    panel.on_log_record("2026-06-24 12:00:00 | INFO    | test:1 | x\n")
    panel.clear()
    assert panel._text.toPlainText() == ""
    panel.close()


# ============================================================
# QtLogHandler 端到端
# ============================================================


def test_phase5_qt_log_handler_emits_signal(qtbot):
    """QtLogHandler 安装后,logger.info 触发 signal。"""
    from loguru import logger
    handler = QtLogHandler()
    sink_id = install(handler)
    try:
        received = []
        handler.log_record.connect(lambda m: received.append(m))
        logger.info("test_message_p5")
        # loguru 同步派发(我们用 enqueue=False)
        assert any("test_message_p5" in m for m in received)
    finally:
        uninstall(handler, sink_id)


# ============================================================
# ControlPanel
# ============================================================


def test_phase5_control_panel_set_running_disables_start(qtbot):
    """set_running(True) → Start 按钮 disabled。"""
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_running(True)
    assert not panel._btn_start.isEnabled()
    assert panel._btn_stop.isEnabled()
    panel.set_running(False)
    assert panel._btn_start.isEnabled()
    assert not panel._btn_stop.isEnabled()
    panel.close()


def test_phase5_control_panel_start_emits_with_task_ids(qtbot):
    """点 Start 按钮 → 发出 start_requested(task_ids) 信号。"""
    panel = ControlPanel()
    qtbot.addWidget(panel)
    received = []
    panel.start_requested.connect(lambda ids: received.append(ids))
    panel.set_selected_task_ids(["task_a", "task_b"])
    panel._btn_start.click()
    assert received == [["task_a", "task_b"]]
    panel.close()


def test_phase5_control_panel_schemes_dropdown(qtbot):
    """方案下拉填充 + 当前方案 getter。"""
    panel = ControlPanel()
    qtbot.addWidget(panel)
    panel.set_available_schemes(["alpha", "beta", "gamma"])
    assert panel._scheme_combo.count() == 3
    panel.set_current_scheme("beta")
    assert panel.get_current_scheme() == "beta"
    panel.close()


# ============================================================
# RunWorker(用 MagicMock engine)
# ============================================================


def test_phase5_run_worker_emits_finished(qtbot, project_with_daily_signin):
    """RunWorker 跑完发出 finished(RunReport) 信号。"""
    from datetime import datetime
    from core.scheduler import RunReport
    from core.base_task import TaskResult, TaskStatus
    from tasks.task_engine import TaskEngine

    engine = MagicMock(spec=TaskEngine)
    engine.run_all.return_value = RunReport(
        started_at=datetime.now(),
        finished_at=datetime.now(),
        task_results=[
            TaskResult(
                task_id="daily_signin",
                status=TaskStatus.SUCCESS,
                message="ok",
            ),
        ],
    )
    worker = RunWorker(engine, ["daily_signin"])
    finished = []
    worker.finished.connect(lambda r: finished.append(r))
    # 调 run(同线程,直接执行)
    worker.run()
    assert len(finished) == 1
    assert finished[0].total_count == 1


def test_phase5_run_worker_emits_error_on_exception(qtbot):
    """engine.run_all 抛异常 → error signal。"""
    from tasks.task_engine import TaskEngine
    engine = MagicMock(spec=TaskEngine)
    engine.run_all.side_effect = RuntimeError("engine failed")
    worker = RunWorker(engine, ["x"])
    errs = []
    worker.error.connect(lambda m: errs.append(m))
    worker.run()
    assert len(errs) == 1
    assert "RuntimeError" in errs[0]
    assert "engine failed" in errs[0]


# ============================================================
# 完整 E2E 流程
# ============================================================


def test_phase5_full_flow_gui_start_to_finish(
    qtbot, project_with_daily_signin, monkeypatch,
):
    """完整流程:
    GUI 启动 → 加载 daily 方案 → 启动 worker → 接收日志 → 任务结束。

    用 MagicMock 替换 TaskEngine.run_all 让它快速返回。
    """
    from datetime import datetime
    from core.scheduler import RunReport
    from core.base_task import TaskResult, TaskStatus
    from tasks.task_engine import TaskEngine

    win = MainWindow(project_with_daily_signin)
    qtbot.addWidget(win)
    # mock engine.run_all → 立即返 RunReport
    fake_report = RunReport(
        started_at=datetime.now(),
        finished_at=datetime.now(),
        task_results=[
            TaskResult(
                task_id="daily_signin",
                status=TaskStatus.SUCCESS,
                message="e2e ok",
            ),
        ],
    )
    win._engine.run_all = MagicMock(return_value=fake_report)
    # 触发 Start(daily 方案已选)
    win._on_start(["daily_signin"])
    # 等 thread 完成(注意:完成后 _on_worker_finished 会把 self._thread = None)
    thread_ref = win._thread
    if thread_ref is not None:
        qtbot.waitUntil(lambda: not thread_ref.isRunning(), timeout=5000)
    # engine.run_all 被调
    win._engine.run_all.assert_called_once_with(["daily_signin"])
    # 状态:已停(start button 重新 enabled)
    assert win._control_panel._btn_start.isEnabled()
    win.close()


# ============================================================
# main.py --gui 命令
# ============================================================


def test_phase5_main_py_gui_arg_defined(project_with_daily_signin):
    """main.py argparse 含 --gui 选项。"""
    from main import parse_args
    args = parse_args(["--gui"])
    assert args.gui is True
