"""test_config_manager.py — 配置管理关键行为。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config_manager import ConfigManager, ConfigurationError


def test_init_generates_defaults(tmp_path: Path):
    cfg = ConfigManager(tmp_path, auto_load=True)
    assert (tmp_path / "config" / "app_config.yaml").exists()
    assert (tmp_path / "config" / "device_config.yaml").exists()
    assert (tmp_path / "config" / "task_registry.yaml").exists()
    assert cfg.app.app.name == "naruto-auto-daily"


def test_partial_yaml_gets_defaults(tmp_path: Path):
    (tmp_path / "config").mkdir()
    # 只写一部分字段；Pydantic 应该用默认值补齐缺失项
    (tmp_path / "config" / "app_config.yaml").write_text(
        "app:\n  name: 'partial'\n  debug: true\n", encoding="utf-8"
    )
    (tmp_path / "config" / "device_config.yaml").write_text(
        "active_profile: 'default'\nprofiles:\n  default: {}\n", encoding="utf-8"
    )
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks: {}\nschedule_order: []\n", encoding="utf-8"
    )
    cfg = ConfigManager(tmp_path, auto_load=True)
    assert cfg.app.app.name == "partial"
    assert cfg.app.app.debug is True
    # 缺失字段补齐
    assert cfg.app.logger.console_level == "INFO"
    assert cfg.app.scheduler.task_timeout_sec == 300


def test_invalid_yaml_is_backed_up_and_recovered(tmp_path: Path):
    """P1-STABLE-04: YAML 损坏 → backup + 写默认值，不抛 ConfigurationError。"""
    (tmp_path / "config").mkdir()
    bad = tmp_path / "config" / "app_config.yaml"
    bad.write_text("app:\n  name: 'broken'\n  : invalid yaml here :\n", encoding="utf-8")
    # 同目录补齐 device + tasks 防止 reload 时其它 yaml 也失败
    (tmp_path / "config" / "device_config.yaml").write_text(
        "active_profile: 'default'\nprofiles:\n  default: {}\n", encoding="utf-8"
    )
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks: {}\nschedule_order: []\n", encoding="utf-8"
    )

    cfg = ConfigManager(tmp_path, auto_load=True)
    # 加载应成功（fallback 到默认值）
    assert cfg.app.app.name == "naruto-auto-daily"
    # 备份文件应存在
    backups = list((tmp_path / "config").glob("app_config.*.bak"))
    assert backups, "expected at least one .bak file"
    # 主文件应被改写成合法 YAML
    assert "name:" in bad.read_text(encoding="utf-8")


def test_unknown_fields_ignored(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app_config.yaml").write_text(
        "app:\n  name: 'x'\n  unknown_top_field: 999\n", encoding="utf-8"
    )
    (tmp_path / "config" / "device_config.yaml").write_text(
        "active_profile: 'default'\nprofiles:\n  default: {}\n", encoding="utf-8"
    )
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks: {}\nschedule_order: []\n", encoding="utf-8"
    )
    cfg = ConfigManager(tmp_path, auto_load=True)
    assert cfg.app.app.name == "x"


def test_active_profile_lookup(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app_config.yaml").write_text(
        "app: {}\nlogger: {}\nscheduler: {}\nstate_machine: {}\nscreenshot: {}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "device_config.yaml").write_text(
        "active_profile: 'mumu'\n"
        "profiles:\n"
        "  mumu:\n"
        "    match_mode: 'title_contains'\n"
        "    match_keywords: ['MuMu']\n"
        "    process_blacklist: []\n"
        "    require_visible: true\n"
        "    require_not_minimized: true\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks: {}\nschedule_order: []\n", encoding="utf-8"
    )
    cfg = ConfigManager(tmp_path, auto_load=True)
    profile = cfg.device.active()
    assert profile.match_keywords == ["MuMu"]
    assert cfg.device.active_profile == "mumu"