"""test_retry_manager.py — RetryManager 关键行为 + Phase 4 P0/P1 回归测试。

覆盖:
    - RetryPolicy 基础 + 校验
    - RetryManager.execute_with_retry 通用 API
    - RetryManager.execute_adb_action 真实调用链(Phase 4 重点)
    - 异常分类、指数退避、配置加载
    - P0-BUG-04 / P1-QUAL-01: safe_back/safe_home max_retries 实际使用
    - P1-STABLE-01: RecoveryManager 优先 adb.screenshot 截真实设备
    - P1-STABLE-02: 阈值 0 不被替换为默认
    - P1-QUAL-02: recover_popup 在 safe_back 后调 observe
    - P1-OVER-01: LoggingConfig 死配置已删
    - P0-ARCH-01 / P1-QUAL-03: --phase3-smoke argparse 可达
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from device.types import ActionResult
from recovery.recovery_manager import RecoveryManager
from recovery.retry_manager import (
    RetryManager,
    RetryPolicy,
    execute_with_retry,
)
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine
from tasks.common_actions import CommonActions


# ============================================================
# Common fixtures(被 Phase 4 P0/P1 回归测试用)
# ============================================================


@pytest.fixture
def fake_adb() -> MagicMock:
    """ADBClient MagicMock,默认所有 keyevent / screenshot / tap 都返回 success。"""
    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.return_value = ActionResult(
        success=True, message="ok", next_state=None,
        payload=np.zeros((100, 100, 3), dtype=np.uint8),
    )
    adb.tap.return_value = ActionResult(True, "ok", None)
    return adb


@pytest.fixture
def fake_recognizer() -> MagicMock:
    """PageRecognizer MagicMock,默认 detect_state 返回 UNKNOWN。"""
    from recognition.types import RecognitionResult
    rec = MagicMock()
    rec.detect_state.return_value = RecognitionResult(
        state=GameState.UNKNOWN, confidence=0.0, method="mock",
    )
    return rec


@pytest.fixture
def fake_game_sm() -> GameStateMachine:
    return GameStateMachine(initial=GameState.UNKNOWN)


@pytest.fixture
def common(
    fake_adb: MagicMock,
    fake_recognizer: MagicMock,
    fake_game_sm: GameStateMachine,
    tmp_path,
) -> CommonActions:
    return CommonActions(
        adb_client=fake_adb,
        recognizer=fake_recognizer,
        game_sm=fake_game_sm,
        config=MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=0.0))),
        project_root=tmp_path,
    )


@pytest.fixture
def fake_common() -> MagicMock:
    """mock CommonActions,默认 True / UNKNOWN;observe 副作用更新 game_sm 通过外部管理。"""
    c = MagicMock()
    c.close_popup.return_value = True
    c.go_home.return_value = True
    c.wait_loading.return_value = True
    c.observe.return_value = GameState.UNKNOWN
    c.safe_back.return_value = True
    c.safe_home.return_value = True
    return c


@pytest.fixture
def fake_screenshot_mgr() -> MagicMock:
    s = MagicMock()
    s.capture.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
    s.save_recovery.return_value = None
    return s


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fast_policy() -> RetryPolicy:
    """测试用快策略:最多 3 次,delay 0.01s,不做真 sleep。"""
    return RetryPolicy(
        max_attempts=3,
        delay_seconds=0.01,
        exponential_backoff=True,
        max_delay_seconds=0.05,
        retryable_exceptions=(),
    )


@pytest.fixture
def retry_mgr(fast_policy) -> RetryManager:
    return RetryManager(policy=fast_policy)


# ============================================================
# RetryPolicy
# ============================================================


def test_retry_policy_defaults():
    """默认策略:3 次 / 1s / 指数退避 / 上限 30s。"""
    p = RetryPolicy()
    assert p.max_attempts == 3
    assert p.delay_seconds == 1.0
    assert p.exponential_backoff is True
    assert p.max_delay_seconds == 30.0
    assert p.retryable_exceptions == ()


def test_retry_policy_from_config(tmp_path):
    """从 ConfigManager.app.retry 构造策略。"""
    from core.config_manager import (
        AppConfig, AppMeta, ConfigManager, LoggerConfig, RecoveryConfig,
        RetryConfig, SchedulerConfig, StateMachineConfig, ScreenshotConfig,
        AdbConfig, TemplateMatchingConfig, GameStateConfig, LoggingConfig,
    )

    # 手工构造 ConfigManager 风格的 cfg
    cfg = MagicMock()
    cfg.app.retry = RetryConfig(
        max_attempts=5, delay_seconds=2.0, exponential_backoff=False,
        max_delay_seconds=10.0, retryable_exceptions=["ADBError"],
    )
    policy = RetryPolicy.from_config(cfg)
    assert policy.max_attempts == 5
    assert policy.delay_seconds == 2.0
    assert policy.exponential_backoff is False
    assert policy.retryable_exceptions == ("ADBError",)


def test_retry_policy_validation_max_attempts():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_retry_policy_validation_negative_delay():
    with pytest.raises(ValueError):
        RetryPolicy(delay_seconds=-1.0)


def test_retry_policy_validation_max_delay_less_than_delay():
    with pytest.raises(ValueError):
        RetryPolicy(delay_seconds=10.0, max_delay_seconds=5.0)


def test_delay_for_exponential_grows():
    """指数退避:delay_for(1)=delay, delay_for(2)=2*delay, delay_for(3)=4*delay。"""
    p = RetryPolicy(
        max_attempts=10, delay_seconds=1.0,
        exponential_backoff=True, max_delay_seconds=100.0,
    )
    assert p.delay_for(1) == 1.0
    assert p.delay_for(2) == 2.0
    assert p.delay_for(3) == 4.0
    assert p.delay_for(4) == 8.0


def test_delay_for_caps_at_max_delay():
    """指数退避封顶 max_delay_seconds。"""
    p = RetryPolicy(
        max_attempts=20, delay_seconds=1.0,
        exponential_backoff=True, max_delay_seconds=5.0,
    )
    assert p.delay_for(1) == 1.0
    assert p.delay_for(2) == 2.0
    assert p.delay_for(3) == 4.0
    assert p.delay_for(4) == 5.0  # 8 capped to 5
    assert p.delay_for(5) == 5.0


def test_delay_for_fixed():
    """非指数退避:固定 delay_seconds。"""
    p = RetryPolicy(
        max_attempts=5, delay_seconds=2.0,
        exponential_backoff=False, max_delay_seconds=10.0,
    )
    assert p.delay_for(1) == 2.0
    assert p.delay_for(2) == 2.0
    assert p.delay_for(3) == 2.0


def test_is_retryable_empty_white_list_retries_all():
    """retryable_exceptions 为空 → 全部重试。"""
    p = RetryPolicy()
    assert p.is_retryable(RuntimeError("x")) is True
    assert p.is_retryable(ValueError("x")) is True


def test_is_retryable_white_list_filters():
    """retryable_exceptions 非空 → 只重试列出的(及子类)。"""
    p = RetryPolicy(retryable_exceptions=("ADBTimeoutError",))
    class ADBTimeoutError(Exception):
        pass
    class OtherError(Exception):
        pass
    assert p.is_retryable(ADBTimeoutError("x")) is True
    assert p.is_retryable(OtherError("x")) is False


# ============================================================
# RetryManager.execute_with_retry 通用 API
# ============================================================


def test_execute_with_retry_success_first_try(retry_mgr):
    """第一次就成功 → 不重试。"""
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    result = retry_mgr.execute_with_retry(fn)
    assert result == "ok"
    assert calls["n"] == 1


def test_execute_with_retry_succeeds_on_third_attempt(retry_mgr, monkeypatch):
    """第 3 次成功 → 重试 2 次。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError(f"transient {calls['n']}")
        return "ok"

    result = retry_mgr.execute_with_retry(fn)
    assert result == "ok"
    assert calls["n"] == 3


