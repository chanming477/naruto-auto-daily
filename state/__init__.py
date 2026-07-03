"""state package · Phase 2 游戏状态层。

包含:
    game_state — 游戏页面的离散状态枚举
    types      — GameContext / 公共 dataclass

依赖方向: state 是底层模块,只依赖 core.config_manager 与标准库。
"""

__all__ = ["game_state", "types"]
__version__ = "0.2.0"
