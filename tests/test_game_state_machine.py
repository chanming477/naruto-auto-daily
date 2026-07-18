"""test_game_state_machine.py — GameStateMachine 关键行为。

V3 (Phase 4): recover() 签名收紧 — 删除 probe 参数,只接受 RecoveryManager。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from state_machine.game_state import GameState
from state_machine.game_state_machine import GameStateMachine, StateTransition


def test_initial_state_default_is_unknown():
    sm = GameStateMachine()
    assert sm.current_state == GameState.UNKNOWN
    assert sm.initial_state == GameState.UNKNOWN


def test_initial_state_can_be_set():
    sm = GameStateMachine(initial=GameState.HOME)
    assert sm.current_state == GameState.HOME


def test_initial_state_validation():
    with pytest.raises(TypeError):
        GameStateMachine(initial="HOME")  # type: ignore[arg-type]


def test_update_state_changes_current():
    sm = GameStateMachine()
    assert sm.update_state(GameState.HOME) is True
    assert sm.current_state == GameState.HOME
    assert len(sm.history) == 1


def test_update_state_same_state_returns_false():
    sm = GameStateMachine(initial=GameState.HOME)
    assert sm.update_state(GameState.HOME) is False
    assert sm.history == []


def test_update_state_records_transition():
    sm = GameStateMachine()
    sm.update_state(GameState.HOME, source="test")
    assert len(sm.history) == 1
    tr = sm.history[0]
    assert tr.from_state == GameState.UNKNOWN
    assert tr.to_state == GameState.HOME
    assert tr.source == "test"


def test_update_state_rejects_non_enum():
    sm = GameStateMachine()
    assert sm.update_state("HOME") is False  # type: ignore[arg-type]
    assert sm.current_state == GameState.UNKNOWN
    assert sm.history == []


def test_go_home_changes_to_home():
    sm = GameStateMachine(initial=GameState.POPUP)
    assert sm.go_home() is True
    assert sm.current_state == GameState.HOME
    assert sm.history[-1].source == "go_home"


def test_go_home_from_unknown():
    sm = GameStateMachine()
    sm.go_home()
    assert sm.current_state == GameState.HOME


def test_go_home_noop_when_already_home():
    sm = GameStateMachine(initial=GameState.HOME)
    assert sm.go_home() is False
    assert sm.history == []


# ============================================================
# V3 (Phase 4): recover() 新签名 — 只接 RecoveryManager
# ============================================================


def test_recover_skipped_when_not_unknown():
    """recover 在非 UNKNOWN 状态下幂等返回 current(不论有没有 recovery_manager)。"""
    sm = GameStateMachine(initial=GameState.HOME)
    # 无 recovery_manager 也不应被调(因为不 UNKNOWN)
    recovered = sm.recover(recovery_manager=None)
    assert recovered == GameState.HOME


def test_recover_without_recovery_manager_stays_unknown():
    """V3: current=UNKNOWN 但 recovery_manager is None → warning + 状态保持 UNKNOWN(不抛)。"""
    sm = GameStateMachine()
    assert sm.current_state == GameState.UNKNOWN
    recovered = sm.recover(recovery_manager=None)
    assert recovered == GameState.UNKNOWN
    assert sm.current_state == GameState.UNKNOWN
    assert sm.history == []  # 没产生切换


def test_recover_with_recovery_manager_invokes_recover_unknown():
    """V3: 传 recovery_manager 时,recover() 调 recovery_manager.recover_unknown() 并 update_state。"""
    sm = GameStateMachine()
    assert sm.current_state == GameState.UNKNOWN

    # mock RecoveryManager:recover_unknown 返 HOME
    rm = MagicMock()
    rm.recover_unknown.return_value = GameState.HOME

    recovered = sm.recover(recovery_manager=rm)

    rm.recover_unknown.assert_called_once()
    assert recovered == GameState.HOME
    assert sm.current_state == GameState.HOME
    assert sm.history[-1].source == "recovery_manager"


def test_recover_with_recovery_manager_returns_unknown_if_recovery_fails():
    """V3: recovery_manager.recover_unknown 返 UNKNOWN → 状态保持 UNKNOWN,不 update。"""
    sm = GameStateMachine()
    rm = MagicMock()
    rm.recover_unknown.return_value = GameState.UNKNOWN

    recovered = sm.recover(recovery_manager=rm)

    rm.recover_unknown.assert_called_once()
    assert recovered == GameState.UNKNOWN
    assert sm.current_state == GameState.UNKNOWN
    assert sm.history == []  # 没产生切换


def test_recover_idempotent_when_already_known():
    """非 UNKNOWN 状态调 recover(),即使有 recovery_manager 也不调它。"""
    sm = GameStateMachine(initial=GameState.HOME)
    rm = MagicMock()
    recovered = sm.recover(recovery_manager=rm)
    assert recovered == GameState.HOME
    rm.recover_unknown.assert_not_called()  # 关键:不调


# ============================================================
# 其它(保留)
# ============================================================


def test_history_capped():
    sm = GameStateMachine(history_limit=5)
    for _ in range(10):
        sm.update_state(GameState.HOME)
        sm.update_state(GameState.UNKNOWN)
    assert len(sm.history) == 5


def test_reset_returns_to_initial_and_clears_history():
    sm = GameStateMachine(initial=GameState.HOME)
    sm.update_state(GameState.POPUP)
    sm.update_state(GameState.LOADING)
    assert len(sm.history) == 2
    sm.reset()
    assert sm.current_state == GameState.HOME
    assert sm.history == []


def test_is_known_property():
    sm = GameStateMachine()
    assert sm.is_known is False
    sm.update_state(GameState.HOME)
    assert sm.is_known is True
    sm.update_state(GameState.UNKNOWN)
    assert sm.is_known is False


def test_state_transition_str():
    tr = StateTransition(
        timestamp=__import__("datetime").datetime(2026, 1, 1, 12, 0, 0),
        from_state=GameState.UNKNOWN,
        to_state=GameState.HOME,
        source="x",
    )
    s = str(tr)
    assert "UNKNOWN" in s
    assert "HOME" in s
    assert "x" in s