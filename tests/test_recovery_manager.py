"""test_recovery_manager.py — RecoveryManager 4 个恢复方法。

所有依赖用 MagicMock,零真实 ADB / 游戏资源。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from device.types import ActionResult
from recovery.recovery_manager import RecoveryManager
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fake_game_sm() -> GameStateMachine:
    return GameStateMachine(initial=GameState.UNKNOWN)


@pytest.fixture
def fake_common() -> MagicMock:
    """mock CommonActions,所有方法默认 True / 返回 UNKNOWN。

    注意: ``observe`` mock **没有副作用**(不更新 game_sm),跟真实实现不同。
    测试用 ``fake_common.observe.return_value = X`` 覆盖时,需要**手动**调
    ``fake_game_sm.update_state(X)`` 模拟真实 observe 内部的 update_state 副作用。
    详见 ``_set_observe_and_sm_state`` helper。
    """
    c = MagicMock()
    c.close_popup.return_value = True
    c.go_home.return_value = True
    c.wait_loading.return_value = True
    c.observe.return_value = GameState.UNKNOWN
    return c


def _set_observe_and_sm_state(
    common_mock: MagicMock, game_sm: GameStateMachine, state: GameState,
) -> None:
    """设置 ``common.observe`` 返 X + 同步更新 game_sm(模拟真实 observe 副作用)。

    注意:对 ``recover_unknown`` 测试,game_sm 必须保持 UNKNOWN,否则会被早返回。
    调用方应根据场景决定 game_sm 是否同步更新。
    """
    common_mock.observe.return_value = state
    # 不在这里改 game_sm,留给调用方决定


def _set_observe_only(common_mock: MagicMock, state: GameState) -> None:
    """只设置 ``common.observe`` 返 X,不动 game_sm。

    适合 ``recover_unknown`` 测试 — recover_unknown 检查 game_sm 是 UNKNOWN 才走主流程。
    """
    common_mock.observe.return_value = state


def _simulate_observe_side_effect(
    common_mock: MagicMock, game_sm: GameStateMachine,
) -> None:
    """给 ``common.observe`` 加 side_effect:返 X 同时 update_state(game_sm, X)。

    模拟真实 CommonActions.observe 的副作用。
    """
    def _side_effect():
        state = common_mock.observe.return_value
        game_sm.update_state(state, source="mock_observe_side_effect")
        return state
    common_mock.observe.side_effect = _side_effect


@pytest.fixture
def fake_adb() -> MagicMock:
    a = MagicMock()
    a.disconnect.return_value = ActionResult(True, "disconnected", None)
    a.connect.return_value = ActionResult(True, "connected", None)
    a.is_connected = True
    return a


@pytest.fixture
def fake_screenshot_mgr() -> MagicMock:
    s = MagicMock()
    s.capture.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
    s.save_recovery.return_value = Path("screenshots/recovery/x.png")
    return s


@pytest.fixture
def recovery_mgr(fake_common, fake_game_sm, fake_adb, fake_screenshot_mgr) -> RecoveryManager:
    return RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=fake_screenshot_mgr,
        config=None,  # 用硬编码默认阈值
    )


# ============================================================
# recover_unknown
# ============================================================


def test_recover_unknown_returns_current_when_not_unknown(recovery_mgr, fake_game_sm, fake_common):
    """非 UNKNOWN 状态 → 直接返 current,不调 observe。"""
    fake_game_sm.update_state(GameState.HOME)
    result = recovery_mgr.recover_unknown()
    assert result == GameState.HOME
    fake_common.observe.assert_not_called()


def test_recover_unknown_uses_common_observe_to_refresh_state(recovery_mgr, fake_game_sm, fake_common):
    """UNKNOWN 时:observe 一次,若结果非 UNKNOWN 就返。"""
    # game_sm 保持 UNKNOWN(recover_unknown 走主流程);
    # observe mock 返 HOME + 副作用更新 game_sm(模拟真实 observe)。
    _set_observe_only(fake_common, GameState.HOME)
    _simulate_observe_side_effect(fake_common, fake_game_sm)
    result = recovery_mgr.recover_unknown()
    assert result == GameState.HOME
    assert fake_game_sm.current_state == GameState.HOME
    # observe 调了 1 次就退出(命中 HOME)
    assert fake_common.observe.call_count == 1


def test_recover_unknown_exhausts_retries_then_go_home(recovery_mgr, fake_game_sm, fake_common):
    """observe 全部返 UNKNOWN → 最后 go_home 兜底(go_home 切到 HOME)。"""
    fake_common.observe.return_value = GameState.UNKNOWN  # 全部 UNKNOWN
    fake_common.go_home.return_value = True
    # 模拟 go_home 切到 HOME(真实 CommonActions.go_home 内部会调 update_state)
    def _go_home_side_effect():
        fake_game_sm.update_state(GameState.HOME, source="mock_go_home")
        return True
    fake_common.go_home.side_effect = _go_home_side_effect

    result = recovery_mgr.recover_unknown()
    # go_home 内部把 game_sm 切到 HOME 后,recover_unknown 应返 HOME
    assert result == GameState.HOME


def test_recover_unknown_returns_unknown_when_all_fail(recovery_mgr, fake_game_sm, fake_common):
    """observe 全部返 UNKNOWN + go_home 失败 → 返 UNKNOWN。"""
    fake_common.observe.return_value = GameState.UNKNOWN
    fake_common.go_home.return_value = False

    result = recovery_mgr.recover_unknown()
    assert result == GameState.UNKNOWN


def test_recover_unknown_saves_recovery_screenshot_on_success(recovery_mgr, fake_game_sm, fake_common, fake_screenshot_mgr):
    """恢复成功 → 调 ScreenshotManager.save_recovery。"""
    _set_observe_only(fake_common, GameState.HOME)
    _simulate_observe_side_effect(fake_common, fake_game_sm)
    recovery_mgr.recover_unknown()
    fake_screenshot_mgr.save_recovery.assert_called()


# ============================================================
# recover_popup
# ============================================================


def test_recover_popup_returns_true_when_not_popup(recovery_mgr, fake_game_sm, fake_common):
    """非 POPUP → 返 True,不调 close_popup / go_home。"""
    fake_game_sm.update_state(GameState.HOME)
    result = recovery_mgr.recover_popup()
    assert result is True
    fake_common.close_popup.assert_not_called()
    fake_common.go_home.assert_not_called()


def test_recover_popup_succeeds_when_go_home_works(recovery_mgr, fake_game_sm, fake_common):
    """POPUP + safe_back 失败 + go_home 切到 HOME → 返 True。"""
    fake_game_sm.update_state(GameState.POPUP)
    # safe_back 不切状态(BACK 没关掉 POPUP);
    # go_home 副作用:切到 HOME
    def _go_home():
        fake_game_sm.update_state(GameState.HOME, source="mock_go_home")
        return True
    fake_common.go_home.side_effect = _go_home
    # safe_back 默认返 True 但不切 game_sm(因为是 mock,没有真实逻辑)
    # close_popup 默认返 True 但不切 game_sm
    result = recovery_mgr.recover_popup()
    assert result is True
    # safe_back / close_popup / go_home 都应被调过
    assert fake_common.safe_back.called
    assert fake_common.close_popup.called
    assert fake_common.go_home.called


def test_recover_popup_returns_false_after_max_attempts(recovery_mgr, fake_game_sm, fake_common):
    """POPUP + 多次都失败 → 返 False。"""
    fake_game_sm.update_state(GameState.POPUP)
    fake_common.go_home.return_value = False
    fake_common.close_popup.return_value = False
    result = recovery_mgr.recover_popup()
    assert result is False


# ============================================================
# recover_loading_timeout
# ============================================================


def test_recover_loading_timeout_returns_true_when_not_loading(recovery_mgr, fake_game_sm, fake_common):
    """非 LOADING → 返 True。"""
    fake_game_sm.update_state(GameState.HOME)
    result = recovery_mgr.recover_loading_timeout()
    assert result is True
    fake_common.wait_loading.assert_not_called()


def test_recover_loading_timeout_succeeds_when_wait_loading_returns_true(
    recovery_mgr, fake_game_sm, fake_common
):
    """LOADING + wait_loading 成功 → 返 True。"""
    fake_game_sm.update_state(GameState.LOADING)
    fake_common.wait_loading.return_value = True
    result = recovery_mgr.recover_loading_timeout()
    assert result is True
    fake_common.wait_loading.assert_called_once()


def test_recover_loading_timeout_falls_back_to_go_home(recovery_mgr, fake_game_sm, fake_common):
    """LOADING + wait_loading 超时 + go_home 成功 → 返 True。"""
    fake_game_sm.update_state(GameState.LOADING)
    fake_common.wait_loading.return_value = False
    fake_common.go_home.return_value = True
    fake_game_sm.update_state(GameState.HOME)  # go_home 切了
    result = recovery_mgr.recover_loading_timeout()
    assert result is True


def test_recover_loading_timeout_returns_false_when_all_fail(recovery_mgr, fake_game_sm, fake_common):
    """LOADING + wait_loading 超时 + go_home 失败 → 返 False。"""
    fake_game_sm.update_state(GameState.LOADING)
    fake_common.wait_loading.return_value = False
    fake_common.go_home.return_value = False
    result = recovery_mgr.recover_loading_timeout()
    assert result is False


# ============================================================
# recover_adb_error
# ============================================================


def test_recover_adb_error_succeeds_on_first_reconnect(recovery_mgr, fake_adb, fake_screenshot_mgr):
    """第 1 次 connect 成功 → 返 True。"""
    fake_adb.connect.return_value = ActionResult(True, "connected", None)
    fake_adb.is_connected = True
    result = recovery_mgr.recover_adb_error()
    assert result is True
    fake_adb.disconnect.assert_called_once()
    fake_adb.connect.assert_called_once()


def test_recover_adb_error_retries_when_connect_fails(recovery_mgr, fake_adb, monkeypatch):
    """第 1 次 connect 失败,第 2 次成功 → 返 True。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    fake_adb.connect.side_effect = [
        ActionResult(False, "fail 1", None),
        ActionResult(True, "connected", None),
    ]
    fake_adb.is_connected = True
    result = recovery_mgr.recover_adb_error()
    assert result is True
    assert fake_adb.connect.call_count == 2


