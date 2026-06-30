"""logging_ext — Phase 4 日志扩展(纯日志上下文,不参与业务)。

子模块:
    - ``run_context``   RunContext context manager(state_before/state_after/elapsed_ms 绑定)
"""

from logging_ext.run_context import RunContext

__all__ = ["RunContext"]
