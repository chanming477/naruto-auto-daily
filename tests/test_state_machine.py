"""test_state_machine.py — 状态机的关键行为。"""

from __future__ import annotations

import threading

import pytest

from core.state_machine import (
    StateMachine,
    TaskEvent,
    TaskState,
    build_default_state_machine,
)


def test_basic_transition():
    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    assert sm.state == TaskState.IDLE
    assert sm.trigger(TaskEvent.START) is True
    assert sm.state == TaskState.RUNNING


def test_illegal_transition_rejected():
    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    # IDLE 不允许直接 COMPLETE
    assert sm.trigger(TaskEvent.COMPLETE) is False
    assert sm.state == TaskState.IDLE


def test_reset_returns_to_initial_state():
    """P0-BUG-02: reset 必须能回到初始状态。"""
    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    sm.trigger(TaskEvent.START)
    assert sm.state == TaskState.RUNNING
    sm.trigger(TaskEvent.COMPLETE)
    assert sm.state == TaskState.COMPLETED

    # reset() 不传参 → 必须回到 initial_state (IDLE)，而不是当前状态
    sm.reset()
    assert sm.state == TaskState.IDLE
    assert sm.initial_state == TaskState.IDLE


def test_reset_to_explicit_target():
    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    sm.trigger(TaskEvent.START)
    sm.trigger(TaskEvent.COMPLETE)
    sm.reset(to_state="PAUSED")
    assert sm.state == "PAUSED"


def test_legal_events():
    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    assert set(sm.legal_events()) == {TaskEvent.START}
    sm.trigger(TaskEvent.START)
    assert set(sm.legal_events()) == {TaskEvent.PAUSE, TaskEvent.COMPLETE,
                                      TaskEvent.FAIL, TaskEvent.ABORT}


def test_callbacks_invoked_on_enter_and_exit():
    entered: list[str] = []
    exited: list[str] = []

    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    sm.add_callbacks(
        TaskState.RUNNING,
        on_enter=lambda s, p: entered.append(s),
        on_exit=lambda s, p: exited.append(s),
    )

    sm.trigger(TaskEvent.START)
    assert entered == [TaskState.RUNNING]
    assert exited == []  # IDLE 没注册 on_exit

    sm.trigger(TaskEvent.COMPLETE)
    assert exited == [TaskState.RUNNING]


def test_history_capped():
    sm = StateMachine("A", history_limit=3)
    sm.add_transition("A", "go_b", "B")
    sm.add_transition("B", "go_a", "A")
    for _ in range(5):
        sm.trigger("go_b")
        sm.trigger("go_a")
    assert len(sm.history) == 3
    # deque(maxlen=3) 保留最近 3 条，最新条目是最后一次 trigger(go_a)，所以
    # history[-1] 是 B→A；history[0] 是 3 条里最早的（B→A）。
    assert sm.history[-1].from_state == "B"
    assert sm.history[-1].event == "go_a"


def test_callback_exception_does_not_break_machine():
    def bad_cb(_s, _p):
        raise RuntimeError("boom")

    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    sm.add_callbacks(TaskState.RUNNING, on_enter=bad_cb)
    sm.trigger(TaskEvent.START)  # 不应抛错
    assert sm.state == TaskState.RUNNING


def test_concurrent_state_reads_are_safe():
    """P0-STABLE-01: 心跳线程并发读 + 主线程写，必须不抛错。"""
    sm = build_default_state_machine(TaskState.IDLE, log_transitions=False)
    errors: list[BaseException] = []
    stop = threading.Event()

    def writer():
        try:
            for _ in range(500):
                if not sm.trigger(TaskEvent.START):
                    pass
                sm.trigger(TaskEvent.COMPLETE)
                sm.reset()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    def reader():
        try:
            while not stop.is_set():
                _ = sm.state
                _ = sm.legal_events()
                _ = sm.history
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads[:-1]:
        t.join()
    stop.set()
    threads[-1].join()
    assert not errors, f"concurrent access raised: {errors}"