def test_execute_with_retry_exhausts_attempts(retry_mgr, monkeypatch):
    """3 次都失败 → 抛最后一次异常。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RuntimeError(f"fail {calls['n']}")

    with pytest.raises(RuntimeError, match="fail 3"):
        retry_mgr.execute_with_retry(fn)
    assert calls["n"] == 3


def test_execute_with_retry_max_attempts_one_means_no_retry():
    """max_attempts=1 表示不重试(只跑一次)。"""
    p = RetryPolicy(max_attempts=1, delay_seconds=0.0)
    rm = RetryManager(policy=p)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        rm.execute_with_retry(fn)
    assert calls["n"] == 1


def test_execute_with_retry_propagates_keyboard_interrupt(monkeypatch):
    """KeyboardInterrupt 永远不重试,直接抛。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    p = RetryPolicy(max_attempts=3, delay_seconds=0.0)
    rm = RetryManager(policy=p)

    def fn():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        rm.execute_with_retry(fn)


def test_execute_with_retry_non_retryable_exception_propagates(monkeypatch):
    """非 retryable 异常(白名单过滤)立即抛,不重试。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    p = RetryPolicy(
        max_attempts=3, delay_seconds=0.0,
        retryable_exceptions=("ADBTimeoutError",),
    )
    rm = RetryManager(policy=p)
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("not retryable")  # 不在白名单

    with pytest.raises(ValueError, match="not retryable"):
        rm.execute_with_retry(fn)
    assert calls["n"] == 1  # 不重试


def test_execute_with_retry_passes_args_and_kwargs(retry_mgr):
    """args / kwargs 透传给 fn。"""
    def fn(a, b, *, c):
        return (a, b, c)

    result = retry_mgr.execute_with_retry(fn, 1, 2, c=3)
    assert result == (1, 2, 3)


def test_execute_with_retry_uses_exponential_backoff(retry_mgr, monkeypatch):
    """指数退避:delay 序列应是 0.01 → 0.02 → 0.04 ...(封顶 0.05)。"""
    delays = []
    monkeypatch.setattr("time.sleep", lambda d: delays.append(d))

    def fn():
        raise RuntimeError("always fail")

    with pytest.raises(RuntimeError):
        retry_mgr.execute_with_retry(fn)

    # 3 次尝试 → 2 次 delay(attempt 1, 2);第 3 次不 delay(耗尽)
    assert len(delays) == 2
    # 第 1 次 delay = 0.01(0.01 * 2^0)
    # 第 2 次 delay = 0.02(0.01 * 2^1)
    assert abs(delays[0] - 0.01) < 1e-9
    assert abs(delays[1] - 0.02) < 1e-9


def test_execute_with_retry_top_level_convenience(monkeypatch):
    """顶层 execute_with_retry 函数。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("x")
        return "y"

    result = execute_with_retry(
        fn, policy=RetryPolicy(max_attempts=3, delay_seconds=0.0),
    )
    assert result == "y"
    assert calls["n"] == 2


