"""recovery.retry_manager — 统一重试策略(Phase 4)。

职责:
    包装任意 ``fn(*args, **kwargs)`` 调用,在 ``retryable_exceptions`` 内做最多
    ``max_attempts`` 次重试,支持指数退避。可观测:每次 attempt 记录 loguru。

设计要点:
    - 与 ``BaseTask.execute`` 的重试职责不冲突:
        * RetryManager = **函数级** 重试(任意同步调用);
        * BaseTask.execute = **任务级** 重试(整任务一次跑完后再跑一次);
        两者粒度不同,RetryManager 适合「单次 ADB 命令」/「单次截图」级别。
    - 与 ``ADBClient.screenshot`` 内部的 ``retry_count`` 循环不冲突:
        * ADBClient 内部是「同命令短间隔重试」;
        * RetryManager 是「外层策略包装」,提供指数退避 + 统一日志 + 统计;
        调用方选择是否走 ``RetryManager.execute_adb_action(adb, "screenshot")``。
    - 不做: 状态机更新、截图落盘、RecoveryManager 调用。
      RetryManager 是纯函数包装层,业务由调用方编排。

公开 API:
    RetryPolicy
        .from_config(cfg: ConfigManager) -> RetryPolicy
    RetryManager
        .execute_with_retry(fn, *args, **kwargs) -> T
        .execute_adb_action(adb, method_name, *args, **kwargs) -> ActionResult
    execute_with_retry(fn, *args, **kwargs) -> T   # 顶层便捷函数
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from loguru import logger

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from device.adb_client import ADBClient

T = TypeVar("T")

__all__ = ["RetryPolicy", "RetryManager", "execute_with_retry"]


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略(不可变)。

    Attributes:
        max_attempts: 最大尝试次数(含首次);<=1 表示不重试。
        delay_seconds: 第一次重试前等待秒数;指数退避时按 2^(n-1) 翻倍。
        exponential_backoff: True 时 delay 按 2^(n-1) 翻倍,False 时固定。
        max_delay_seconds: 退避上限。
        retryable_exceptions: 允许重试的异常类名字符串列表(空 = 全部重试)。
            字符串而非异常类,避免 ``recovery`` 模块反向依赖 ``device.adb_client`` 内部类型。
    """

    max_attempts: int = 3
    delay_seconds: float = 1.0
    exponential_backoff: bool = True
    max_delay_seconds: float = 30.0
    retryable_exceptions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.delay_seconds < 0:
            raise ValueError(f"delay_seconds must be >= 0, got {self.delay_seconds}")
        if self.max_delay_seconds < self.delay_seconds:
            raise ValueError(
                f"max_delay_seconds ({self.max_delay_seconds}) must be >= "
                f"delay_seconds ({self.delay_seconds})",
            )

    @classmethod
    def from_config(cls, cfg: "ConfigManager") -> "RetryPolicy":
        """从 ``ConfigManager.app.retry`` 构造策略。

        Args:
            cfg: 项目级 ConfigManager(已 reload 过)。

        Returns:
            RetryPolicy 实例。
        """
        r = cfg.app.retry
        return cls(
            max_attempts=int(r.max_attempts),
            delay_seconds=float(r.delay_seconds),
            exponential_backoff=bool(r.exponential_backoff),
            max_delay_seconds=float(r.max_delay_seconds),
            retryable_exceptions=tuple(r.retryable_exceptions or []),
        )

    def delay_for(self, attempt: int) -> float:
        """第 ``attempt`` 次重试前的等待秒数(``attempt=1`` 表示第一次重试)。

        Args:
            attempt: 1-indexed,表示「第 N 次重试」(1 = 第一次重试,首次调用前不 delay)。

        Returns:
            等待秒数,0 表示不等待。
        """
        if not self.exponential_backoff:
            return self.delay_seconds
        # 指数: delay * 2^(attempt-1),封顶 max_delay_seconds
        raw = self.delay_seconds * (2 ** max(0, attempt - 1))
        return min(raw, self.max_delay_seconds)

    def is_retryable(self, exc: BaseException) -> bool:
        """判断异常是否在重试白名单内。

        ``retryable_exceptions`` 为空 → 全部重试(默认);
        非空 → 只重试类名匹配的(避免重试明确不可恢复的异常如 ``KeyboardInterrupt``)。
        """
        if not self.retryable_exceptions:
            return True
        cls_name = type(exc).__name__
        # 兼容子类的处理: 任意祖先类名命中即视为可重试
        for mro_cls in type(exc).__mro__:
            if mro_cls.__name__ in self.retryable_exceptions:
                return True
        return cls_name in self.retryable_exceptions


