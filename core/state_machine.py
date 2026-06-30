"""core.state_machine — 程序生命周期状态机(运行级,线程安全)。

V2 职责边界声明:
    本模块 **仅负责程序生命周期管理**:
        - IDLE / RUNNING / PAUSED / COMPLETED / FAILED / ABORTING / ABORTED
    本模块 **禁止处理游戏页面状态**(HOME / POPUP / LOADING / UNKNOWN),
    那属于 ``state_machine.game_state_machine``。

两个状态机的关系:
    - ``core.state_machine`` (本模块) — 运行级:Scheduler / BaseTask 用它驱动
      START/PAUSE/COMPLETE/FAILED/ABORT 转换。
    - ``state_machine.game_state_machine`` — 业务级:CommonActions / PageRecognizer
      用它记录当前游戏页面。
    两者 **不互相 import、不互相调用、不维护同一状态**。

设计要点:
- 不依赖第三方状态机库(transitions / statemachine),避免引入隐性行为。
- 状态用字符串:常量化在 ``TaskState`` 类里。
- 转换规则显式声明:(from_state, event) -> to_state,可选 guard。
- 每个状态可注册 on_enter / on_exit 回调;回调异常会被捕获并日志,不破坏状态机本身。
- 转换历史保留最近 N 条,方便诊断。
- 线程安全:所有读 / 写操作通过 ``threading.RLock`` 保护,心跳线程与主线程可并发访问。

公开 API:
    StateMachine(initial_state: str, *, history_limit: int = 100)
    build_default_state_machine(initial_state: str, *, log_transitions: bool = True)
        工厂函数:注入 Phase 1 标准任务状态机(IDLE/RUNNING/PAUSED/COMPLETED/
        FAILED/ABORTING/ABORTED)的全部转换 + 日志回调。
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque

from loguru import logger

__all__ = [
    "StateMachine",
    "TransitionRecord",
    "TaskState",
    "TaskEvent",
    "build_default_state_machine",
]

Guard = Callable[[str, dict[str, Any] | None], bool]
EnterCb = Callable[[str, dict[str, Any] | None], None]
ExitCb = Callable[[str, dict[str, Any] | None], None]


class TaskState:
    """全局任务执行状态常量。"""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"

    ALL = (IDLE, RUNNING, PAUSED, COMPLETED, FAILED, ABORTING, ABORTED)
    TERMINAL = (COMPLETED, FAILED, ABORTED)


class TaskEvent:
    """全局事件常量。"""

    START = "START"           # IDLE -> RUNNING
    PAUSE = "PAUSE"           # RUNNING -> PAUSED
    RESUME = "RESUME"         # PAUSED -> RUNNING
    COMPLETE = "COMPLETE"     # RUNNING -> COMPLETED
    FAIL = "FAIL"             # RUNNING/PAUSED -> FAILED
    ABORT = "ABORT"           # 任何非终止态 -> ABORTING
    FINALIZE_ABORT = "FINALIZE_ABORT"  # ABORTING -> ABORTED
    RESET = "RESET"           # 终止态 -> IDLE


@dataclass
class TransitionRecord:
    timestamp: datetime
    from_state: str
    event: str
    to_state: str
    payload: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover
        return (f"[{self.timestamp.isoformat(timespec='milliseconds')}] "
                f"{self.from_state} --{self.event}--> {self.to_state}")


@dataclass
class _Rule:
    from_state: str
    event: str
    to_state: str
    guard: Guard | None = None


@dataclass
class _Callbacks:
    on_enter: list[EnterCb] = field(default_factory=list)
    on_exit: list[ExitCb] = field(default_factory=list)


class StateMachine:
    """线程安全的轻量状态机。

    所有读 / 写操作通过内部 ``RLock`` 保护，可安全用于「主线程驱动状态转换 +
    心跳线程读取状态」的场景。RLock 允许同一线程重入，适合回调嵌套触发。
    """

    def __init__(self, initial_state: str, *, history_limit: int = 100) -> None:
        if not initial_state:
            raise ValueError("initial_state must be non-empty")
        self._initial_state: str = initial_state
        self._state: str = initial_state
        self._rules: list[_Rule] = []
        self._callbacks: dict[str, _Callbacks] = {}
        self._history: Deque[TransitionRecord] = deque(maxlen=max(1, history_limit))
        self._lock = threading.RLock()

    # ----- properties ---------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def initial_state(self) -> str:
        return self._initial_state

    @property
    def history(self) -> list[TransitionRecord]:
        with self._lock:
            return list(self._history)

    @property
    def is_terminal(self) -> bool:
        with self._lock:
            return self._state in TaskState.TERMINAL

    # ----- declaration --------------------------------------------------

    def add_transition(
        self,
        from_state: str,
        event: str,
        to_state: str,
        *,
        guard: Guard | None = None,
    ) -> None:
        if not (from_state and event and to_state):
            raise ValueError("from_state, event, to_state must all be non-empty")
        with self._lock:
            self._rules.append(_Rule(from_state, event, to_state, guard))

    def add_callbacks(
        self,
        state: str,
        *,
        on_enter: EnterCb | None = None,
        on_exit: ExitCb | None = None,
    ) -> None:
        with self._lock:
            cb = self._callbacks.setdefault(state, _Callbacks())
            if on_enter is not None:
                cb.on_enter.append(on_enter)
            if on_exit is not None:
                cb.on_exit.append(on_exit)

    # ----- queries ------------------------------------------------------

    def can_trigger(self, event: str, payload: dict[str, Any] | None = None) -> bool:
        with self._lock:
            return self._find_rule(event, payload) is not None

    def legal_events(self) -> list[str]:
        with self._lock:
            return [r.event for r in self._rules if r.from_state == self._state]

    # ----- transitions --------------------------------------------------

    def trigger(self, event: str, payload: dict[str, Any] | None = None) -> bool:
        """触发一次状态转换。返回 True 表示状态确实发生了改变。"""
        # 注意：必须把「查规则」「改状态」「写历史」「触发回调」放在同一个锁里，
        # 否则心跳线程可能读到中间状态。同时回调本身会在锁内执行（同步语义），
        # 这对调试更友好——回调抛错能被状态机立刻捕获。
        with self._lock:
            rule = self._find_rule(event, payload)
            if rule is None:
                logger.debug("state transition rejected: state={} event={}",
                             self._state, event)
                return False

            prev = self._state
            self._fire_callbacks_locked(prev, "on_exit", payload)
            self._state = rule.to_state
            self._history.append(
                TransitionRecord(
                    timestamp=datetime.now(),
                    from_state=prev,
                    event=event,
                    to_state=rule.to_state,
                    payload=payload,
                )
            )
            logger.debug("state {} --{}--> {}", prev, event, rule.to_state)
            self._fire_callbacks_locked(self._state, "on_enter", payload)
            return True

    def reset(self, to_state: str | None = None) -> None:
        """回到初始状态（或显式目标）。"""
        target = to_state or self._initial_state
        with self._lock:
            if target == self._state:
                return
            self._fire_callbacks_locked(self._state, "on_exit", None)
            prev = self._state
            self._state = target
            self._history.append(
                TransitionRecord(
                    timestamp=datetime.now(),
                    from_state=prev,
                    event="RESET",
                    to_state=target,
                )
            )
            logger.debug("state RESET: {} --> {}", prev, target)
            self._fire_callbacks_locked(self._state, "on_enter", None)

    # ----- internals ----------------------------------------------------

    def _find_rule(self, event: str, payload: dict[str, Any] | None) -> _Rule | None:
        for rule in self._rules:
            if rule.from_state == self._state and rule.event == event:
                if rule.guard is None or rule.guard(self._state, payload):
                    return rule
        return None

    def _fire_callbacks_locked(
        self,
        state: str,
        kind: str,
        payload: dict[str, Any] | None,
    ) -> None:
        """注意：调用方必须已持有 _lock。"""
        cb = self._callbacks.get(state)
        if cb is None:
            return
        cbs = cb.on_enter if kind == "on_enter" else cb.on_exit
        for fn in cbs:
            try:
                fn(state, payload)
            except Exception as exc:  # 回调不应破坏状态机
                logger.warning("state callback error (state={}, kind={}): {}",
                               state, kind, exc)


# ============================================================
# Factory
# ============================================================


def build_default_state_machine(
    initial_state: str = TaskState.IDLE,
    *,
    log_transitions: bool = True,
) -> StateMachine:
    """构造 Phase 1 / 2 / 3 通用任务状态机。

    把所有转换规则从 ``main.py`` 内聚到这里，main 只负责传入配置项。
    转换规则：
        IDLE      --START-->          RUNNING
        RUNNING   --PAUSE-->          PAUSED
        PAUSED    --RESUME-->         RUNNING
        RUNNING   --COMPLETE-->       COMPLETED
        RUNNING   --FAIL-->           FAILED
        PAUSED    --FAIL-->           FAILED
        RUNNING   --ABORT-->          ABORTING
        PAUSED    --ABORT-->          ABORTING
        ABORTING  --FINALIZE_ABORT--> ABORTED
        {COMPLETED, FAILED, ABORTED} --RESET--> IDLE
    """
    sm = StateMachine(initial_state)

    sm.add_transition(TaskState.IDLE, TaskEvent.START, TaskState.RUNNING)
    sm.add_transition(TaskState.RUNNING, TaskEvent.PAUSE, TaskState.PAUSED)
    sm.add_transition(TaskState.PAUSED, TaskEvent.RESUME, TaskState.RUNNING)
    sm.add_transition(TaskState.RUNNING, TaskEvent.COMPLETE, TaskState.COMPLETED)
    sm.add_transition(TaskState.RUNNING, TaskEvent.FAIL, TaskState.FAILED)
    sm.add_transition(TaskState.PAUSED, TaskEvent.FAIL, TaskState.FAILED)
    sm.add_transition(TaskState.RUNNING, TaskEvent.ABORT, TaskState.ABORTING)
    sm.add_transition(TaskState.PAUSED, TaskEvent.ABORT, TaskState.ABORTING)
    sm.add_transition(TaskState.ABORTING, TaskEvent.FINALIZE_ABORT, TaskState.ABORTED)
    sm.add_transition(TaskState.COMPLETED, TaskEvent.RESET, TaskState.IDLE)
    sm.add_transition(TaskState.FAILED, TaskEvent.RESET, TaskState.IDLE)
    sm.add_transition(TaskState.ABORTED, TaskEvent.RESET, TaskState.IDLE)

    if log_transitions:
        sm.add_callbacks(
            TaskState.RUNNING,
            on_enter=lambda s, p: logger.info("state machine -> {}", s),
        )
        sm.add_callbacks(
            TaskState.COMPLETED,
            on_enter=lambda s, p: logger.success("state machine -> {}", s),
        )
        sm.add_callbacks(
            TaskState.FAILED,
            on_enter=lambda s, p: logger.error(
                "state machine -> {} ({})", s, (p or {}).get("reason", "")),
        )
        sm.add_callbacks(
            TaskState.ABORTED,
            on_enter=lambda s, p: logger.warning(
                "state machine -> {} ({})", s, (p or {}).get("reason", "")),
        )

    return sm