# ============================================================
# execute_adb_action 真实调用链(Phase 4 重点)
# ============================================================


def test_execute_adb_action_wraps_screenshot_success(retry_mgr):
    """execute_adb_action 包装 ADBClient.screenshot,返回 ActionResult。"""
    adb = MagicMock()
    expected = ActionResult(True, "screenshot ok 720x1280", None, payload=MagicMock())
    adb.screenshot.return_value = expected

    result = retry_mgr.execute_adb_action(adb, "screenshot")
    assert result is expected
    assert result.success is True
    adb.screenshot.assert_called_once()


def test_execute_adb_action_passes_args_and_kwargs(retry_mgr):
    """execute_adb_action 透传 *args / **kwargs 给 adb 方法。"""
    adb = MagicMock()
    adb.tap.return_value = ActionResult(True, "tap ok", None)

    result = retry_mgr.execute_adb_action(adb, "tap", 100, 200, duration=50)
    assert result.success is True
    adb.tap.assert_called_once_with(100, 200, duration=50)


def test_execute_adb_action_retries_on_transient_adb_error(monkeypatch):
    """adb.screenshot 第 1 次抛 ADBTimeoutError,RetryManager 重试,最终成功。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    from device.adb_client import ADBTimeoutError

    adb = MagicMock()
    success_result = ActionResult(True, "screenshot ok", None, payload=MagicMock())
    adb.screenshot.side_effect = [ADBTimeoutError("transient"), success_result]

    policy = RetryPolicy(
        max_attempts=3, delay_seconds=0.0,
        retryable_exceptions=("ADBTimeoutError",),
    )
    rm = RetryManager(policy=policy)

    result = rm.execute_adb_action(adb, "screenshot")
    assert result is success_result
    assert adb.screenshot.call_count == 2


def test_execute_adb_action_exhausts_retries_on_persistent_failure(monkeypatch):
    """adb.tap 3 次都抛 → 抛最后一次异常。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    from device.adb_client import ADBCommandError

    adb = MagicMock()
    adb.tap.side_effect = ADBCommandError("adb tap failed")

    policy = RetryPolicy(
        max_attempts=3, delay_seconds=0.0,
        retryable_exceptions=("ADBCommandError",),
    )
    rm = RetryManager(policy=policy)

    with pytest.raises(ADBCommandError, match="adb tap failed"):
        rm.execute_adb_action(adb, "tap", 100, 200)
    assert adb.tap.call_count == 3


