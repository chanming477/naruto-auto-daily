"""device.types — Phase 2 设备动作结果数据类。

按 Prompt 要求字段:
    success     — 动作是否成功
    message     — 人类可读的状态 / 错误描述 (str)
    next_state  — 期望接下来进入的游戏状态(用于状态机驱动),None 表示无变化

扩展字段:
    payload     — 任意附带数据(目前主要用于 ``ADBClient.screenshot`` 承载 ndarray)。

设计要点:
    - Prompt 三件套字段保持原签名;``payload`` 是新增的第四字段,
      老调用方 ``ActionResult(True, "msg")`` / ``ActionResult(True, "msg", state)`` 仍兼容。
    - screenshot 成功时 ``payload`` 是 ``np.ndarray`` (BGR uint8) 的 **拷贝**(不是引用),
      避免调用方就地修改污染 ActionResult。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from state_machine.game_state import GameState

__all__ = ["ActionResult"]


@dataclass(frozen=True)
class ActionResult:
    """单次设备动作的结果。

    Attributes:
        success: 动作是否成功执行(命令返回码 0 / 截图非空 等)。
        message: 人类可读的状态描述;失败时是错误原因。
            类型固定为 ``str``(契约);截图 ndarray 不放在这里,改用 ``payload``。
        next_state: 期望的状态机下一步;``None`` 表示无变化。
        payload: 任意附带数据(目前由 ``ADBClient.screenshot`` 承载 ``np.ndarray`` 拷贝)。
    """

    success: bool
    message: str = ""
    next_state: "GameState | None" = None
    payload: Any = None

    def to_dict(self) -> dict[str, object]:
        """序列化(供日志 / 测试断言)。"""
        return {
            "success": self.success,
            "message": self.message,
            "next_state": self.next_state.value if self.next_state else None,
            "has_payload": self.payload is not None,
        }
