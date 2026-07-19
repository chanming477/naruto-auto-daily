"""test_main.py — main.py CLI 端到端 (V1 2026-07-19)。

不连真机, 只验 CLI 参数解析 + 退出码 + 关键 stdout。
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from main import main, parse_args


# ============================================================
# parse_args
# ============================================================


def test_parse_args_defaults():
    """无参数时, 默认启 GUI 路径(no_action=True → main 走 _launch_mfaavalonia_gui)。"""
    args = parse_args([])
    assert args.gui is False
    assert args.check is False
    assert args.list_tasks is False
    assert args.init_config is False
    assert args.version is False
    assert args.debug is False
    assert args.quiet is False


def test_parse_args_version():
    args = parse_args(["--version"])
    assert args.version is True


def test_parse_args_check():
    args = parse_args(["--check"])
    assert args.check is True


def test_parse_args_combined():
    args = parse_args(["--check", "--debug"])
    assert args.check is True
    assert args.debug is True
    assert args.quiet is False


def test_parse_args_deleted_commands_rejected():
    """OPT-2 删的命令应 parse 失败 (--run-task / --daily-all / --capture-test / --smoke-test)。"""
    for deleted in ["--run-task", "--daily-all", "--capture-test", "--smoke-test",
                    "--list-windows", "--activate-window", "--phase2", "--phase3"]:
        with pytest.raises(SystemExit):
            parse_args([deleted])


# ============================================================
# main()
# ============================================================


def test_main_version(capsys: pytest.CaptureFixture):
    rc = main(["--version"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "naruto-auto-daily" in out
    # version 格式: "naruto-auto-daily 0.7.0"
    assert "0.7.0" in out


def test_main_help(capsys: pytest.CaptureFixture):
    """--help argparse 退出 (SystemExit 0), 输出 usage + 命令列表。"""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out.lower() or "naruto-auto-daily" in out
    # 6 个保留命令都应在 help 里
    for cmd in ["--gui", "--init-config", "--list-tasks", "--check",
                "--debug", "--quiet", "--version"]:
        assert cmd in out, f"--help 输出缺 {cmd}"


def test_main_init_config(tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch):
    """--init-config 在 tmp_path 写 2 份 YAML (app_config.yaml + task_registry.yaml)。

    2026-07-19 OPT-1+OPT-2 后: 删 device_config.yaml, 只剩 2 份。
    """
    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("main.get_user_data_dir", lambda: tmp_path)
    rc = main(["--init-config"])
    out = capsys.readouterr().out
    assert rc == 0
    assert (tmp_path / "config" / "app_config.yaml").exists()
    assert (tmp_path / "config" / "task_registry.yaml").exists()
    # 旧 device_config.yaml 不再自动生成
    assert not (tmp_path / "config" / "device_config.yaml").exists()
    # 旧 schedule.json 不再自动生成
    assert not (tmp_path / "config" / "schedule.json").exists()
    assert "已生成" in out


def test_main_init_config_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch):
    """第二次跑 --init-config 应跳过(所有文件已存在)。"""
    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("main.get_user_data_dir", lambda: tmp_path)
    main(["--init-config"])  # 第一次创建
    capsys.readouterr()  # 清空 stdout
    rc = main(["--init-config"])  # 第二次
    out = capsys.readouterr().out
    assert rc == 0
    assert "已存在" in out or "未做任何修改" in out


def test_main_list_tasks(capsys: pytest.CaptureFixture):
    """--list-tasks 打印 TASK_MAPPING + 资源路径验证。"""
    rc = main(["--list-tasks"])
    out = capsys.readouterr().out
    assert rc == 0
    # 关键 24 个 entry 至少出现几个
    for tid in ["mail", "activity", "liveness_award", "headhunt", "get_copper",
                "survival_challenge", "naruto_club", "leaderboard"]:
        assert tid in out, f"--list-tasks 缺 {tid}"
    # 资源路径验证
    assert "[OK] resource path valid" in out or "resource path" in out


def test_main_check(tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch):
    """--check 4 项检查全过 (Pydantic / 模板目录 / 任务注册表 / ADB WARN)。"""
    # 重定向 PROJECT_ROOT 到 tmp_path (--check 读 config/task_registry.yaml)
    monkeypatch.setattr("main.PROJECT_ROOT", tmp_path)
    # 预填 task_registry.yaml, 让 [3/4] 检查过
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n  mail:\n    enabled: true\n    display_order: 2\n    category: daily\n",
        encoding="utf-8",
    )
    rc = main(["--check"])
    out = capsys.readouterr().out
    # ADB 找不到会 WARN, 不算 FAIL, exit code 应该是 0
    assert rc == 0, f"--check 退出码 {rc}, 输出:\n{out}"
    assert "PASS" in out
    # 4 项都跑了
    assert "[1/4]" in out
    assert "[2/4]" in out
    assert "[3/4]" in out
    assert "[4/4]" in out