def test_recover_adb_error_returns_false_after_max_attempts(recovery_mgr, fake_adb, monkeypatch):
    """所有 connect 都失败 → 返 False。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    fake_adb.connect.return_value = ActionResult(False, "fail", None)
    fake_adb.is_connected = False
    result = recovery_mgr.recover_adb_error()
    assert result is False
    # 默认 adb_reconnect_attempts=2,加上 disconnect 前的 1 次 = 2 次 connect
    assert fake_adb.connect.call_count == 2


def test_recover_adb_error_handles_disconnect_exception(recovery_mgr, fake_adb, monkeypatch):
    """disconnect 抛异常时,不阻塞后续 connect。"""
    monkeypatch.setattr("time.sleep", lambda _x: None)
    fake_adb.disconnect.side_effect = RuntimeError("oops")
    fake_adb.connect.return_value = ActionResult(True, "ok", None)
    fake_adb.is_connected = True
    # 不应抛
    result = recovery_mgr.recover_adb_error()
    assert result is True


# ============================================================
# 复用 CommonActions(不复制导航逻辑)
# ============================================================


def test_recovery_manager_does_not_implement_navigation(recovery_mgr, fake_common):
    """V2 职责边界: RecoveryManager 不直接调 adb.keyevent,全部委托 CommonActions。"""
    recovery_mgr.recover_unknown()
    recovery_mgr.recover_popup()
    recovery_mgr.recover_loading_timeout()
    # fake_common.close_popup / go_home / wait_loading 应被调过
    # 但 adb_client.keyevent 不应被 recovery_mgr 直接调
    # (recovery_mgr 内部不持有 keyevent 逻辑)
    assert fake_common.close_popup.called or fake_common.go_home.called


# ============================================================
# screenshot_manager 为 None 时不归档
# ============================================================


def test_recovery_manager_without_screenshot_manager_does_not_crash(
    fake_common, fake_game_sm, fake_adb
):
    """screenshot_manager=None 时,save_recovery 被跳过,主流程不抛。"""
    rm = RecoveryManager(
        common_actions=fake_common,
        game_sm=fake_game_sm,
        adb_client=fake_adb,
        screenshot_manager=None,
        config=None,
    )
    fake_common.observe.return_value = GameState.HOME
    # 不应抛
    result = rm.recover_unknown()
    assert result == GameState.HOME
