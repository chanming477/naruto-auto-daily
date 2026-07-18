"""core.base_task — 任务抽象基类 + ExecutionContext + TaskResult。

设计要点：
- BaseTask 是任务实现的唯一基类，提供标准生命周期：
        pre_check -> run -> post_check -> cleanup
  每个钩子默认 no-op，子类按需覆盖。
- 真正干活的 ``run(ctx)`` 是抽象方法。
- ``execute(ctx)`` 是模板方法：负责异常捕获、重试、计时、日志。
  - 业务层（Scheduler）只调用 ``execute``，不直接调用 ``run``。
- ExecutionContext 把整个运行时需要的东西装一起（依赖注入容器）。
  任务通过 ctx 访问所有 Manager，避免在 Task 内部自己 import。

公开 API：
    ExecutionContext
    TaskResult, TaskStatus
    BaseTask（抽象）
"""

from __future__ import annotations

import abc
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from core.config_manager import ConfigManager
from core.screenshot_manager import ScreenshotManager
from core.state_machine import StateMachine
from core.window_manager import WindowInfo, WindowManager

__all__ = [
    "ExecutionContext",
    "TaskResult",
    "TaskStatus",
    "BaseTask",
]


# ============================================================
# TaskStatus & TaskResult
# ============================================================


class TaskStatus:
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    RETRY = "RETRY"
    SKIP = "SKIP"
    #: P0 增量(2026-07-02): task 主流程失败但选择"接受失败,返 SUCCESS 以避免阻塞
    #: 调度"(mail / liveness / recruit / activity / daily_signin / weekly_signin
    #: 等 best-effort 任务)。**新监控语义**:
    #:   - ``is_success`` 仍 = True(向后兼容,scheduler 继续跑下一个 task)
    #:   - ``is_best_effort`` = True(给监控/GUI/RunReport 一个"降级成功"信号)
    #:   - ``is_failure`` = False(不算 FAIL,不算 RETRY)
    #: RunReport 新增 ``best_effort_count`` 让"完美成功"vs"降级成功"可见。
    #:
    #: 原"两次 pipeline 失败后返 status=TaskStatus.SUCCESS 掩盖故障"问题已修复
    #: — 6 个 best-effort task 文件(mail/liveness/recruit/activity/daily_signin/
    #: weekly_signin)从 SUCCESS 改为 BEST_EFFORT。
    BEST_EFFORT = "BEST_EFFORT"


@dataclass
class TaskResult:
    task_id: str
    status: str = TaskStatus.FAIL
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_sec: float = 0.0
    attempts: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        # SUCCESS 与 BEST_EFFORT 都算"成功"(从调度链看都进入下一 task)
        return self.status in (TaskStatus.SUCCESS, TaskStatus.BEST_EFFORT)

    @property
    def is_failure(self) -> bool:
        return self.status in (TaskStatus.FAIL, TaskStatus.RETRY)

    @property
    def is_skip(self) -> bool:
        return self.status == TaskStatus.SKIP

    @property
    def is_best_effort(self) -> bool:
        """True 表示 task 失败但选择"接受降级"(原 SUCCESS 掩盖故障问题修复)。"""
        return self.status == TaskStatus.BEST_EFFORT

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_sec": round(self.duration_sec, 3),
            "attempts": self.attempts,
            "extra": self.extra,
        }


# ============================================================
# ExecutionContext
# ============================================================


@dataclass
class ExecutionContext:
    """单次运行共享状态容器（依赖注入）。"""

    config: ConfigManager
    window_manager: WindowManager
    screenshot_manager: ScreenshotManager
    state_machine: StateMachine
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = field(default_factory=datetime.now)
    task_results: list[TaskResult] = field(default_factory=list)
    current_task_id: str | None = None
    last_screenshot_path: str | None = None
    #: Phase 4 增量: 业务级游戏状态(由 ``recovery.RecoveryManager`` / ``GameStateMachine`` 写入)。
    #:
    #: 与 ``state_machine`` 字段(运行级状态机)区别:
    #:   - ``state_machine`` 是程序生命周期 (IDLE/RUNNING/COMPLETED/FAILED)
    #:   - ``last_state`` 是游戏页面 (HOME/POPUP/LOADING/UNKNOWN)
    #:
    #: 任务执行过程中可读、可写,用于跨任务的状态传递。
    last_state: "Any | None" = None
    #: Phase 4 增量: 最近一次业务级截图(ndarray BGR uint8)。
    #:
    #: ``last_screenshot_path`` 是文件路径(``capture_and_save`` 用);
    #: 本字段是内存中的 ndarray(``RecoveryManager`` 内部传递用,避免重复截图)。
    last_screenshot: "Any | None" = None

    def target_window(self) -> WindowInfo | None:
        return self.window_manager.find_target()

    def bind_logger(self, task_id: str):
        """返回一个绑定了 task_id / run_id 的 logger。"""
        return logger.bind(run_id=self.run_id, task_id=task_id)

    def record(self, result: TaskResult) -> None:
        self.task_results.append(result)
        if result.extra.get("screenshot_path"):
            self.last_screenshot_path = result.extra["screenshot_path"]


# ============================================================
# BaseTask
# ============================================================


