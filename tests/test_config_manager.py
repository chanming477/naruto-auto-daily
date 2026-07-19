"""test_config_manager.py — 配置管理关键行为。

2026-07-19 OPT: config/device_config.yaml + config/schedule.json 已删 (dead,
对应 WindowManager / --daily-all 在 OPT-1+OPT-2 删)。本测试改成只测
app_config.yaml 的 Pydantic 行为。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config_manager import ConfigManager, ConfigurationError


def test_init_generates_defaults(tmp_path: Path):
    cfg = ConfigManager(tmp_path, auto_load=True)
    assert (tmp_path / "config" / "app_config.yaml").exists()
    assert cfg.app.app.name == "naruto-auto-daily"


def test_partial_yaml_gets_defaults(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app_config.yaml").write_text(
        "app:\n  name: 'partial'\n  debug: true\n", encoding="utf-8"
    )
    cfg = ConfigManager(tmp_path, auto_load=True)
    assert cfg.app.app.name == "partial"
    assert cfg.app.app.debug is True
    # 缺失字段补齐
    assert cfg.app.logger.console_level == "INFO"


def test_invalid_yaml_is_backed_up_and_recovered(tmp_path: Path):
    """P1-STABLE-04: YAML 损坏 → backup + 写默认值，不抛 ConfigurationError。"""
    (tmp_path / "config").mkdir()
    bad = tmp_path / "config" / "app_config.yaml"
    bad.write_text("app:\n  name: 'broken'\n  : invalid yaml here :\n", encoding="utf-8")

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
    cfg = ConfigManager(tmp_path, auto_load=True)
    assert cfg.app.app.name == "x"