def test_execute_adb_action_uses_exponential_backoff_between_attempts(monkeypatch):
    """指数退避:delay 序列在 tap 重试时正确。"""
    delays = []
    monkeypatch.setattr("time.sleep", lambda d: delays.append(d))
    from device.adb_client import ADBTimeoutError

    adb = MagicMock()
    adb.tap.side_effect = ADBTimeoutError("x")

    policy = RetryPolicy(
        max_attempts=4, delay_seconds=0.1,
        exponential_backoff=True, max_delay_seconds=10.0,
        retryable_exceptions=("ADBTimeoutError",),
    )
    rm = RetryManager(policy=policy)

    with pytest.raises(ADBTimeoutError):
        rm.execute_adb_action(adb, "tap", 0, 0)

    # 4 次尝试 → 3 次 delay
    assert len(delays) == 3
    assert abs(delays[0] - 0.1) < 1e-9
    assert abs(delays[1] - 0.2) < 1e-9
    assert abs(delays[2] - 0.4) < 1e-9


def test_execute_adb_action_raises_attribute_error_for_unknown_method(retry_mgr):
    """adb 上没有 method_name → 抛 AttributeError(不重试)。"""
    adb = MagicMock(spec=["screenshot"])  # 只有 screenshot,没 tap
    with pytest.raises(AttributeError, match="has no method 'tap'"):
        retry_mgr.execute_adb_action(adb, "tap", 0, 0)


def test_execute_adb_action_keyevent_real_call(retry_mgr):
    """keyevent 是最常用的 ADB 操作,验证真实调用链可工作。"""
    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "keyevent(BACK)", None)

    result = retry_mgr.execute_adb_action(adb, "keyevent", "BACK")
    assert result.success is True
    adb.keyevent.assert_called_once_with("BACK")


# ============================================================
# P0-BUG-04 / P1-QUAL-01 回归测试
# ============================================================


def test_common_actions_safe_back_actually_uses_max_retries(common, fake_adb):
    """P0-BUG-04: safe_back 必须按 max_retries 重试,不丢弃参数。"""
    fake_adb.keyevent.return_value = ActionResult(False, "fail", None)
    result = common.safe_back(max_retries=3)
    assert result is False
    # 应该调 3 次(不再只调 1 次)
    assert fake_adb.keyevent.call_count == 3


def test_common_actions_safe_back_succeeds_on_retry(common, fake_adb):
    """safe_back:第 2 次成功 → 返 True,不调第 3 次。"""
    fake_adb.keyevent.side_effect = [
        ActionResult(False, "fail 1", None),
        ActionResult(True, "ok", None),
        ActionResult(True, "ok", None),
    ]
    result = common.safe_back(max_retries=3)
    assert result is True
    assert fake_adb.keyevent.call_count == 2


def test_common_actions_safe_home_actually_uses_max_retries(common, fake_adb):
    """P1-QUAL-01: safe_home 同 safe_back,使用 max_retries。"""
    fake_adb.keyevent.return_value = ActionResult(False, "fail", None)
    result = common.safe_home(max_retries=5)
    assert result is False
    assert fake_adb.keyevent.call_count == 5


