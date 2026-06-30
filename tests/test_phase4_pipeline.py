"""test_phase4_pipeline.py — Phase 4 端到端测试。

验证 E2E 流程:
    任务执行 → 内部 ADB 操作抛异常 → RetryManager 重试 → 成功 → 继续
    任务执行 → GameState UNKNOWN → RecoveryManager.recover_unknown → 切回 HOME
    任务执行 → 全程 RunContext 包裹 → __exit__ 打 elapsed_ms 日志

所有依赖 MagicMock / 临时目录,零真实 ADB / 模拟器 / 游戏资源。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.base_task import ExecutionContext
from core.config_manager import ConfigManager
from core.state_machine import build_default_state_machine
from device.types import ActionResult
from logging_ext import RunContext
from main import run_phase4_demo
from recovery.recovery_manager import RecoveryManager
from recovery.retry_manager import RetryManager, RetryPolicy
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine
from tasks.common_actions import CommonActions


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def task_registry_with_daily_signin(tmp_path: Path) -> Path:
    """最小可用 task_registry.yaml,daily_signin 任务。"""
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
        "  max_delay_seconds: 1.0\n  retryable_exceptions: ['ADBTimeoutError', 'ADBCommandError']\n"
        "recovery:\n  max_unknown_retries: 2\n  max_popup_retries: 2\n"
        "  max_loading_seconds: 5.0\n  adb_reconnect_attempts: 2\n"
        "logging_ext:\n  capture_transitions: true\n  log_state_changes: true\n",
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
        "    enabled: true\n    display_order: 1\n    category: daily\n"
        "    description: 'Phase 4 E2E'\n    estimated_time_sec: 5\n"
        "    retry_on_failure: false\n    max_retries: 0\n    config_options: {}\n",
        encoding="utf-8",
    )
    for state in ("HOME", "POPUP", "LOADING"):
        (tmp_path / "resources" / "templates" / state).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def fast_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        max_attempts=3,
        delay_seconds=0.0,
        exponential_backoff=False,
        max_delay_seconds=0.0,
        retryable_exceptions=("ADBTimeoutError", "ADBCommandError", "RuntimeError"),
    )


# ============================================================
# E2E 1: 任务执行 → 内部 ADB 抛异常 → RetryManager 重试 → 成功
# ============================================================


def test_e2e_adb_transient_error_recovered_by_retry_manager(
    task_registry_with_daily_signin, fast_retry_policy, monkeypatch
):
    """任务执行:adb.screenshot 第 1 次抛 ADBTimeoutError,RetryManager 重试,最终成功。

    验证:
        - 任务最终 SUCCESS(没有让 TaskResult 失败)
        - RetryManager 调了 2 次 adb.screenshot(失败 + 成功)
        - 整个流程有 RunContext 包裹(elapsed_ms 字段)
    """
    from device.adb_client import ADBTimeoutError
    monkeypatch.setattr("time.sleep", lambda _x: None)

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
    ctx.common_actions = common

    # adb mock:第 1 次抛 ADBTimeoutError,第 2 次成功
    success_action = ActionResult(
        True, "screenshot ok", None, payload=np.zeros((10, 10, 3), dtype=np.uint8),
    )
    adb = MagicMock()
    adb.screenshot.side_effect = [ADBTimeoutError("transient"), success_action]

    retry_mgr = RetryManager(policy=fast_retry_policy)

    # 模拟任务执行 + RetryManager
    with RunContext(task_id="e2e_adb_retry", state_before="HOME") as rc:
        # 第一次调用(应该失败)
        # 第二次调用(RetryManager 重试,成功)
        result = retry_mgr.execute_adb_action(adb, "screenshot")
        rc.state_after = "HOME"  # 后续状态

    assert result is success_action
    assert result.success is True
    assert adb.screenshot.call_count == 2
    assert rc.elapsed_ms >= 0


# ============================================================
# E2E 2: GameState UNKNOWN → RecoveryManager.recover_unknown → 切回 HOME
# ============================================================


def test_e2e_unknown_state_recovered_via_recovery_manager(task_registry_with_daily_signin):
    """GameState = UNKNOWN → recover(recovery_manager) → 切到 HOME(成功路径)。"""
    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)

    # 装配一个 mock 环境,让 recover_unknown 内部 observe 返 HOME
    common = MagicMock(spec=CommonActions)
    common.observe.return_value = GameState.HOME  # 第 1 次 observe 就命中

    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    adb = MagicMock()

    rm = RecoveryManager(
        common_actions=common,
        game_sm=game_sm,
        adb_client=adb,
        screenshot_manager=None,
        config=cfg,
    )

    with RunContext(task_id="e2e_unknown_recover", state_before="UNKNOWN") as rc:
        recovered = game_sm.recover(recovery_manager=rm)
        rc.state_after = recovered.value

    assert recovered == GameState.HOME
    assert game_sm.current_state == GameState.HOME
    assert game_sm.history[-1].source == "recovery_manager"
    common.observe.assert_called_once()


# ============================================================
# E2E 3: 全流程 RecoveryManager 4 个方法各演示一次
# ============================================================


def test_e2e_all_four_recovery_methods_invokable(task_registry_with_daily_signin):
    """RecoveryManager 4 个方法都至少能调一次 + 状态正常切换。"""
    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)
    common = MagicMock(spec=CommonActions)
    common.observe.return_value = GameState.HOME
    common.close_popup.return_value = True
    common.go_home.return_value = True
    common.wait_loading.return_value = True

    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    adb = MagicMock()
    adb.disconnect.return_value = ActionResult(True, "ok", None)
    adb.connect.return_value = ActionResult(True, "ok", None)
    adb.is_connected = True

    rm = RecoveryManager(
        common_actions=common,
        game_sm=game_sm,
        adb_client=adb,
        screenshot_manager=None,
        config=cfg,
    )

    with RunContext(task_id="e2e_all_recover", state_before="UNKNOWN") as rc:
        # 1) recover_unknown — observe 返 HOME,game_sm 同步
        game_sm.update_state(GameState.UNKNOWN)
        r1 = rm.recover_unknown()
        # 真实 observe 内部会 update_state;mock 没副作用,手动同步
        game_sm.update_state(r1, source="test_sync")
        assert r1 == GameState.HOME

        # 2) recover_popup — POPUP + close_popup + go_home → HOME
        game_sm.update_state(GameState.POPUP)
        # go_home mock 返 True,但 game_sm 不会自动改(go_home mock 没副作用)
        # recover_popup 检查 game_sm.current_state == HOME,所以先改再调
        # 改用:让 go_home 副作用更新 game_sm
        def _go_home_side_effect():
            game_sm.update_state(GameState.HOME, source="mock_go_home")
            return True
        common.go_home.side_effect = _go_home_side_effect
        r2 = rm.recover_popup()
        assert r2 is True

        # 3) recover_loading_timeout
        game_sm.update_state(GameState.LOADING)
        r3 = rm.recover_loading_timeout()
        assert r3 is True

        # 4) recover_adb_error
        r4 = rm.recover_adb_error()
        assert r4 is True

        rc.state_after = game_sm.current_state.value

    # 4 个方法都至少被调过
    assert common.observe.called
    assert common.close_popup.called
    assert common.wait_loading.called
    assert adb.connect.called


# ============================================================
# E2E 4: main.py --phase4 入口
# ============================================================


def test_e2e_run_phase4_demo_returns_zero(task_registry_with_daily_signin):
    """main.run_phase4_demo 跑通 → exit 0。"""
    rc = run_phase4_demo(
        task_registry_with_daily_signin,
        use_real_adb=False,
        console_level="WARNING",
    )
    assert rc == 0


# ============================================================
# E2E 5: 配置驱动 — RetryPolicy.from_config + RecoveryManager(cfg)
# ============================================================


def test_e2e_retry_policy_loaded_from_config(task_registry_with_daily_signin):
    """从 cfg.app.retry 读配置,行为正确。"""
    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)
    policy = RetryPolicy.from_config(cfg)
    assert policy.max_attempts == 3
    assert policy.delay_seconds == 0.0
    assert policy.exponential_backoff is False
    # 白名单里包含 ADBTimeoutError / ADBCommandError
    assert "ADBTimeoutError" in policy.retryable_exceptions
    assert "ADBCommandError" in policy.retryable_exceptions


def test_e2e_recovery_manager_uses_config_thresholds(task_registry_with_daily_signin):
    """RecoveryManager 读 cfg.app.recovery 阈值。"""
    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)
    common = MagicMock(spec=CommonActions)
    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    adb = MagicMock()
    rm = RecoveryManager(
        common_actions=common, game_sm=game_sm, adb_client=adb,
        screenshot_manager=None, config=cfg,
    )
    # cfg.app.recovery.max_unknown_retries = 2
    assert rm._max_unknown == 2
    assert rm._max_popup == 2
    assert rm._max_loading_sec == 5.0
    assert rm._adb_reconnect == 2


# ============================================================
# E2E 6: 任务执行 → RunContext 日志含 state_before / state_after / elapsed_ms
# ============================================================


def test_e2e_run_context_records_state_transitions(task_registry_with_daily_signin):
    """RunContext 完整生命周期:state_before → 任务执行 → state_after。"""
    rc_ctx = RunContext(task_id="state_transition_test", state_before="UNKNOWN")
    with rc_ctx as rc:
        # 任务执行
        assert rc.state_after is None
        rc.state_after = "HOME"
        assert rc.state_after == "HOME"

    # 退出后 elapsed_ms 可读
    assert rc_ctx.elapsed_ms >= 0
    # state_after 在 __exit__ 后保留(供调用方读)
    assert rc_ctx.state_after == "HOME"


# ============================================================
# E2E 7: 失败场景 — RetryManager 耗尽 + RecoveryManager 兜底
# ============================================================


def test_e2e_retry_exhausted_then_recovery_recovers(
    task_registry_with_daily_signin, fast_retry_policy, monkeypatch
):
    """RetryManager 3 次都失败 → 由 RecoveryManager 接管 → 恢复成功。"""
    from device.adb_client import ADBTimeoutError
    monkeypatch.setattr("time.sleep", lambda _x: None)

    cfg = ConfigManager(task_registry_with_daily_signin, auto_load=True)
    common = MagicMock(spec=CommonActions)
    common.observe.return_value = GameState.HOME
    common.go_home.return_value = True

    # adb 模拟 3 次都 timeout
    adb = MagicMock()
    adb.screenshot.side_effect = ADBTimeoutError("persistent")

    retry_mgr = RetryManager(policy=fast_retry_policy)
    rm = RecoveryManager(
        common_actions=common,
        game_sm=GameStateMachine(initial=GameState.UNKNOWN),
        adb_client=adb,
        screenshot_manager=None,
        config=cfg,
    )

    with RunContext(task_id="e2e_retry_fail_recovery_ok", state_before="UNKNOWN") as rc:
        # 1) RetryManager 调,3 次都失败,抛 ADBTimeoutError
        with pytest.raises(ADBTimeoutError):
            retry_mgr.execute_adb_action(adb, "screenshot")
        assert adb.screenshot.call_count == 3

        # 2) RecoveryManager 接管(模拟业务层捕获异常后调)
        recovered = rm.recover_unknown()
        rc.state_after = recovered.value

    assert recovered == GameState.HOME  # observe 返 HOME
    common.observe.assert_called()
