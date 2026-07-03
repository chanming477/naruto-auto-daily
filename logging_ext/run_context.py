"""logging_ext.run_context — 单次执行区间的日志上下文(Phase 4)。

职责(单一):
    进入时绑定 loguru 上下文(task_id / state_before / run_id) + 开始计时;
    退出时计算 elapsed_ms + 绑定 state_after(由调用方在 __exit__ 前 set) +
    写一条结构化 INFO/SUCCESS 日志。

设计要点 — Non-goals / Hard Limits(硬约束,不可违反):
    1. **不** import tasks / state / recovery / state_machine 任何业务模块
       (本文件只允许 import core.logger、stdlib typing、time、loguru)。
    2. **不**修改任何外部状态 — 只通过 ``__exit__`` 写一条 loguru 日志。
    3. **不**引入第二套 ExecutionContext — ``task_id`` / ``state_before`` /
       ``state_after`` 只用于 ``loguru.bind`` 字段,不参与任何业务判断。
    4. **不**调用 GameStateMachine / CommonActions / ADBClient / RecoveryManager。
    5. **不**实现 ``state_before`` / ``state_after`` 的「自动推断」— 它们由
       调用方在 ``__enter__`` / ``__exit__`` 时显式传入或显式 set。
    6. **不**做任何 IO(不写文件、不截图、不发网络请求)。
    7. **不**捕获异常改变控制流(异常照常向上抛;``__exit__`` 只 log 一行,
       不返回 True 吞掉异常)。

一句话:它是一个 loguru 绑定 + elapsed 计时 + 一次性 __exit__ log 行的
context manager,**不是新的业务层**。

公开 API:
    RunContext(task_id, state_before=None, level="INFO")
        .state_after        # 属性:__exit__ 之前可 set,__exit__ 时绑定
        .log                # 属性:绑定了 task_id 的 logger
        __enter__ / __exit__
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

__all__ = ["RunContext"]


class RunContext:
    """单次执行区间的日志上下文。

    Usage:
        with RunContext(task_id="daily_signin", state_before="UNKNOWN") as rc:
            rc.state_after = "HOME"
            rc.log.info("doing something")
        # __exit__ 自动 log 一行含 elapsed_ms + state_after

    Args:
        task_id: 任务 ID(必传,会绑到 loguru context)。
        state_before: 起始状态(可选,字符串或任意可 ``str()`` 的值)。
            仅做 loguru 绑定,不参与任何业务判断。
        level: 退出时打日志的级别,默认 INFO。失败时可由调用方在
            ``__exit__`` 前 set ``exit_level = "ERROR"`` 覆盖。
        extra: 其它想绑到 loguru context 的字段(可选)。

    Notes:
        - 嵌套使用:内层 ``__enter__`` 不会覆盖外层的 task_id 绑定;
          loguru 的 bind 行为是「合并」而非「替换」。
        - ``state_after`` / ``exit_level`` 是**仅有的**可写 attribute,
          其它业务 attr 在测试里通过 ``dir()`` 静态约束。
    """

    # 公开可写 attribute 集合(其它 attribute 一律私有,不让外部读)
    _PUBLIC_WRITE_ATTRS = frozenset({"state_after", "exit_level", "extra_fields"})

    def __init__(
        self,
        task_id: str,
        state_before: Any = None,
        *,
        level: str = "INFO",
        **extra: Any,
    ) -> None:
        self._task_id = str(task_id)
        self._state_before = state_before
        self._level = level
        self._extra = dict(extra) if extra else {}
        self._t0: float = 0.0
        self._log: Any = None
        # 公开可写 attribute
        self.state_after: Any = None
        self.exit_level: str = level
        self.extra_fields: dict[str, Any] = {}

    # ----- properties -------------------------------------------------

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def state_before(self) -> Any:
        return self._state_before

    @property
    def level(self) -> str:
        return self._level

    @property
    def log(self) -> Any:
        """绑定了 task_id / state_before 的 logger(``__enter__`` 之后才能用)。"""
        if self._log is None:
            raise RuntimeError(
                "RunContext.log is only available inside 'with' block; " "access it in __enter__ or later.",
            )
        return self._log

    @property
    def elapsed_ms(self) -> float:
        """从 __enter__ 到当前的毫秒数。"""
        if self._t0 == 0.0:
            return 0.0
        return (time.monotonic() - self._t0) * 1000.0

    # ----- context manager --------------------------------------------

    def __enter__(self) -> "RunContext":
        bind = {"task_id": self._task_id}
        if self._state_before is not None:
            bind["state_before"] = str(self._state_before)
        # extra 字段
        for k, v in self._extra.items():
            bind[k] = v
        self._log = logger.bind(**bind)
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed_ms = (time.monotonic() - self._t0) * 1000.0
        bind = {
            "elapsed_ms": round(elapsed_ms, 2),
            "state_after": str(self.state_after) if self.state_after is not None else None,
        }
        for k, v in self.extra_fields.items():
            bind[k] = v
        if exc_type is not None:
            bind["error_type"] = exc_type.__name__
            bind["error_message"] = str(exc_val)
        bound = logger.bind(**bind)
        msg = f"RunContext[{self._task_id}] finished in {elapsed_ms:.2f}ms"
        # 异常时升级为 ERROR,否则用 self.exit_level
        effective_level = "ERROR" if exc_type is not None else self.exit_level
        try:
            getattr(bound, effective_level.lower())(msg)
        except (AttributeError, ValueError):
            bound.info(msg)
        # 注意:不返回 True,异常照常向上抛(Non-goals #7)