def test_common_actions_safe_back_default_max_retries_is_three(common, fake_adb):
    """默认 max_retries=3,3 次都失败。"""
    fake_adb.keyevent.return_value = ActionResult(False, "fail", None)
    result = common.safe_back()
    assert result is False
    assert fake_adb.keyevent.call_count == 3


def test_common_actions_safe_back_max_retries_one_means_no_retry(common, fake_adb):
    """max_retries=1 → 只调 1 次,失败返 False。"""
    fake_adb.keyevent.return_value = ActionResult(False, "fail", None)
    result = common.safe_back(max_retries=1)
    assert result is False
    assert fake_adb.keyevent.call_count == 1


# ============================================================
# P1-STABLE-01 回归测试
# ============================================================


def test_recovery_save_snapshot_uses_adb_screenshot_first(
    fake_common, fake_game_sm, fake_adb, fake_screenshot_mgr
):
    """P1-STABLE-01: 恢复归档时优先用 adb.screenshot() 截真实设备画面。"""
    import numpy as np
    from device.types import ActionResult

    fake_common.observe.return_value = GameState.HOME
    # adb.screenshot 返回成功,带 ndarray payload
    adb_arr = np.zeros((100, 100, 3), dtype=np.uint8)
    fake_adb.screenshot.return_value = ActionResult(
        True, "adb screenshot", None, payload=adb_arr,
    )
    # screenshot_manager 的 capture 返不同 array(用于验证不会先用它)
    local_arr = np.ones((50, 50, 3), dtype=np.uint8) * 255
    fake_screenshot_mgr.capture.return_value = local_arr

    rm = RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=fake_screenshot_mgr,
        config=None,
    )
    rm.recover_unknown()

    # 优先 adb.screenshot(真实设备)
    fake_adb.screenshot.assert_called()
    # 截图用的应该是 adb 返回的 array(全 0),不是 screenshot_mgr 的(全 255)
    fake_screenshot_mgr.save_recovery.assert_called_once()
    saved_arr = fake_screenshot_mgr.save_recovery.call_args.args[0]
    assert np.array_equal(saved_arr, adb_arr)


def test_recovery_save_snapshot_falls_back_to_screenshot_mgr_when_adb_fails(
    fake_common, fake_game_sm, fake_adb, fake_screenshot_mgr
):
    """P1-STABLE-01 降级路径: adb 拿不到时降级到 ScreenshotManager。"""
    import numpy as np
    from device.types import ActionResult

    fake_common.observe.return_value = GameState.HOME
    # adb.screenshot 失败
    fake_adb.screenshot.return_value = ActionResult(False, "adb fail", None)
    # screenshot_manager 给一张图
    local_arr = np.ones((50, 50, 3), dtype=np.uint8) * 128
    fake_screenshot_mgr.capture.return_value = local_arr

    rm = RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=fake_screenshot_mgr,
        config=None,
    )
    rm.recover_unknown()

    fake_adb.screenshot.assert_called()
    fake_screenshot_mgr.capture.assert_called()
    fake_screenshot_mgr.save_recovery.assert_called_once()
    # 应该是 screenshot_mgr 的 array
    saved_arr = fake_screenshot_mgr.save_recovery.call_args.args[0]
    assert np.array_equal(saved_arr, local_arr)


# ============================================================
# P1-STABLE-02 回归测试
# ============================================================


def test_recovery_manager_threshold_zero_means_zero_not_default(
    fake_common, fake_game_sm, fake_adb
):
    """P1-STABLE-02: cfg.app.recovery.max_unknown_retries=0 → 0,不是默认 3。"""
    # 构造一个 fake config,显式设 0
    from types import SimpleNamespace
    cfg = SimpleNamespace()
    cfg.app = SimpleNamespace()
    cfg.app.recovery = SimpleNamespace(
        max_unknown_retries=0,
        max_popup_retries=0,
        max_loading_seconds=0.0,
        adb_reconnect_attempts=0,
    )
    rm = RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=None,
        config=cfg,
    )
    assert rm._max_unknown == 0  # 不是 3
    assert rm._max_popup == 0
    assert rm._max_loading_sec == 0.0
    assert rm._adb_reconnect == 0


