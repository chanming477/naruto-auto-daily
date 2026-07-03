"""tasks.task_engine_maafw — MaaFramework 版的任务引擎 wrapper(2026-07-02)。

跟 ``tasks.task_engine.TaskEngine`` 并行存在,**不破坏旧实现**。

设计:
    - ``MaaTaskEngine.run_task(task_id)``:
        1. ``resolve_entry(task_id)`` → narutomobile entry 名
        2. ``MaTaskerSingleton.run_task(entry)`` → job
        3. ``MaaEventSink.to_task_result(success=...)`` → ``core.base_task.TaskResult``
        4. 失败时调 ``RecoveryManager.on_task_failed``
        5. 返回 TaskResult

    - ``MaaTaskEngine.run_daily(task_ids)``:
        - 顺序跑 task_ids
        - 产出 ``RunReport``(同 core.scheduler.RunReport schema)

CLI 入口:
    ``python main.py --daily-maafw`` 跑 schemes/daily.json 的全部 task(走 maafw)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from core.base_task import TaskResult, TaskStatus
from maafw_bridge import (
    MaaEventSink,
    MaaTaskerSingleton,
    get_tasker,
    resolve_entry,
)

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.scheduler import RunReport


_LOG = logger.bind(component="task_engine_maafw")


# ----- RunReport 简化版(本模块自用) -----------------------------------------


class _SimpleRunReport:
    """轻量 RunReport,字段对齐 core.scheduler.RunReport。

    我们不直接 import core.scheduler.RunReport — 避免循环依赖 + 减少耦合。
    如果上层要统一的 RunReport,可 to_dict() 然后让 caller 适配。
    """

    def __init__(self) -> None:
        self.started_at = datetime.now()
        self.finished_at: datetime | None = None
        self.task_results: list[TaskResult] = []
        self.aborted = False
        self.abort_reason: str = ""

    @property
    def total_count(self) -> int:
        return len(self.task_results)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.task_results if r.is_success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.task_results if r.is_failure)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total": self.total_count,
            "success": self.success_count,
            "fail": self.fail_count,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "tasks": [r.to_dict() for r in self.task_results],
        }


# ----- Engine ----------------------------------------------------------------


class MaaTaskEngine:
    """MaaFramework 版 task engine。

    Args:
        cfg: ConfigManager 实例(读 ``cfg.app.maafw.*`` 配置)。
        recovery_mgr: 可选 RecoveryManager(失败时回调)。None 则不回调。
        qt_signal: 可选 Qt signal,接收 ``(task_id, node_name, detail_dict)`` 三元组
                  用于 GUI 细粒度进度。需要 signal 有 3 个 str 参数。
    """

    def __init__(
        self,
        cfg: "ConfigManager",
        recovery_mgr: Any = None,
        qt_signal: Any = None,
    ) -> None:
        self.cfg = cfg
        self.recovery = recovery_mgr
        self._qt_signal = qt_signal
        # 触发 init(cfg)(连 ADB + 加载 resource + bind tasker + 注册 custom actions)
        self._singleton = get_tasker()
        self._singleton.init(cfg)
        _LOG.info(
            "MaaTaskEngine ready: tasker.inited={}",
            self._singleton.tasker.inited,
        )

    def run_task(self, task_id: str) -> TaskResult | None:
        """跑单个 task(走 maafw entry)。

        Args:
            task_id: 我们 task_id(如 ``mail`` / ``recruit`` / ``group_signin``)。

        Returns:
            ``TaskResult`` 实例。task_id 在 TASK_MAPPING 找不到时返 None。
        """
        from maafw_bridge.pipeline_overrides import get_overrides_for_entry

        entry = resolve_entry(task_id)
        log = _LOG.bind(task_id=task_id, entry=entry)
        log.info("run_task: {} → entry={}", task_id, entry)

        sink = MaaEventSink(task_id=task_id, qt_signal=self._qt_signal)
        # 全局 tasker context sink(简化,不用 job-level sink)
        self._singleton.tasker.add_context_sink(sink)

        # v2 (2026-07-02): 用 narutomobile 模式的 pipeline_override
        # 5 个 entry (group/mission_office/point_race/weekly_win/stronghold) 走 override;
        # 其他 entry 走默认 merged.json。
        override = get_overrides_for_entry(entry)

        try:
            job = self._singleton.run_task(entry, override=override)
            detail = job.wait().get()
        except Exception as exc:
            log.error("run_task failed: {}", exc)
            if self.recovery is not None and hasattr(self.recovery, "on_task_failed"):
                try:
                    self.recovery.on_task_failed(task_id, str(exc))
                except Exception as cb_exc:  # noqa: BLE001
                    log.warning("recovery callback failed: {}", cb_exc)
            return sink.to_task_result(success=False, error=str(exc))

        # 判断 task 是否真成功 / StopTask 兜底 / 真失败
        status_obj = getattr(detail, "status", None)
        if status_obj is None:
            success: bool | str = False
            error = "no status returned"
        elif getattr(status_obj, "succeeded", False):
            success = True
            error = ""
        elif getattr(status_obj, "done", False):
            # Status.done=True 表示 pipeline 跑完但 .failed=True — narutomobile 兜底行为
            # 按 user profile "best-effort SUCCESS" 接受
            success = "stopped"
            error = "pipeline completed but status.failed=True (best-effort)"
        else:
            success = False
            error = "status.failed=True and not done"

        result = sink.to_task_result(success=success, error=error if success is False else "")
        log.info(
            "run_task done: status={} nodes={} elapsed={:.2f}s",
            result.status,
            sink.recognition_count + sink.action_count,
            result.duration_sec,
        )
        return result

    def run_daily(
        self,
        task_ids: list[str] | None = None,
        *,
        stop_on_failure: bool = False,
    ) -> _SimpleRunReport:
        """顺序跑一批 task。

        Args:
            task_ids: 要跑的任务 ID 列表。None 时按 ``cfg.tasks.tasks`` 字典顺序。
            stop_on_failure: 任一 task 失败时是否中止。

        Returns:
            ``_SimpleRunReport``(字段对齐 core.scheduler.RunReport)。
        """
        if task_ids is None:
            # cfg.tasks.tasks 是 BaseTask 注册表 dict(本项目旧架构)
            # 我们走 task_mapping 表
            from maafw_bridge import list_supported_tasks
            task_ids = list_supported_tasks()

        report = _SimpleRunReport()
        log = _LOG
        log.info("run_daily: {} task(s) stop_on_failure={}", len(task_ids), stop_on_failure)

        for tid in task_ids:
            if report.aborted:
                break
            result = self.run_task(tid)
            if result is None:
                log.warning("run_daily: skip unknown task '{}'", tid)
                continue
            report.task_results.append(result)
            if result.is_failure and stop_on_failure:
                report.aborted = True
                report.abort_reason = f"stop_on_failure after {tid}"

        report.finished_at = datetime.now()
        log.info(
            "run_daily finished: total={} success={} fail={} aborted={}",
            report.total_count, report.success_count, report.fail_count, report.aborted,
        )
        return report

    @staticmethod
    def print_report(report: _SimpleRunReport) -> None:
        """打印 RunReport 总结(给 CLI 用)。"""
        print()
        print("=" * 70)
        print("MaaTaskEngine daily summary")
        print("=" * 70)
        print(f"  started_at:  {report.started_at.isoformat()}")
        print(f"  finished_at: {report.finished_at.isoformat() if report.finished_at else '-'}")
        print(f"  total:       {report.total_count}")
        print(f"  success:     {report.success_count}")
        print(f"  fail:        {report.fail_count}")
        print(f"  aborted:     {report.aborted} ({report.abort_reason})")
        print()
        print(f"  {'task_id':<20s} {'status':<10s} {'duration':<10s} {'message':<40s}")
        print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*40}")
        for r in report.task_results:
            print(
                f"  {r.task_id:<20s} {r.status:<10s} "
                f"{r.duration_sec:<10.2f} {r.message[:40]:<40s}"
            )