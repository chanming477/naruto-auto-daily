"""test_base_task.py — BaseTask 生命周期 / pre_check / retry。"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pytest

from core.base_task import BaseTask, ExecutionContext, TaskResult, TaskStatus
from core.config_manager import ConfigManager
from core.state_machine import build_default_state_machine
from core.window_manager import WindowProfile


class _CountingTask(BaseTask):
    """测试用任务：记录 run() 被调用次数。"""

    def __init__(self, fail_times: int = 0) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.call_count = 0

    def run(self, ctx: ExecutionContext) -> TaskResult:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL,
                              message=f"forced fail #{self.call_count}")
        return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS,
                          message="ok")


class _PreCheckFailsTask(BaseTask):
    def pre_check(self, ctx: ExecutionContext) -> bool:
        return False

    def run(self, ctx: ExecutionContext) -> TaskResult:
        raise AssertionError("run() should not be called when pre_check fails")


class _RunRaisesTask(BaseTask):
    def run(self, ctx: ExecutionContext) -> TaskResult:
        raise RuntimeError("kaboom")


@pytest.fixture
def ctx(tmp_path: Path) -> ExecutionContext:
    cfg = ConfigManager(tmp_path, auto_load=True)
    profile = WindowProfile()
    # 不实例化真正的 WindowManager（platform-dependent）；用 SimpleNamespace
    from types import SimpleNamespace
    wm = SimpleNamespace(find_target=lambda: None, wait_for_target=lambda **kw: None)
    sm = build_default_state_machine("IDLE", log_transitions=False)
    from core.screenshot_manager import ScreenshotManager
    smgr = ScreenshotManager.__new__(ScreenshotManager)  # skip __init__
    smgr.window_manager = wm
    smgr.config = cfg.app.screenshot
    smgr.project_root = tmp_path
    smgr.output_dir = tmp_path / "screenshots"
    smgr.output_dir.mkdir(exist_ok=True)

    return ExecutionContext(
        config=cfg,
        window_manager=wm,
        screenshot_manager=smgr,
        state_machine=sm,
    )


def test_success_first_try(ctx):
    t = _CountingTask(fail_times=0)
    result = t.execute(ctx)
    assert result.is_success
    assert result.attempts == 1
    assert t.call_count == 1


def test_retry_then_success(ctx):
    t = _CountingTask(fail_times=2)
    result = t.execute(ctx)
    assert result.is_success
    assert result.attempts == 3
    assert t.call_count == 3


def test_retry_exhausted_then_fail(ctx):
    t = _CountingTask(fail_times=10)  # 永远 fail
    result = t.execute(ctx)
    assert result.status == TaskStatus.FAIL
    # 默认 max_retries=2 → 初次 + 2 次重试 = 3 次
    assert result.attempts == 3
    assert t.call_count == 3


def test_pre_check_skip(ctx):
    t = _PreCheckFailsTask()
    result = t.execute(ctx)
    assert result.status == TaskStatus.SKIP
    assert ctx.task_results[-1] is result


def test_run_exception_caught(ctx):
    t = _RunRaisesTask()
    result = t.execute(ctx)
    assert result.status == TaskStatus.FAIL
    assert "kaboom" in result.message


def test_retry_disabled(ctx):
    t = _CountingTask(fail_times=1)
    t.retryable = False
    result = t.execute(ctx)
    assert result.status == TaskStatus.FAIL
    assert result.attempts == 1


def test_cleanup_always_runs(ctx):
    """cleanup 即便失败也要运行。"""
    calls = {"cleanup": 0, "pre_check": 0}

    class _T(BaseTask):
        def run(self, ctx):
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS)

        def cleanup(self, ctx, result):
            calls["cleanup"] += 1

        def pre_check(self, ctx):
            calls["pre_check"] += 1
            return True

    t = _T()
    t.execute(ctx)
    assert calls["cleanup"] == 1
    assert calls["pre_check"] == 1


def test_result_recorded_in_context(ctx):
    t = _CountingTask()
    t.execute(ctx)
    assert len(ctx.task_results) == 1
    assert ctx.task_results[0].task_id == t.task_id


# ============================================================
# BEST_EFFORT 测试(P0 修复 2026-07-02)
# 防止"两次 pipeline 失败后返 SUCCESS 掩盖故障"问题回归
# ============================================================


class _BestEffortTask(BaseTask):
    """第一次返回 FAIL,重试后返回 BEST_EFFORT(模拟 best-effort task 实际行为)。"""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def run(self, ctx: ExecutionContext) -> TaskResult:
        self.call_count += 1
        if self.call_count == 1:
            return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL,
                              message="first attempt failed")
        return TaskResult(task_id=self.task_id, status=TaskStatus.BEST_EFFORT,
                          message="best-effort: accept degraded success")


class _DirectBestEffortTask(BaseTask):
    """直接返回 BEST_EFFORT(不重试)。"""

    def run(self, ctx: ExecutionContext) -> TaskResult:
        return TaskResult(task_id=self.task_id, status=TaskStatus.BEST_EFFORT,
                          message="direct best-effort")


def test_best_effort_status_is_distinct_from_success(ctx):
    """BEST_EFFORT 必须有独立 status 字符串,不能和 SUCCESS 混用。"""
    t = _DirectBestEffortTask()
    result = t.execute(ctx)
    assert result.status == TaskStatus.BEST_EFFORT
    assert result.status != TaskStatus.SUCCESS
    assert result.status != TaskStatus.FAIL
    # 监控语义:is_best_effort 标志位打开
    assert result.is_best_effort is True
    # 向后兼容:is_success 仍为 True(Scheduler 继续跑下一个 task)
    assert result.is_success is True
    # 不算失败
    assert result.is_failure is False


def test_best_effort_after_retry(ctx):
    """第一次 FAIL → 重试 → BEST_EFFORT。attempts=2,status=BEST_EFFORT。"""
    t = _BestEffortTask()
    result = t.execute(ctx)
    assert result.status == TaskStatus.BEST_EFFORT
    assert result.attempts == 2
    assert t.call_count == 2
    assert "best-effort" in result.message


def test_run_report_best_effort_count():
    """RunReport.best_effort_count 必须能区分"完美成功"和"降级成功"。

    P2-6 (2026-07-18): RunReport 从 core.scheduler 移到 tasks.task_engine_maafw。
    """
    from tasks.task_engine_maafw import RunReport
    results = [
        TaskResult(task_id="a", status=TaskStatus.SUCCESS, message="ok"),
        TaskResult(task_id="b", status=TaskStatus.BEST_EFFORT, message="degraded"),
        TaskResult(task_id="c", status=TaskStatus.FAIL, message="failed"),
        TaskResult(task_id="d", status=TaskStatus.BEST_EFFORT, message="degraded2"),
    ]
    report = RunReport(started_at=datetime.now(), task_results=results)
    # success_count = SUCCESS + BEST_EFFORT(向后兼容:调度链不再阻塞)
    assert report.success_count == 3      # a (SUCCESS) + b + d (BEST_EFFORT)
    assert report.best_effort_count == 2  # b + d 是降级成功
    assert report.fail_count == 1         # c
    assert report.has_best_effort is True
    # is_success property 应该把 SUCCESS + BEST_EFFORT 都算"成功"
    assert results[0].is_success is True
    assert results[1].is_success is True
    assert results[2].is_success is False