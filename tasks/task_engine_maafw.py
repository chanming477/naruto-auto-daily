"""tasks.task_engine_maafw — MaaFramework 版的任务引擎 wrapper(2026-07-02)。

跟 ``tasks.task_engine.TaskEngine`` 并行存在,**不破坏旧实现**。

设计:
    - ``MaaTaskEngine.run_task(task_id)``:
        1. ``resolve_entry(task_id)`` → narutomobile entry 名
        2. ``MaTaskerSingleton.run_task(entry)`` → job
        3. ``MaaEventSink.to_task_result(success=...)`` → ``core.task_result.TaskResult``
        4. 失败时调 ``recovery_mgr.on_task_failed`` (P2-6 2026-07-18 删 RecoveryManager
           后, ``recovery_mgr`` 仅为 ``Any`` 类型占位参数,保留向后兼容)
        5. 返回 TaskResult

    - ``MaaTaskEngine.run_daily(task_ids)``:
        - 顺序跑 task_ids,任务间调 ``_back_to_home`` 恢复主页
        - 产出 ``RunReport``(本地 dataclass, P2-6 2026-07-18 删 core.scheduler 后内联)

CLI 入口:
    ``python main.py --daily-maafw`` 跑 config/schedule.json 的全部 task(走 maafw)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from core.task_result import TaskResult, TaskStatus
from maafw_bridge import (
    MaaEventSink,
    MaaTaskerSingleton,
    get_tasker,
    resolve_entry,
)

if TYPE_CHECKING:
    from core.config_manager import ConfigManager


_LOG = logger.bind(component="task_engine_maafw")


# ----- RunReport (P2-6 2026-07-18 从 core.scheduler 移入) --------------------


@dataclass
class RunReport:
    """单次 daily run 的统计报告。

    P2-6: 从 core.scheduler.RunReport 移入(原模块已删)。字段保持向后兼容。
    """

    started_at: datetime
    finished_at: datetime | None = None
    task_results: list[TaskResult] = field(default_factory=list)
    aborted: bool = False
    abort_reason: str = ""

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.task_results if r.is_success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.task_results if r.is_failure)

    @property
    def skip_count(self) -> int:
        return sum(1 for r in self.task_results if r.is_skip)

    @property
    def best_effort_count(self) -> int:
        return sum(1 for r in self.task_results if r.is_best_effort)

    @property
    def has_best_effort(self) -> bool:
        return self.best_effort_count > 0

    @property
    def total_count(self) -> int:
        return len(self.task_results)

    @property
    def duration_sec(self) -> float:
        if not self.finished_at:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()

if TYPE_CHECKING:
    from core.config_manager import ConfigManager


_LOG = logger.bind(component="task_engine_maafw")


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
    ) -> RunReport:
        """顺序跑一批 task。

        Args:
            task_ids: 要跑的任务 ID 列表。None 时按 ``cfg.tasks.tasks`` 字典顺序。
            stop_on_failure: 任一 task 失败时是否中止。

        Returns:
            ``RunReport`` (本地 dataclass, 见本模块顶部定义)。
        """
        if task_ids is None:
            # 2026-07-15 fix: 用 list_supported_entries 避免同 entry 重复运行
            from maafw_bridge import list_supported_entries
            task_ids = list_supported_entries()

        report = RunReport(started_at=datetime.now())
        log = _LOG
        log.info("run_daily: {} task(s) stop_on_failure={}", len(task_ids), stop_on_failure)

        for i, tid in enumerate(task_ids):
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
                break
            # P0-2 任务间恢复:除最后一个 task 外,跑 narutomobile 现有链回主页
            # 旧 TaskEngine.run_all 每个任务后 observe() + tap_home_button()
            # 新实现走 narutomobile 已有的 back_main_screen_before_task(17 个 recovery action)
            if i < len(task_ids) - 1:
                self._back_to_home()

        report.finished_at = datetime.now()
        log.info(
            "run_daily finished: total={} success={} fail={} aborted={}",
            report.total_count, report.success_count, report.fail_count, report.aborted,
        )
        return report

    def _back_to_home(self) -> None:
        """任务间恢复:跑 narutomobile back_main_screen_before_task 链回到主页。

        非致命:失败只记 warning,不中断 daily run。
        (替代旧 TaskEngine.run_all 后的 observe() + tap_home_button())
        """
        try:
            job = self._singleton.run_task("back_main_screen_before_task")
            detail = job.wait().get()
            status_obj = getattr(detail, "status", None)
            if not (status_obj and getattr(status_obj, "succeeded", False)):
                _LOG.warning("_back_to_home: did not succeed")
        except Exception as exc:
            _LOG.warning("_back_to_home failed (non-fatal): {}", exc)

    @staticmethod
    def print_report(report: RunReport) -> None:
        """打印 RunReport 总结(给 CLI 用)。"""
        print()
        print("=" * 70)
        print("MaaTaskEngine daily summary")
        print("=" * 70)
        print(f"  started_at:  {report.started_at.isoformat()}")
        print(f"  finished_at: {report.finished_at.isoformat() if report.finished_at else '-'}")
        print(f"  total:       {report.total_count}")
        print(f"  success:     {report.success_count}")
        print(f"  best_effort: {report.best_effort_count}")  # P1-2 新增
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