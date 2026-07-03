"""state.types — Phase 2 类型定义。

V2 修正: 不再维护独立的 ``GameContext`` dataclass。
所有运行时状态都存在 ``core.base_task.ExecutionContext`` 里,``GameContext``
仅作为类型别名提供向后兼容。

为什么这么改:
    - Phase 1 的 ``ExecutionContext`` 已经是唯一运行上下文(config + window_manager +
      screenshot_manager + state_machine + run_id + task_results + ...)。
    - 维护两套上下文会引入状态不一致风险(哪个为真?)。
    - 业务级状态(HOME/UNKNOWN)由 ``state_machine.game_state_machine.GameStateMachine``
      直接持有,CommonActions 通过 ``game_sm.current_state`` 读取,不放在 ctx 里。
"""

from __future__ import annotations

from core.base_task import ExecutionContext as GameContext

__all__ = ["GameContext"]
