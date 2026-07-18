"""recognition.types — Phase 2 识别结果数据类。

按 Prompt 要求字段:
    state       — 识别到的游戏状态(GameState)
    confidence  — 置信度,0.0 - 1.0
    method      — 识别来源,如 "template_match" / "fallback"
    timestamp   — 识别时刻(本地时间,无时区)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from state_machine.game_state import GameState

__all__ = ["RecognitionResult"]


@dataclass(frozen=True)
class RecognitionResult:
    """单次页面识别的输出。

    Attributes:
        state: 识别出的游戏状态;若所有方法都失败则为 GameState.UNKNOWN。
        confidence: 置信度 [0.0, 1.0]。
        method: 识别方法标识;用于日志与排查:
            - ``"template_match:<state>:<template_name>"`` 模板匹配成功
            - ``"fallback:no_match"`` 所有方法失败
            - ``"fallback:empty_templates"`` 模板目录为空
        timestamp: 识别时刻。
    """

    state: GameState
    confidence: float
    method: str
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        # 强制约束:confidence 必须在 [0, 1],state 必须是合法枚举。
        # 违反约束立即抛错,避免脏数据传到上层。
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not isinstance(self.state, GameState):
            raise TypeError(f"state must be a GameState enum, got {type(self.state).__name__}")

    def is_recognized(self) -> bool:
        """是否识别到具体状态(非 UNKNOWN)。"""
        return self.state != GameState.UNKNOWN

    def to_dict(self) -> dict[str, object]:
        """序列化(供日志 / 测试断言)。"""
        return {
            "state": self.state.value,
            "confidence": round(self.confidence, 4),
            "method": self.method,
            "timestamp": self.timestamp.isoformat(timespec="milliseconds"),
        }
