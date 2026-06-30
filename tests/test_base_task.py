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