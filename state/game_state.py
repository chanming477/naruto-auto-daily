"""state.game_state — 游戏页面状态枚举。

枚举项含义:
    HOME      — 主界面(任务入口所在的根页面)
    POPUP     — 任意弹窗(网络错误 / 公告 / 更新提示 / 奖励领取 等)
    LOADING   — 加载 / 转场画面(动画进行中)
    UNKNOWN   — 未识别(任意识别方法都没匹配到可信结果)

Phase 2 仅交付这 4 个状态。Phase 3+ 才会扩展到 RECRUIT / MISSION / SHOP 等
具体页面。增加新枚举项时必须同步:
    1) resources/templates/<state_name>/ 目录
    2) recognizer.page_recognizer 的 templates 映射
    3) core.config_manager.AppConfig.game_state 的允许值
"""

from __future__ import annotations

from enum import Enum

__all__ = ["GameState"]


class GameState(str, Enum):
    """游戏页面状态。

    继承 ``str`` 是为了与 Pydantic v2 / JSON 序列化兼容,
    让 YAML 里直接写 ``initial_state: "HOME"`` 也能正确反序列化。
    """

    HOME = "HOME"
    POPUP = "POPUP"
    LOADING = "LOADING"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def all(cls) -> tuple[str, ...]:
        """所有枚举值的字符串元组,用于校验 / 日志展示。"""
        return tuple(s.value for s in cls)

    @classmethod
    def is_recognized(cls, value: "GameState | str") -> bool:
        """返回是否处于已识别状态(HOME/POPUP/LOADING),用于判断是否进 recover。"""
        v = value.value if isinstance(value, GameState) else value
        return v in {cls.HOME.value, cls.POPUP.value, cls.LOADING.value}
