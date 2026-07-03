"""core.scheduler — 顺序任务调度器。

设计要点：
- 启动时从 ConfigManager.tasks 加载注册表,按 display_order 升序排序,
  过滤掉 ``enabled=False`` 的项。
- Phase 1 注册表为空 → 调度器表现为「无任务」，但骨架仍要完整跑通：
  状态机会从 IDLE → RUNNING → COMPLETED，心跳定时器正常运转。
- 每个任务通过 ``BaseTask.execute(ctx)`` 调用，失败重试 / 跳过 / 中止策略
  全部由配置项驱动，Scheduler 本身只负责顺序、超时、间隔与日志。
- 状态机是单一真相：Scheduler 不维护自己的运行状态，只在事件触发时
  转发到 ctx.state_machine。
- ``run()`` 与 ``run_single()`` 走同一个 ``_execute_pipeline`` 路径，
  共享 START/COMPLETE/FAIL 状态转换 + 心跳线程。

公开 API：
    Scheduler(ctx: ExecutionContext)
        .run() -> RunReport
        .run_single(task_id: str) -> TaskResult | None
        .request_abort(reason: str) -> None
"""

from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from core.base_task import BaseTask, ExecutionContext, TaskResult, TaskStatus
from core.config_manager import TaskRegistryConfig
from core.state_machine import TaskEvent

__all__ = ["Scheduler", "RunReport", "TaskFactory"]


# ============================================================
# RunReport
# ============================================================


