"""agent.custom — CustomAction / CustomRecognition 注册 (Agent 模式)。

**Agent 模式 (2026-07-15 方案 A)**:
    - action.py: NonlinearSwipe / GoIntoEntryByGuide (用 @AgentServer.custom_action 装饰器)
    - reco.py: IsInNinjaGuide / IsCounterOverflow (占位,merged.json 暂不引用)

**Direct API 模式 (旧)**:
    - ``maafw_bridge.custom_actions`` (继承 CustomAction,Python 自己管 Resource)
    - ``maafw_bridge._actions_core`` (核心逻辑,两模式共用)

两套入口都调 ``maafw_bridge._actions_core`` 的核心函数,避免维护两份。
"""

from agent.utils.logger import get_agent_logger

_log = get_agent_logger()

# 显式 re-export
__all__ = [
    "action",
    "reco",
]
