"""state_machine.game_state_machine — 游戏页面状态机(业务级)。

V3 职责边界声明(Phase 4 收紧):
    本模块 **仅负责游戏页面状态管理**:
        - HOME / POPUP / LOADING / UNKNOWN
    本模块 **禁止处理程序生命周期状态**(IDLE / RUNNING / COMPLETED / FAILED 等),
    那属于 ``core.state_machine``。

两个状态机的关系:
    - ``core.state_machine`` — 运行级:Scheduler / BaseTask 驱动 START/PAUSE/COMPLETE/FAILED。
    - ``state_machine.game_state_machine`` (本模块) — 业务级:CommonActions / PageRecognizer
      记录当前游戏页面。
    两者 **不互相 import、不互相调用、不维护同一状态**。

V3 关键变更(Phase 4):
    - ``recover()`` 签名收紧:删除 ``probe`` 参数,只接受 ``RecoveryManager``。
      真正的恢复动作(截图 + RetryManager + CommonActions)全部在 RecoveryManager 里。
      ``GameStateMachine.recover()`` 只做「状态切换入口」。

职责:
    维护当前 ``GameState`` 状态,提供 3 个核心动作:
        - ``update_state(new_state)`` — 直接切换状态,记日志
        - ``go_home()`` — 强制回到 HOME(等价于 update_state(HOME))
        - ``recover(recovery_manager)`` — UNKNOWN 时调用 RecoveryManager 恢复,
          把结果 update 到状态机;RecoveryManager 缺失时仅 warning + 不动状态

设计要点:
    - 状态机本身不调用 PageRecognizer / ADBClient / CommonActions;
      真正的恢复逻辑在 ``recovery.recovery_manager`` 里,避免循环依赖。
    - 状态变更全部走 loguru 记录,便于回溯。
    - 简单实现:一个 dataclass + 三个方法 + 历史列表;不引入第三方 FSM 库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from state.game_state import GameState

if TYPE_CHECKING:
    from recovery.recovery_manager import RecoveryManager

__all__ = ["GameStateMachine", "StateTransition"]


@dataclass(frozen=True)
class StateTransition:
    """一次状态切换的记录。

    Attributes:
        timestamp: 切换时刻。
        from_state: 切换前的状态。
        to_state: 切换后的状态。
        source: 切换来源,如 ``"detect_state"`` / ``"go_home"`` / ``"recovery_manager"``。
    """

    timestamp: datetime
    from_state: GameState
    to_state: GameState
    source: str

    def __str__(self) -> str:
        return (
            f"[{self.timestamp.isoformat(timespec='milliseconds')}] "
            f"{self.from_state.value} --({self.source})--> {self.to_state.value}"
        )


class GameStateMachine:
    """游戏业务级状态机。

    单一真相: ``self._current``;切换通过 ``update_state`` 唯一入口。
    """

    def __init__(
        self,
        initial: GameState = GameState.UNKNOWN,
        *,
        history_limit: int = 100,
    ) -> None:
        """初始化。

        Args:
            initial: 初始状态,默认 ``UNKNOWN``(Phase 2 demo 启动时尚未截图)。
            history_limit: 历史切换记录保留上限。
        """
        if not isinstance(initial, GameState):
            raise TypeError(f"initial must be a GameState, got {type(initial).__name__}")
        self._initial: GameState = initial
        self._current: GameState = initial
        self._history_limit: int = max(1, int(history_limit))
        self._history: list[StateTransition] = []
        logger.bind(component="fsm").info("GameStateMachine initialized: initial={}", initial.value)

    # ----- properties ---------------------------------------------------

    @property
    def current_state(self) -> GameState:
        return self._current

    @property
    def initial_state(self) -> GameState:
        return self._initial

    @property
    def history(self) -> list[StateTransition]:
        """返回历史切换记录的浅拷贝(防止外部修改内部列表)。"""
        return list(self._history)

    @property
    def is_known(self) -> bool:
        """是否处于已识别状态(非 UNKNOWN)。"""
        return GameState.is_recognized(self._current)

    # ----- public actions ----------------------------------------------

    def update_state(self, new_state: GameState, *, source: str = "external") -> bool:
        """切换到 ``new_state``。

        Args:
            new_state: 目标状态;必须是 ``GameState`` 枚举。
            source: 切换来源,用于日志(例如 ``"detect_state"`` / ``"manual"``)。

        Returns:
            True 表示状态确实发生了变化;False 表示与当前状态相同(不算切换)。
        """
        if not isinstance(new_state, GameState):
            logger.bind(component="fsm").error(
                "update_state rejected: new_state must be GameState, got {}",
                type(new_state).__name__,
            )
            return False

        if new_state == self._current:
            logger.bind(component="fsm").debug("update_state noop: current={}", self._current.value)
            return False

        prev = self._current
        self._current = new_state
        record = StateTransition(
            timestamp=datetime.now(),
            from_state=prev,
            to_state=new_state,
            source=source,
        )
        self._history.append(record)
        # 保留最近 N 条
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit :]

        log = logger.bind(component="fsm")
        if new_state == GameState.UNKNOWN:
            log.warning("FSM: {} -> UNKNOWN ({})", prev.value, source)
        else:
            log.success("FSM: {} -> {} ({})", prev.value, new_state.value, source)
        return True

    def go_home(self) -> bool:
        """强制切换到 ``HOME``。

        Returns:
            True 表示状态确实发生了变化;False 表示当前已经在 HOME。
        """
        return self.update_state(GameState.HOME, source="go_home")

    def recover(
        self,
        recovery_manager: "RecoveryManager | None" = None,
    ) -> GameState:
        """UNKNOWN → 状态切换入口(真正的恢复动作全部在 RecoveryManager)。

        V3 (Phase 4 收紧):
            - 删除 V2 的 ``probe`` 参数 — 不再做「自己 probe + fallback initial_state」,
              避免和 ``RecoveryManager.recover_unknown`` 双重恢复。
            - 只接受 ``recovery_manager``;缺失时 warning + 不动状态(不抛)。

        Args:
            recovery_manager: ``RecoveryManager`` 实例,负责真正的恢复动作。
                None 时仅记录 warning,状态保持 UNKNOWN(让调用方决定下一步)。

        Returns:
            最终的 ``GameState``(可能仍是 UNKNOWN)。
        """
        if self._current != GameState.UNKNOWN:
            logger.bind(component="fsm").debug(
                "recover skipped: current={} (not UNKNOWN)", self._current.value
            )
            return self._current

        log = logger.bind(component="fsm")

        if recovery_manager is None:
            log.warning(
                "recover: current=UNKNOWN but no RecoveryManager; "
                "state stays UNKNOWN (see Phase 4 RecoveryManager)"
            )
            return self._current

        log.warning("recover: entering recovery flow via RecoveryManager")
        target = recovery_manager.recover_unknown()
        if target is not None and target != GameState.UNKNOWN:
            self.update_state(target, source="recovery_manager")
        return self._current

    def reset(self) -> None:
        """回到 initial_state,并清空历史。"""
        prev = self._current
        self._current = self._initial
        self._history.clear()
        logger.bind(component="fsm").info("FSM reset: {} -> {}", prev.value, self._initial.value)