@dataclass
class RunReport:
    started_at: datetime
    finished_at: datetime | None = None
    task_results: list[TaskResult] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""

    @property
    def success_count(self) -> int:
        # SUCCESS + BEST_EFFORT 都算"调度链成功"(向后兼容)
        return sum(
            1 for r in self.task_results
            if r.status in (TaskStatus.SUCCESS, TaskStatus.BEST_EFFORT)
        )

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.task_results if r.status == TaskStatus.FAIL)

    @property
    def skip_count(self) -> int:
        return sum(1 for r in self.task_results if r.status == TaskStatus.SKIP)

    @property
    def retry_count(self) -> int:
        return sum(1 for r in self.task_results if r.status == TaskStatus.RETRY)

    @property
    def best_effort_count(self) -> int:
        """P0 增量(2026-07-02): best-effort task 数量(mail/liveness/recruit/activity/
        daily_signin/weekly_signin 等"接受降级"的 task)。

        **监控关键指标**:
            - ``best_effort_count == 0`` → 所有 task 完美成功
            - ``best_effort_count > 0`` → 有 task 失败被掩盖,需要人工审查 message 字段
        """
        return sum(1 for r in self.task_results if r.is_best_effort)

    @property
    def has_best_effort(self) -> bool:
        """快速判断有没有"降级成功"task。GUI/调度器/邮件警报可订阅此属性。"""
        return self.best_effort_count > 0

    @property
    def total_count(self) -> int:
        return len(self.task_results)

    @property
    def duration_sec(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()

    def summary(self) -> str:
        return (
            f"RunReport(tasks={self.total_count} success={self.success_count} "
            f"[best_effort={self.best_effort_count}] fail={self.fail_count} "
            f"skip={self.skip_count} retry={self.retry_count} "
            f"aborted={self.aborted} duration={self.duration_sec:.2f}s)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_sec": round(self.duration_sec, 3),
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "totals": {
                "total": self.total_count,
                "success": self.success_count,
                "best_effort": self.best_effort_count,
                "fail": self.fail_count,
                "skip": self.skip_count,
                "retry": self.retry_count,
                "has_best_effort": self.has_best_effort,
            },
            "tasks": [r.to_dict() for r in self.task_results],
        }


# ============================================================
# Task factory
# ============================================================


class TaskFactory:
    """从 ``task_registry.yaml`` 中的 ``task_class`` 字段导入 Python 类。"""

    @staticmethod
    def build(task_id: str, entry: Any) -> BaseTask:
        path = getattr(entry, "task_class", "") or ""
        if not path:
            # Phase 1 容错：没有 task_class 也能产生一个占位任务
            return _NoopTask(task_id)
        try:
            module_name, class_name = path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
        except Exception as exc:
            raise ImportError(
                f"failed to import task class '{path}' for task '{task_id}': {exc}"
            ) from exc
        if not isinstance(cls, type) or not issubclass(cls, BaseTask):
            raise TypeError(f"task class '{path}' must subclass BaseTask")
        instance = cls()
        instance.task_id = task_id
        return instance


class _NoopTask(BaseTask):
    """注册表里有任务定义但还没写代码时的占位。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.name = f"[Phase 1 占位] {task_id}"

    def run(self, ctx: ExecutionContext) -> TaskResult:
        log = ctx.bind_logger(self.task_id)
        log.info("noop task executed (no task_class registered)")
        return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS,
                          message="noop (phase 1 placeholder)")


# ============================================================
# Scheduler
# ============================================================


class Scheduler:
    """顺序任务调度器。"""

    def __init__(self, ctx: ExecutionContext) -> None:
        self.ctx = ctx
        self.cfg = ctx.config.app.scheduler
        # V2: 不缓存 TaskRegistryConfig 引用,每次访问都从 ctx.config.tasks 读最新。
        # 这样 ConfigManager.reload() 后 Scheduler 立即看到新配置,不需要重建。
        self._ctx = ctx
        self._abort_flag = threading.Event()

    # ----- public -------------------------------------------------------

    def request_abort(self, reason: str = "user requested abort") -> None:
        self._abort_flag.set()
        self.ctx.state_machine.trigger(TaskEvent.ABORT, {"reason": reason})
        logger.warning("abort requested: {}", reason)

    def is_aborted(self) -> bool:
        """是否已请求中止。

        公开 API,让 ``TaskEngine`` 等包装层在循环里检查中止状态
        而不需要直接触碰 ``_abort_flag``(P1-ARCH-03: 私有属性泄露)。
        """
        return self._abort_flag.is_set()

    def run(self) -> RunReport:
        """按注册表顺序执行全部启用的任务。"""
        report = RunReport(started_at=datetime.now())
        self._abort_flag.clear()

        # 1) 启动心跳（START 在 _execute_pipeline 内触发）
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(heartbeat_stop,),
            daemon=True,
            name="scheduler-heartbeat",
        )
        heartbeat_thread.start()

        try:
            # 2) 预热等待
            warmup = float(self.cfg.startup_warmup_sec)
            if warmup > 0:
                logger.info("startup warmup: {:.1f}s", warmup)
                if self._sleep_interruptible(warmup):
                    report.aborted = True
                    report.abort_reason = "aborted during warmup"
                    self.ctx.state_machine.trigger(TaskEvent.ABORT,
                                                   {"reason": report.abort_reason})
                    return report

            # 3) 装载任务实例
            tasks = self._instantiate_tasks()
            if not tasks:
                logger.info("no tasks in registry; scheduler run completes with 0 tasks")

            # 4) 进入 RUNNING
            self.ctx.state_machine.trigger(TaskEvent.START, {"run_id": self.ctx.run_id})

            # 5) 顺序执行（每个任务独立走 _execute_pipeline）
            any_fail = False
            for task in tasks:
                if self.is_aborted():
                    report.aborted = True
                    report.abort_reason = "abort flag set before task"
                    break

                result = self._execute_pipeline(task)
                report.task_results.append(result)

                if result.status == TaskStatus.FAIL:
                    any_fail = True
                    if self.cfg.stop_on_failure:
                        logger.error("stop_on_failure=True, aborting scheduler after: {}",
                                     result.task_id)
                        report.aborted = True
                        report.abort_reason = f"stop_on_failure after {result.task_id}"
                        break

                if self.is_aborted():
                    report.aborted = True
                    report.abort_reason = "abort flag set after task"
                    break

                # 任务间隔
                if self.cfg.inter_task_delay_sec > 0 and task is not tasks[-1]:
                    if self._sleep_interruptible(float(self.cfg.inter_task_delay_sec)):
                        report.aborted = True
                        report.abort_reason = "aborted during inter-task delay"
                        break

            # 6) 状态机收尾
            if report.aborted:
                self.ctx.state_machine.trigger(TaskEvent.FINALIZE_ABORT,
                                               {"reason": report.abort_reason})
            elif any_fail and self.cfg.stop_on_failure:
                self.ctx.state_machine.trigger(TaskEvent.FAIL,
                                               {"reason": "stop_on_failure triggered"})
            else:
                if any_fail:
                    logger.warning("some tasks failed but stop_on_failure=False; "
                                   "scheduler still completes")
                self.ctx.state_machine.trigger(TaskEvent.COMPLETE)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
            report.finished_at = datetime.now()

        logger.success("scheduler finished: {}", report.summary())
        return report

    def run_single(self, task_id: str) -> TaskResult | None:
        """只跑一个指定任务(单任务模式)。

        与 ``run()`` 的差异(P0-REG-01 文档同步):
            - **不**做 ``startup_warmup_sec`` 预热,直接进任务
            - **不**触发全局 START — 复用 ``_execute_pipeline``,在需要时
              触发 START (payload=``task_id``);``run()`` 触发 START (payload=``run_id``)
            - **会**在入口清空 ``_abort_flag``,所以前一次被中止的 run 不会
              污染本次调用
            - **不**处理任务间隔(``inter_task_delay_sec``)
            - **不**应用 ``stop_on_failure`` 中止后续 — 既然只跑一个,无后续可中止

        共用 ``_execute_pipeline``:
            START (若 ``state != RUNNING``) → 跑任务 → COMPLETE / FAIL
            同时启停心跳线程(``scheduler-heartbeat-single``)。

        Returns:
            ``None`` 仅在「task_id 不在注册表」时返回;
            任务执行失败会返回 ``status=FAIL`` 的 ``TaskResult``。
        """
        self._abort_flag.clear()

        tasks = self._instantiate_tasks()
        target = next((t for t in tasks if t.task_id == task_id), None)
        if target is None:
            logger.error("task_id '{}' not found in registry", task_id)
            return None

        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(heartbeat_stop,),
            daemon=True,
            name="scheduler-heartbeat-single",
        )
        heartbeat_thread.start()
        try:
            return self._execute_pipeline(target)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)

    # ----- shared pipeline (用于 run() 和 run_single()) -----------------

    def _execute_pipeline(self, task: BaseTask) -> TaskResult:
        """单任务的完整生命周期：进入 RUNNING（如尚未在）→ 跑任务 → COMPLETE/FAIL。

        如果调度器已在 RUNNING（多任务场景下），不会重复触发 START。
        """
        # 确保进入 RUNNING
        if self.ctx.state_machine.state != "RUNNING":
            self.ctx.state_machine.trigger(TaskEvent.START, {"task_id": task.task_id})

        result = self._run_with_timeout(task)

        if result.status == TaskStatus.SUCCESS:
            self.ctx.state_machine.trigger(TaskEvent.COMPLETE, {"task_id": task.task_id})
        elif result.status == TaskStatus.FAIL:
            self.ctx.state_machine.trigger(TaskEvent.FAIL, {
                "task_id": task.task_id, "reason": result.message,
            })
        # SKIP / RETRY 不直接驱动状态机（RUNNING 保持）
        return result

    # ----- internals ----------------------------------------------------

    def _instantiate_tasks(self) -> list[BaseTask]:
        """从 ``ConfigManager.tasks`` 加载任务实例,按 ``display_order`` 升序排列。

        V2: 唯一排序来源是 ``display_order``,旧的 ``schedule_order`` 字段已删除。
        ``enabled=False`` 的任务被跳过;实例化失败的任务被跳过 + log error。
        """
        # 按 display_order 升序,task_id 作为二级稳定排序键(同 order 时确定性)
        registry = self._ctx.config.tasks  # 每次访问最新
        sorted_ids = sorted(
            registry.tasks.keys(),
            key=lambda tid: (registry.tasks[tid].display_order, tid),
        )

        tasks: list[BaseTask] = []
        for tid in sorted_ids:
            entry = registry.tasks.get(tid)
            if entry is None:
                continue
            if not entry.enabled:
                logger.debug("task '{}' disabled, skip", tid)
                continue
            try:
                instance = TaskFactory.build(tid, entry)
            except Exception as exc:
                logger.error("failed to build task '{}': {}", tid, exc)
                continue
            tasks.append(instance)
        logger.info("scheduler loaded {} task(s): {}", len(tasks),
                    [t.task_id for t in tasks])
        return tasks

    def _run_with_timeout(self, task: BaseTask) -> TaskResult:
        """带超时执行一个任务。

        ⚠ 已知限制（P0-STABLE-02）：
        超时走的是「主线程 join(timeout) + 工作线程 daemon=True」模式。
        超时到达后 join 立即返回，但工作线程不会立即终止——它持有的 GDI 句柄、
        文件锁、阻塞 IO 等都可能让它一直跑到自然结束。Python 解释器退出时才
        会强制清理 daemon 线程。
        因此在 Phase 1 任务极少的情况下可接受，但 Phase 2+ 必须引入
        「cooperative cancellation」机制（BaseTask 暴露 ``ctx.is_cancelled``
        标志，任务内部周期性检查）。这是已知技术债。
        """
        timeout = int(self.cfg.task_timeout_sec)
        log = self.ctx.bind_logger(task.task_id)
        if timeout <= 0:
            return task.execute(self.ctx)
        log.debug("task timeout = {}s", timeout)

        result_box: dict[str, Any] = {}

        def _runner() -> None:
            try:
                result_box["result"] = task.execute(self.ctx)
            except Exception as exc:  # execute 自身已捕获，这里仅防线程问题
                log.error("task thread crashed: {}", exc)
                result_box["result"] = None

        th = threading.Thread(target=_runner, name=f"task-{task.task_id}", daemon=True)
        th.start()
        th.join(timeout=timeout)
        if th.is_alive():
            log.error(
                "task '{}' exceeded timeout ({}s); abandoning daemon thread "
                "(see P0-STABLE-02 in code comments)",
                task.task_id, timeout,
            )
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAIL,
                message=f"timeout after {timeout}s (daemon thread abandoned)",
            )
        result = result_box.get("result")
        if result is None:
            return TaskResult(task_id=task.task_id, status=TaskStatus.FAIL,
                              message="task thread crashed")
        return result

    def _sleep_interruptible(self, seconds: float) -> bool:
        """可被打断的 sleep；返回 True 表示被打断。"""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.is_aborted():
                return True
            time.sleep(min(0.2, end - time.monotonic()))
        return False

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        interval = max(1, int(self.cfg.heartbeat_interval_sec))
        while not stop.wait(interval):
            # StateMachine.state 内部已加锁，心跳线程安全读取
            state = self.ctx.state_machine.state
            logger.info("♥ heartbeat | state={} done={} run_id={}",
                        state, len(self.ctx.task_results), self.ctx.run_id)