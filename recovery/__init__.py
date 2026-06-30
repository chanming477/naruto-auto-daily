"""recovery — Phase 4 稳定性体系。

子模块:
    - ``retry_manager``   统一重试策略(RetryPolicy + RetryManager)
    - ``recovery_manager`` 4 个异常场景的统一恢复(UNKNOWN / POPUP / LOADING / ADB)
"""

from recovery.retry_manager import RetryManager, RetryPolicy, execute_with_retry
from recovery.recovery_manager import RecoveryManager

__all__ = [
    "RetryManager",
    "RetryPolicy",
    "execute_with_retry",
    "RecoveryManager",
]