def test_recovery_manager_threshold_missing_uses_default(
    fake_common, fake_game_sm, fake_adb
):
    """无 cfg / cfg.app / cfg.app.recovery → 用硬编码默认。"""
    rm = RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=None,
        config=None,
    )
    assert rm._max_unknown == 3
    assert rm._max_popup == 3
    assert rm._max_loading_sec == 60.0
    assert rm._adb_reconnect == 2


# ============================================================
# P1-QUAL-02 回归测试
# ============================================================


def test_recover_popup_calls_observe_after_safe_back(
    fake_common, fake_game_sm, fake_adb
):
    """P1-QUAL-02: safe_back 不更新 game_sm,recover_popup 必须 observe 一次。"""
    from device.types import ActionResult

    # 准备:safe_back 不切 game_sm(因为是 mock),observe 切到 HOME
    fake_common.safe_back.return_value = True
    observe_calls = {"n": 0}
    observed_states = [GameState.POPUP, GameState.HOME]  # 第 1 次还 POPUP,第 2 次 HOME

    def _observe():
        s = observed_states[observe_calls["n"]] if observe_calls["n"] < len(observed_states) else GameState.HOME
        observe_calls["n"] += 1
        fake_game_sm.update_state(s, source="test_observe")
        return s
    fake_common.observe.side_effect = _observe

    fake_common.go_home.return_value = True

    fake_game_sm.update_state(GameState.POPUP)
    rm = RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=None,
        config=None,
    )
    result = rm.recover_popup()
    assert result is True
    # safe_back 调了
    assert fake_common.safe_back.called
    # observe 至少调了 1 次(关键:不能跳过 observe)
    assert observe_calls["n"] >= 1


# ============================================================
# P1-OVER-01 回归测试
# ============================================================


def test_logging_config_has_no_dead_fields():
    """P1-OVER-01: LoggingConfig 不再含 capture_transitions / log_state_changes 死配置。"""
    from core.config_manager import LoggingConfig
    fields = LoggingConfig.model_fields
    # 死配置字段必须不存在
    assert "capture_transitions" not in fields
    assert "log_state_changes" not in fields


def test_logging_config_empty_loads_from_yaml():
    """LoggingConfig 即使 yaml 是空 dict 也能加载(默认值生效)。"""
    from core.config_manager import LoggingConfig
    cfg = LoggingConfig.model_validate({})
    # 既然没字段,model_dump 应该只有空
    assert cfg.model_dump() == {}


# ============================================================
# P0-ARCH-01 / P1-QUAL-03 回归测试
# ============================================================


def test_phase3_smoke_argparse_flag_exists():
    """P0-ARCH-01: --phase3-smoke 必须在 parse_args 中定义。"""
    import argparse
    from main import parse_args
    args = parse_args(["--phase3-smoke"])
    assert args.phase3_smoke is True


def test_phase3_smoke_cli_reachable(tmp_path):
    """P1-QUAL-03: --phase3-smoke 必须能从 CLI 调到 cmd_phase3_smoke。"""
    # 准备一个最小可用的 task_registry
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "app_config.yaml").write_text(
        "app: {}\nlogger:\n  console_level: WARNING\n  file_level: DEBUG\n  log_dir: logs\n"
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
        "    description: 'p4'\n    estimated_time_sec: 1\n"
        "    retry_on_failure: false\n    max_retries: 0\n    config_options: {}\n",
        encoding="utf-8",
    )
    for s in ("HOME", "POPUP", "LOADING"):
        (tmp_path / "resources" / "templates" / s).mkdir(parents=True, exist_ok=True)

    # 实际通过 main() 跑 --phase3-smoke(只验证 CLI 可达,rc 可以是 0 或 1)
    from main import main
    # 重定向 PROJECT_ROOT 不容易,改用 cmd_phase3_smoke 直接调
    import main as main_module
    original_root = main_module.PROJECT_ROOT
    main_module.PROJECT_ROOT = tmp_path
    try:
        rc = main(["--phase3-smoke", "--quiet"])
    finally:
        main_module.PROJECT_ROOT = original_root
    # 关键:CLI 没崩(没抛 SystemExit,rc 0 或 1 都行)
    assert rc in (0, 1)
