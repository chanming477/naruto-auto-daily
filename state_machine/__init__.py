"""state_machine package · Phase 2 游戏状态枚举 + 状态机。

包含:
    game_state          — GameState 枚举(HOME / POPUP / LOADING / UNKNOWN,从 state/ 合并)
    game_state_machine  — update_state / go_home / recover

注意区分:
    - core.state_machine (Phase 1) — 通用任务运行级状态机(IDLE/RUNNING/...)
    - state_machine (本模块)       — 游戏业务级状态机(HOME/UNKNOWN/...)

二者语义不同,刻意不互相依赖。
"""

__all__ = ["game_state", "game_state_machine"]
__version__ = "0.7.0"
