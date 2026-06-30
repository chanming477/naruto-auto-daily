"""tasks.task_engine — Scheduler 业务包装层(严格轻量)。

V2 职责范围(严格限制):
    1. 代码级任务注册表(优先级高于 YAML 自动加载)
    2. 每个任务前自动调 ``CommonActions.ensure_state(HOME)``
    3. 每个任务后自动调 ``CommonActions.go_home()``
    4. ``stop()`` 转发到 ``Scheduler.request_abort``
    5. (P1-ARCH-02) 在 ``__init__`` 时把 ``common_actions`` 挂到
       ``ctx.common_actions`` — 任务的 pre_check / recover 直接从这里取,
       取消 ``cfg._phase3_deps`` 私有属性 hack。

V2 严禁实现:
    - 任务排序 / 调度(由 ``core.scheduler.Scheduler`` 负责)
    - 任务构建(由 ``Scheduler.TaskFactory.build`` 负责)
    - 任务依赖分析(本项目不做)
    - 重试 / 超时 / enabled 过滤(由 Scheduler / BaseTask 负责)
    - 复杂的优先级 / 并发管理

依赖:
    - core.scheduler.Scheduler (复用)
    - core.base_task.BaseTask / TaskResult / ExecutionContext
    - core.scheduler.RunReport
    - tasks.common_actions.CommonActions
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from core.base_task import BaseTask, TaskResult, TaskStatus

if TYPE_CHECKING:
    from core.base_task import ExecutionContext
    from core.scheduler import RunReport, Scheduler
    from tasks.common_actions import CommonActions

__all__ = ["TaskEngine"]


class TaskEngine:
    """Scheduler 的业务包装层。

    Args:
        ctx: ``core.base_task.ExecutionContext``(Phase 1 唯一上下文)。
            **本类的 ``__init__`` 会自动把 ``common_actions`` 挂到
            ``ctx.common_actions``**(P1-ARCH-02),让任务在 ``pre_check`` /
            ``recover`` 里能直接拿到。
        common_actions: 跨任务导航库(必传,run_task 前后用它做 ensure_state/go_home)。

    Notes:
        - ``register_task`` 提供的 task_class **优先级高于** YAML 注册表里的同名任务。
        - ``run_task`` 前后的 ensure_state / go_home 都是「尽力回」语义,
          失败不阻塞任务结果(TaskResult 由 ``BaseTask.execute`` 决定)。
        - ``run_all`` 是简单 for 循环,**不做**任何调度决策(顺序由 ``task_ids`` 决定,
          None 时按 ``cfg.tasks.tasks`` 字典插入顺序,Python 3.7+ dict 保序)。
        - 中止检查走 ``Scheduler.is_aborted()`` 公开 API(P1-ARCH-03),
          不再触碰 ``_abort_flag`` 私有属性。
    """

    def __init__(
        self,
        ctx: "ExecutionContext",
        common_actions: "CommonActions",
    ) -> None:
        # 复用 Phase 1 的 Scheduler,不重写任何调度逻辑
        from core.scheduler import Scheduler  # 延迟 import 避免循环依赖测试

        self._ctx = ctx
        self._scheduler: Scheduler = Scheduler(ctx)
        self._common_actions = common_actions
        self._custom_registry: dict[str, type[BaseTask]] = {}
        self._logger = logger.bind(component="task_engine")

        # P1-ARCH-02: 通过 ExecutionContext 注入,而不是 cfg._phase3_deps 私有属性 hack。
        # 这样业务任务(pre_check / recover)从标准 DI 容器 ctx 拿,测试也直接对 ctx 注入。
        ctx.common_actions = common_actions
        self._logger.debug("injected ctx.common_actions = {}", type(common_actions).__name__)

    # ----- code-level registry (优先级高于 YAML) -----------------------

    def register_task(self, task_id: str, task_class: type[BaseTask]) -> None:
        """代码级注册任务。

        Args:
            task_id: 任务唯一 ID。
            task_class: BaseTask 子类。

        Notes:
            注册后,``run_task(task_id)`` 优先用此处的 task_class 实例化;
            YAML 里的同名 task_class 仅作 fallback(实际不会用到,因为本方法覆盖)。
        """
        if not isinstance(task_class, type) or not issubclass(task_class, BaseTask):
            raise TypeError(
                f"task_class for '{task_id}' must subclass BaseTask, "
                f"got {type(task_class).__name__}"
            )
        self._custom_registry[task_id] = task_class
        self._logger.debug("registered task '{}' from {}", task_id, task_class.__module__)

    def unregister_task(self, task_id: str) -> bool:
        """移除已注册任务。

        Returns:
            True 表示成功移除,False 表示 task_id 不在注册表里。
        """
        existed = self._custom_registry.pop(task_id, None) is not None
        if existed:
            self._logger.debug("unregistered task '{}'", task_id)
        return existed

    def is_registered(self, task_id: str) -> bool:
        """返回 task_id 是否在代码级注册表里。"""
        return task_id in self._custom_registry

    # ----- execution -------------------------------------------------------

    def run_task(self, task_id: str) -> TaskResult | None:
        """执行单个任务。

        流程:
            1. ``CommonActions.ensure_state(HOME)`` — 尽力,不阻塞
            2. ``Scheduler.run_single(task_id)`` — 复用 Phase 1 调度(走 BaseTask.execute)
            3. ``CommonActions.go_home()`` — 任务后回到主页,尽力

        Args:
            task_id: 要执行的任务 ID。

        Returns:
            TaskResult,或 None(当 task_id 在 Scheduler 和代码注册表里都找不到时)。
        """
        log = self._logger
        log.info("run_task: '{}'", task_id)

        # 1. 前置:确保在主页(尽力)
        if not self._common_actions.ensure_state(self._target_state()):
            log.warning("run_task: ensure_state(HOME) failed; continue anyway")

        # 2. 复用 Scheduler 的执行(START/执行/COMPLETE/FAIL + 心跳 + 超时)
        result = self._scheduler.run_single(task_id)
        if result is None:
            log.error("run_task: Scheduler.run_single returned None for '{}'", task_id)
            return None

        # 3. 后置:回到主页(尽力)
        if not self._common_actions.go_home():
            log.warning("run_task: go_home failed; continue anyway")

        return result

    def run_all(self, task_ids: list[str] | None = None) -> "RunReport":
        """顺序执行任务列表。

        Args:
            task_ids: 要执行的任务 ID 列表;None 时按 ``cfg.tasks.tasks`` 的
                字典顺序(不排序)。

        Returns:
            ``RunReport``:包含每个任务的 TaskResult,以及 abort 状态。

        P1-3 (2026-06-29): 任务结束后调 ``observe()`` 验证状态。
            如果不在 HOME,**不**调 ``go_home()``(会按 BACK 触发"是否退出游戏"弹窗)。
            改用模板化的 ``tap_home_button()`` 安全回主页。
        """
        from core.scheduler import RunReport

        if task_ids is None:
            task_ids = list(self._ctx.config.tasks.tasks.keys())
        log = self._logger
        log.info("run_all: {} task(s): {}", len(task_ids), task_ids)

        report = RunReport(started_at=datetime.now())
        stop_on_failure = bool(self._ctx.config.app.scheduler.stop_on_failure)
        log.debug("run_all stop_on_failure={}", stop_on_failure)

        for tid in task_ids:
            # P1-ARCH-03: 用公开 API,不再读私有属性
            if self._scheduler.is_aborted():
                report.aborted = True
                report.abort_reason = "abort flag set before task"
                break

            result = self.run_task(tid)
            if result is None:
                # task_id 不存在;继续下一个(不计入 report)
                log.warning("run_all: skip unknown task '{}'", tid)
                continue

            report.task_results.append(result)

            # P1-3: 任务后状态验证 + 安全回主页(模板化,不按 BACK)
            try:
                from state.game_state import GameState
                current = self._common_actions.observe()
                if current != GameState.HOME:
                    log.warning(
                        "run_all: task '{}' ended at {} (not HOME), tap_home_button()",
                        tid, current,
                    )
                    # 用模板化 tap_home_button (不按 BACK,安全)
                    if not self._common_actions.tap_home_button():
                        log.warning(
                            "run_all: tap_home_button failed after task '{}', "
                            "continuing anyway", tid,
                        )
            except Exception as exc:  # noqa: BLE001 - 验证失败不阻塞任务流
                log.warning("run_all: post-task state validation failed: {}", exc)

            if result.status == TaskStatus.FAIL and stop_on_failure:
                report.aborted = True
                report.abort_reason = f"stop_on_failure after {tid}"
                break

        report.finished_at = datetime.now()
        log.info(
            "run_all finished: tasks={} success={} fail={} aborted={}",
            report.total_count, report.success_count, report.fail_count, report.aborted,
        )
        return report

    def stop(self) -> None:
        """请求中止当前/下一次 run。

        转发到 ``Scheduler.request_abort``。
        """
        self._scheduler.request_abort("TaskEngine.stop()")

    # ----- internals -------------------------------------------------------

    @staticmethod
    def _target_state() -> "GameState":  # type: ignore[name-defined]
        """ensure_state 的目标状态。集中在此便于以后改成可配置。"""
        # 延迟 import 避免 tasks 模块顶层依赖 state_machine
        from state.game_state import GameState

        return GameState.HOME
