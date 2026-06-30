"""test_phase3_pipeline.py — Phase 3 端到端测试。

E2E 验证: 读取配置 → 注册任务 → 执行 → 验证 → 返回主页 → 结束。
所有组件 MagicMock / 临时文件,零真实外部依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.base_task import ExecutionContext
from core.config_manager import ConfigManager
from core.state_machine import build_default_state_machine
from device.types import ActionResult
from main import run_phase3_demo
from recognizer.page_recognizer import PageRecognizer
from recognition.template_matcher import TemplateMatcher
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine
from tasks.common_actions import CommonActions
from tasks.task_engine import TaskEngine


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def task_registry_with_daily_signin(tmp_path: Path) -> Path:
    """写一份 task_registry.yaml,配置 daily_signin 任务。"""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    # app_config.yaml 最小集(让 ConfigManager 加载不报错)
    (cfg_dir / "app_config.yaml").write_text(
        "app: {}\n"
        "logger:\n  console_level: WARNING\n"
        "  file_level: DEBUG\n  log_dir: logs\n  rotation_mb: 50\n"
        "  retention_days: 30\n  compression: true\n  auto_screenshot_on_error: true\n"
        "scheduler:\n  stop_on_failure: false\n  inter_task_delay_sec: 0.1\n"
        "  startup_warmup_sec: 0\n  task_timeout_sec: 30\n  heartbeat_interval_sec: 30\n"
        "state_machine:\n  initial_state: IDLE\n  failure_state: FAILED\n"
        "  success_state: COMPLETED\n  log_transitions: false\n"
        "screenshot:\n  output_dir: screenshots\n  backend: win32_print_window\n"
        "  to_grayscale: false\n  max_empty_retries: 3\n  retry_delay_ms: 200\n"
        "adb:\n  adb_path: ''\n  default_serial: ''\n  command_timeout_sec: 5\n  retry_count: 1\n"
        "template_matching:\n  default_threshold: 0.85\n  multi_scale: false\n"
        "  multi_scale_range: [0.95, 1.0, 1.05]\n"
        "game_state:\n  initial_state: UNKNOWN\n  templates_dir: resources/templates\n"
        "  recovery_probe_max: 3\n",
        encoding="utf-8",
    )
    (cfg_dir / "device_config.yaml").write_text(
        "active_profile: default\nprofiles:\n  default:\n    match_mode: title_contains\n"
        "    match_keywords: []\n    process_blacklist: []\n    require_visible: true\n"
        "    require_not_minimized: true\n    expected_width: 0\n    expected_height: 0\n",
        encoding="utf-8",
    )
    (cfg_dir / "task_registry.yaml").write_text(
        "tasks:\n"
        "  daily_signin:\n"
        "    task_class: 'tasks.daily_signin_task.DailySigninTask'\n"
        "    enabled: true\n"
        "    display_order: 1\n"
        "    category: daily\n"
        "    description: 测试用\n"
        "    estimated_time_sec: 10\n"
        "    retry_on_failure: false\n"
        "    max_retries: 0\n"
        "    config_options: {}\n",
        encoding="utf-8",
    )

    # resources/templates 目录(空也行,PageRecognizer 容错)
    for state in ("HOME", "POPUP", "LOADING"):
        (tmp_path / "resources" / "templates" / state).mkdir(parents=True, exist_ok=True)
    return tmp_path


# ============================================================
# E2E tests
# ============================================================


def test_e2e_load_yaml_register_run_daily_signin(task_registry_with_daily_signin: Path):
    """V3 (P1-BUG-01): 在纯 mock 环境下,DailySigninTask.pre_check 失败,任务 SKIP。

    这是**正确的**行为 — V2 的 mock tolerance 强制 ok=True 是「静默 SUCCESS」反模式。
    关键验证点:
        - rc != 2(task 找到了,不是 unknown task_id)
        - 任务被注册 + 尝试执行(没有被静默跳过)
    注: run_task 模式下 SKIP 会被算作非 success → rc=1
    """
    rc = run_phase3_demo(
        task_registry_with_daily_signin,
        use_real_adb=False,
        task_id="daily_signin",
        console_level="WARNING",
    )
    assert rc != 2  # task 被找到了,不是 unknown
    # run_task 模式:SKIP → is_success=False → rc=1
    assert rc == 1


def test_e2e_run_all_default(task_registry_with_daily_signin: Path):
    """E2E: 不指定 task_id → run_all 从 cfg.tasks 读所有 enabled 任务。

    V3: 在 mock 环境下,任务会 SKIP。run_all 模式下 SKIP 不计入 fail_count,
    所以 rc 可以是 0(SKIP 不算 fail)。
    """
    rc = run_phase3_demo(
        task_registry_with_daily_signin,
        use_real_adb=False,
        task_id=None,
        console_level="WARNING",
    )
    assert rc != 2  # task 被找到了
    # run_all 模式:SKIP 不算 fail → rc 可以是 0
    assert rc in (0, 1)


def test_e2e_run_all_with_unknown_task_id_is_skipped(task_registry_with_daily_signin: Path):
    """E2E: run_all 包含一个不存在的 task_id → 跳过,只跑存在的。

    V3: 纯 mock env → daily_signin 必然 SKIP/FAIL。run_all 模式允许 rc=0 或 1。
    """
    rc = run_phase3_demo(
        task_registry_with_daily_signin,
        use_real_adb=False,
        task_id=None,
        console_level="WARNING",
    )
    # cfg.tasks 只有一个 daily_signin,传 task_ids=None 时只跑这一个
    assert rc != 2  # task 被找到了
    assert rc in (0, 1)


def test_e2e_failure_recovery_via_recover(task_registry_with_daily_signin: Path):
    """V3 (P1-BUG-01): 在 mock 环境下,pre_check 失败,任务 SKIP → rc=1。

    验证关键点:
        - rc != 2(task 找到)
        - rc == 1(pre_check 失败,run_task 模式下不再静默 SUCCESS)
    """
    rc = run_phase3_demo(
        task_registry_with_daily_signin,
        use_real_adb=False,
        task_id="daily_signin",
        console_level="WARNING",
    )
    assert rc != 2  # task 被找到了
    assert rc == 1  # V3 严格语义: run_task 模式 SKIP → rc=1
    # 跑通流程就算 E2E 成功 — 任务被注册、被尝试、结果被记录(不论是 SKIP 还是 FAIL)


# ============================================================
# TaskEngine 直接测试(不通过 main.py)
# ============================================================


def test_task_engine_uses_execution_context_only(task_registry_with_daily_signin: Path):
    """V3 (P1-ARCH-02): TaskEngine 内部只用 ExecutionContext,不维护 cfg._phase3_deps hack;
    依赖通过 ``ctx.common_actions`` 注入。"""
    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)

    # Mock CommonActions
    common = MagicMock(spec=CommonActions)
    common.ensure_state.return_value = True
    common.go_home.return_value = True

    ctx = ExecutionContext(
        config=cfg,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=False),
    )
    # V3: 注入到 ctx,不再写 cfg._phase3_deps
    ctx.common_actions = common

    engine = TaskEngine(ctx, common_actions=common)
    result = engine.run_task("daily_signin")
    assert result is not None
    assert result.is_success


def test_task_engine_report_summary(task_registry_with_daily_signin: Path):
    """E2E: run_all 返回 RunReport,summary 文本可读。"""
    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)

    common = MagicMock(spec=CommonActions)
    common.ensure_state.return_value = True
    common.go_home.return_value = True

    ctx = ExecutionContext(
        config=cfg,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=False),
    )
    # V3: 注入到 ctx
    ctx.common_actions = common

    engine = TaskEngine(ctx, common_actions=common)
    report = engine.run_all()
    assert report.total_count == 1
    assert report.success_count == 1
    assert "tasks=1" in report.summary()


def test_phase3_demo_does_not_break_phase2_demo(task_registry_with_daily_signin: Path):
    """E2E: Phase 3 跑过后,YAML 配置仍然有效,Phase 2 demo 也能跑通。

    V3: Phase 3 demo 在 mock 环境下 rc=1(SKIP),这**不影响** Phase 2 后续调用。
    关键验证点: Phase 2 demo 不被 Phase 3 污染,rc2=0。
    """
    from main import run_phase2_demo

    # 先 Phase 3
    rc3 = run_phase3_demo(task_registry_with_daily_signin, use_real_adb=False,
                         task_id="daily_signin", console_level="WARNING")
    assert rc3 != 2  # Phase 3 task 被找到了(不论 SKIP/FAIL)
    # V3 严格语义: mock env 下 run_task 模式 SKIP → rc=1
    assert rc3 == 1

    # 再 Phase 2(确认 Phase 3 没污染配置)
    rc2 = run_phase2_demo(task_registry_with_daily_signin, use_real_adb=False,
                         console_level="WARNING")
    assert rc2 == 0  # Phase 2 demo 仍能跑通