class RetryManager:
    """重试执行器(单一职责: 函数级重试)。

    Notes:
        - 无状态:同一实例可被多线程复用(policy 是 frozen dataclass)。
        - 不持有上下文:不引入第二套 ExecutionContext。
        - 不修改业务状态:仅 loguru 日志。
    """

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        """初始化。

        Args:
            policy: 重试策略;None 时使用默认 ``RetryPolicy()``(3 次 / 1s / 指数退避)。
        """
        self._policy = policy or RetryPolicy()
        self._logger = logger.bind(component="retry_manager")

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    # ----- public -----------------------------------------------------

    def execute_with_retry(
        self,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """执行 ``fn(*args, **kwargs)``,失败时按 ``policy`` 重试。

        Args:
            fn: 任意可调用对象。
            *args / **kwargs: 透传给 ``fn``。

        Returns:
            ``fn`` 的返回值(只要最后一次重试成功)。

        Raises:
            最后一次失败的异常(若 ``max_attempts`` 耗尽)。
            不可重试的异常(命中白名单过滤)立即透传,不重试。
        """
        last_exc: BaseException | None = None
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                result = fn(*args, **kwargs)
                if attempt > 1:
                    self._logger.success(
                        "retry succeeded on attempt {}/{}: {}",
                        attempt, self._policy.max_attempts, _fn_name(fn),
                    )
                return result
            except BaseException as exc:
                last_exc = exc
                # KeyboardInterrupt 永远不重试(系统级中断)
                if isinstance(exc, KeyboardInterrupt):
                    raise
                if not self._policy.is_retryable(exc):
                    self._logger.warning(
                        "non-retryable exception, propagating: {}: {}",
                        type(exc).__name__, exc,
                    )
                    raise
                if attempt >= self._policy.max_attempts:
                    self._logger.error(
                        "retry exhausted ({} attempts): {}: {}",
                        self._policy.max_attempts, type(exc).__name__, exc,
                    )
                    raise
                delay = self._policy.delay_for(attempt)
                self._logger.warning(
                    "retry {}/{} after {}s: {}: {}",
                    attempt, self._policy.max_attempts, delay,
                    type(exc).__name__, exc,
                )
                if delay > 0:
                    time.sleep(delay)
        # 不应该到这里;防御性 raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("execute_with_retry: unexpected end of loop")

    def execute_adb_action(
        self,
        adb: "ADBClient",
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """真实调用链:包装 ``adb.<method_name>(*args, **kwargs)`` 走重试策略。

        这是 Phase 4 设计的「真实调用链」示例。
        ``ADBClient`` 本身**一行不动**;调用方选择走这条路径而不是裸调。

        Args:
            adb: ADBClient 实例(MagicMock / 真实都行)。
            method_name: ADBClient 上的方法名(如 ``"screenshot"`` / ``"tap"`` /
                ``"keyevent"``)。
            *args / **kwargs: 透传给 adb 方法。

        Returns:
            adb 方法的返回值(一般是 ``ActionResult``)。

        Raises:
            ``AttributeError`` — adb 上没有 ``method_name`` 方法。
            重试用尽后的最后一次异常。
        """
        if not hasattr(adb, method_name):
            raise AttributeError(
                f"ADBClient has no method '{method_name}'; "
                f"available: {[m for m in dir(adb) if not m.startswith('_')][:20]}",
            )
        fn = getattr(adb, method_name)
        self._logger.debug(
            "execute_adb_action: adb.{} via retry chain (policy=attempts={}, delay={}s)",
            method_name, self._policy.max_attempts, self._policy.delay_seconds,
        )
        return self.execute_with_retry(fn, *args, **kwargs)


# ----- 顶层便捷函数 ---------------------------------------------------


def execute_with_retry(
    fn: Callable[..., T],
    *args: Any,
    policy: RetryPolicy | None = None,
    **kwargs: Any,
) -> T:
    """顶层便捷函数,用默认 ``RetryManager`` 跑一次重试。

    Example:
        >>> from recovery import execute_with_retry
        >>> result = execute_with_retry(adb.screenshot, policy=RetryPolicy(max_attempts=5))
    """
    return RetryManager(policy=policy).execute_with_retry(fn, *args, **kwargs)


def _fn_name(fn: Callable[..., Any]) -> str:
    """取可调用对象的可读名(用于日志)。"""
    if hasattr(fn, "__name__"):
        return fn.__name__
    if hasattr(fn, "__class__"):
        return fn.__class__.__name__
    return repr(fn)
