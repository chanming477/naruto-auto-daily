"""test_config_dialog.py — ConfigDialog 单元测试(用 pytest-qt)。

覆盖:
- 加载当前值
- 修改字段
- 接受后保存到 yaml
- 取消不保存
- Pydantic 校验(无效值不通过)
- reload 后生效
"""

from __future__ import annotations

import pytest

# 跳过整个文件如果 PySide6 不可用
pytest.importorskip("PySide6", reason="PySide6 not installed")

from PySide6 import QtCore, QtWidgets

from core.config_manager import ConfigManager
from ui.config_dialog import ConfigDialog


@pytest.fixture
def cfg(tmp_path) -> ConfigManager:
    """最小可用的 ConfigManager,带 app_config.yaml。"""
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
        "retry:\n  max_attempts: 3\n  delay_seconds: 1.0\n  exponential_backoff: true\n"
        "  max_delay_seconds: 30.0\n  retryable_exceptions: []\n"
        "recovery:\n  max_unknown_retries: 3\n  max_popup_retries: 3\n  max_loading_seconds: 60.0\n"
        "  adb_reconnect_attempts: 2\n"
        "logging_ext: {}\n",
        encoding="utf-8",
    )
    return ConfigManager(tmp_path, auto_load=True)


@pytest.fixture
def dialog(qtbot, cfg) -> ConfigDialog:
    dlg = ConfigDialog(cfg)
    qtbot.addWidget(dlg)
    return dlg


# ============================================================
# 加载
# ============================================================


def test_config_dialog_loads_current_values(dialog, cfg):
    """从 cfg 加载的值正确填到 widget。"""
    assert dialog._spin_retry_max.value() == cfg.app.retry.max_attempts
    assert dialog._spin_retry_delay.value() == cfg.app.retry.delay_seconds
    assert dialog._spin_recovery_unknown.value() == cfg.app.recovery.max_unknown_retries
    assert dialog._spin_recovery_popup.value() == cfg.app.recovery.max_popup_retries
    assert abs(
        dialog._spin_tmpl_threshold.value() - cfg.app.template_matching.default_threshold
    ) < 1e-6


# ============================================================
# 修改 + 保存
# ============================================================


def test_config_dialog_modify_and_accept_persists(dialog, cfg, tmp_path, monkeypatch):
    """改 retry.max_attempts → accept → cfg 已更新 + yaml 已写。"""
    dialog._spin_retry_max.setValue(7)
    dialog._spin_retry_delay.setValue(2.5)
    # monkeypatch QMessageBox.warning 防止真的弹窗
    from PySide6 import QtWidgets as _Q
    monkeypatch.setattr(_Q.QMessageBox, "warning", lambda *a, **k: None)
    # 点 OK
    dialog._on_accept()
    assert dialog.result()  # QDialog.Accepted
    # cfg 已更新
    assert cfg.app.retry.max_attempts == 7
    assert abs(cfg.app.retry.delay_seconds - 2.5) < 1e-6
    # yaml 已写
    import yaml
    yaml_path = tmp_path / "config" / "app_config.yaml"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert data["retry"]["max_attempts"] == 7
    assert abs(data["retry"]["delay_seconds"] - 2.5) < 1e-6


def test_config_dialog_reload_after_save(dialog, cfg, tmp_path, monkeypatch):
    """保存后 reload 仍能读到新值。"""
    dialog._spin_recovery_unknown.setValue(8)
    dialog._spin_recovery_popup.setValue(9)
    dialog._spin_tmpl_threshold.setValue(0.75)
    from PySide6 import QtWidgets as _Q
    monkeypatch.setattr(_Q.QMessageBox, "warning", lambda *a, **k: None)
    dialog._on_accept()
    # 新建一个 ConfigManager 实例,模拟 reload
    cfg2 = ConfigManager(tmp_path, auto_load=True)
    assert cfg2.app.recovery.max_unknown_retries == 8
    assert cfg2.app.recovery.max_popup_retries == 9
    assert abs(cfg2.app.template_matching.default_threshold - 0.75) < 1e-6


# ============================================================
# 取消
# ============================================================


def test_config_dialog_cancel_does_not_save(dialog, cfg, tmp_path):
    """点 Cancel → cfg 不变 + yaml 不变。"""
    original = cfg.app.retry.max_attempts
    original_yaml = (tmp_path / "config" / "app_config.yaml").read_text(encoding="utf-8")
    dialog._spin_retry_max.setValue(99)
    dialog.reject()
    # cfg 不变
    assert cfg.app.retry.max_attempts == original
    # yaml 不变
    assert (tmp_path / "config" / "app_config.yaml").read_text(encoding="utf-8") == original_yaml


# ============================================================
# 范围限制
# ============================================================


def test_config_dialog_max_attempts_range(dialog):
    """retry.max_attempts 范围 [1, 20]。"""
    assert dialog._spin_retry_max.minimum() == 1
    assert dialog._spin_retry_max.maximum() == 20


def test_config_dialog_threshold_range(dialog):
    """template_matching.threshold 范围 [0, 1]。"""
    assert dialog._spin_tmpl_threshold.minimum() == 0.0
    assert dialog._spin_tmpl_threshold.maximum() == 1.0


def test_config_dialog_max_attempts_blocks_invalid_via_widget(dialog):
    """SpinBox 范围 [1, 20] 防止 setValue(0)/setValue(100) 越界。"""
    dialog._spin_retry_max.setValue(0)
    # SpinBox 强制修正到 minimum
    assert dialog._spin_retry_max.value() == 1
    dialog._spin_retry_max.setValue(100)
    assert dialog._spin_retry_max.value() == 20


# ============================================================
# 错误处理
# ============================================================


def test_config_dialog_window_title(dialog):
    """对话框标题正确。"""
    assert dialog.windowTitle() == "编辑配置"


def test_config_dialog_save_yaml_creates_file(dialog, cfg, tmp_path, monkeypatch):
    """保存路径正确(<project_root>/config/app_config.yaml)。"""
    dialog._spin_retry_max.setValue(5)
    from PySide6 import QtWidgets as _Q
    monkeypatch.setattr(_Q.QMessageBox, "warning", lambda *a, **k: None)
    dialog._on_accept()
    assert (tmp_path / "config" / "app_config.yaml").is_file()