class BaseTask(abc.ABC):
    """所有任务实现的基类。"""

    #: 任务唯一 ID（默认取类名小写）
    task_id: str = ""
    #: 显示名
    name: str = ""
    #: 默认是否启用
    enabled_by_default: bool = True
    #: 是否可重试
    retryable: bool = True
    #: 默认最大重试次数
    max_retries: int = 2

    def __init__(self) -> None:
        if not self.task_id:
            self.task_id = type(self).__name__.lower()
        if not self.name:
            self.name = type(self).__name__

    # ----- 生命周期 -----------------------------------------------------

    def pre_flight(self, ctx: ExecutionContext) -> bool:  # noqa: D401
        """任务执行前的「前置守护」(Phase 5 P0 增量,2026-07-15 简化)。

        在 ``pre_check`` 之前调用。默认实现直接返回 True。
        子类可覆盖做更细致的前置检查(例如特定分辨率校验)。

        **保证游戏前台** 这个职责已经从 Python 层移走:
            - 旧实现: ``CommonActions.ensure_game_in_foreground()``(在 Navigator 时代,
              每个 task 调一次,防上一任务把游戏切到后台)
            - 新实现: MaaFramework 的 merged.json pipeline 节点
              (e.g. ``IsInHomePage`` 在 ``on_error`` 走 ``ForceBackToHome``)负责
            - Python 端 pre_flight 不再 touch ADB

        原因: 旧 `tasks.common_actions` 已删除(2026-07-15),且 MaaFramework 的
        节点级 on_error 链比 Python pre_flight 更可靠(它有截图证据)。
        """
        return True

    def pre_check(self, ctx: ExecutionContext) -> bool:  # noqa: D401
        """任务执行前的可行性检查。返回 False 会被 Scheduler 当作 SKIP。"""
        return True

    def post_check(self, ctx: ExecutionContext, result: TaskResult) -> None:
        """任务执行后的验证钩子。默认 no-op。"""

    def cleanup(self, ctx: ExecutionContext, result: TaskResult) -> None:
        """无论成败都会跑的清理逻辑。默认 no-op。"""

    @abc.abstractmethod
    def run(self, ctx: ExecutionContext) -> TaskResult:
        """任务主逻辑。子类必须实现。"""

    # ----- 模板方法（业务层只调用本方法）-------------------------------

    def execute(self, ctx: ExecutionContext, *, max_retries: int | None = None) -> TaskResult:
        """带异常捕获 / 重试 / 计时 / 日志的标准执行入口。"""
        attempts_allowed = max(0, max_retries if max_retries is not None else self.max_retries)
        log = ctx.bind_logger(self.task_id)

        # pre_flight(P0 守护:游戏必须在前台)
        try:
            pf_ok = bool(self.pre_flight(ctx))
        except Exception as exc:
            log.error("pre_flight raised: {}\n{}", exc, traceback.format_exc())
            pf_ok = False
        if not pf_ok:
            log.warning("pre_flight failed -> SKIP (game not in foreground)")
            result = TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SKIP,
                message="pre_flight failed (game not in foreground)",
                started_at=datetime.now(),
                finished_at=datetime.now(),
            )
            ctx.record(result)
            ctx.current_task_id = None
            return result

        # pre_check
        try:
            ok = bool(self.pre_check(ctx))
        except Exception as exc:
            log.error("pre_check raised: {}\n{}", exc, traceback.format_exc())
            ok = False
        if not ok:
            log.warning("pre_check failed -> SKIP")
            result = TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SKIP,
                message="pre_check returned False",
                started_at=datetime.now(),
                finished_at=datetime.now(),
            )
            ctx.record(result)
            ctx.current_task_id = None
            return result

        # run with retries
        last_result: TaskResult | None = None
        final: TaskResult | None = None
        for attempt in range(1, attempts_allowed + 2):  # 初次 + 重试 N 次
            ctx.current_task_id = self.task_id
            started = datetime.now()
            log.info("[{}/{}] start", attempt, attempts_allowed + 1)
            t0 = time.monotonic()
            try:
                res = self.run(ctx)
                if not isinstance(res, TaskResult):
                    res = TaskResult(task_id=self.task_id,
                                     status=TaskStatus.FAIL,
                                     message=f"run() returned non-TaskResult: {type(res).__name__}")
            except Exception as exc:
                log.error("run raised: {}\n{}", exc, traceback.format_exc())
                res = TaskResult(task_id=self.task_id, status=TaskStatus.FAIL,
                                 message=f"exception: {exc}",
                                 started_at=started, finished_at=datetime.now())
            res.attempts = attempt
            res.started_at = res.started_at or started
            res.finished_at = datetime.now()
            res.duration_sec = time.monotonic() - t0

            # post_check
            try:
                self.post_check(ctx, res)
            except Exception as exc:
                log.warning("post_check raised: {}", exc)
                # 不改 res.status；仅记录
                res.extra.setdefault("post_check_warnings", []).append(str(exc))

            final = res
            # P0 修复(2026-07-02): BEST_EFFORT 也算"成功终止",不再重试
            # 之前 execute 只把 SUCCESS / SKIP 视作终止条件,导致 BEST_EFFORT 会被
            # 继续重试 max_retries 次 — 与"接受降级成功"语义相悖。
            if res.status in (TaskStatus.SUCCESS, TaskStatus.BEST_EFFORT, TaskStatus.SKIP):
                log.success("[{}] {} in {:.2f}s", self.task_id, res.status, res.duration_sec)
                break
            if not self.retryable or attempt > attempts_allowed:
                log.error("[{}] {} after {} attempt(s) in {:.2f}s: {}",
                          self.task_id, res.status, attempt, res.duration_sec, res.message)
                break
            log.warning("[{}] retrying ({}/{}): {}", self.task_id, attempt,
                        attempts_allowed, res.message)
            last_result = res

        if final is None:
            final = last_result or TaskResult(task_id=self.task_id,
                                               status=TaskStatus.FAIL,
                                               message="no result produced")

        # cleanup（永远跑）
        try:
            self.cleanup(ctx, final)
        except Exception as exc:
            log.warning("cleanup raised: {}", exc)

        ctx.record(final)
        ctx.current_task_id = None
        return final