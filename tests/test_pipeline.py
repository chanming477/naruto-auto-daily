"""test_pipeline.py — 端到端冒烟：build_context + scheduler.run + run_single。

跨平台（不依赖 Windows 后端）：把 WindowManager / ScreenshotManager 替换成
``SimpleNamespace``，但保留 ConfigManager / Logger / StateMachine /
Scheduler / BaseTask 的真实逻辑。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import logger as core_logger
from core.base_task import ExecutionContext
from core.config_manager import ConfigManager, TaskEntry
from core.scheduler import Scheduler, TaskFactory
from core.state_machine import build_default_state_machine

from tests.fixtures import GreetTask


@pytest.fixture
def ctx_with_registry(tmp_path: Path) -> tuple[ExecutionContext, Path]:
    cfg = ConfigManager(tmp_path, auto_load=False)
    cfg.save_default_configs()
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n"
        "  greet:\n"
        "    task_class: 'tests.fixtures.GreetTask'\n"
        "    enabled: true\n"
        "    display_order: 1\n"
        "    category: 'misc'\n",
        encoding="utf-8",
    )
    cfg.reload()

    core_logger.configure(cfg.app.logger, tmp_path)

    wm = SimpleNamespace(
        find_target=lambda: None,
        wait_for_target=lambda **kw: None,
        list_visible=lambda: [],
        activate=lambda h: True,
        close=lambda h: True,
        get_rect=lambda h: None,
    )
    smgr = SimpleNamespace(
        capture=lambda target=None: None,
        capture_gray=lambda target=None: None,
        capture_stable=lambda target=None, **kw: None,
        capture_and_save=lambda name, target=None, save_dir=None: None,
        crop=lambda image, x, y, w, h: None,
    )

    sm = build_default_state_machine("IDLE", log_transitions=True)
    ctx = ExecutionContext(
        config=cfg,
        window_manager=wm,
        screenshot_manager=smgr,
        state_machine=sm,
    )
    return ctx, tmp_path


def test_factory_builds_task():
    entry = TaskEntry(task_class="tests.fixtures.GreetTask")
    t = TaskFactory.build("greet", entry)
    assert t.task_id == "greet"
    assert isinstance(t, GreetTask)


def test_run_with_one_task(ctx_with_registry):
    ctx, _ = ctx_with_registry
    sch = Scheduler(ctx)
    report = sch.run()
    assert report.total_count == 1
    assert report.success_count == 1
    assert ctx.state_machine.state == "COMPLETED"


def test_run_single_with_one_task(ctx_with_registry):
    ctx, _ = ctx_with_registry
    sch = Scheduler(ctx)
    result = sch.run_single("greet")
    assert result is not None
    assert result.is_success
    # run_single 应该让状态机走到 COMPLETED（与 run() 一致）
    assert ctx.state_machine.state == "COMPLETED"


def test_run_single_unknown_task_returns_none(ctx_with_registry):
    ctx, _ = ctx_with_registry
    sch = Scheduler(ctx)
    result = sch.run_single("does_not_exist")
    assert result is None


def test_empty_registry_completes_cleanly(tmp_path):
    cfg = ConfigManager(tmp_path, auto_load=False)
    cfg.save_default_configs()
    core_logger.configure(cfg.app.logger, tmp_path)
    wm = SimpleNamespace(find_target=lambda: None, wait_for_target=lambda **kw: None)
    smgr = SimpleNamespace(capture=lambda target=None: None, capture_gray=lambda target=None: None)
    sm = build_default_state_machine("IDLE", log_transitions=True)
    ctx = ExecutionContext(config=cfg, window_manager=wm, screenshot_manager=smgr, state_machine=sm)

    sch = Scheduler(ctx)
    report = sch.run()
    assert report.total_count == 0
    assert sm.state == "COMPLETED"


def test_state_machine_reset_path(tmp_path):
    """P0-BUG-02: 状态机 reset 必须能回到 initial_state。"""
    sm = build_default_state_machine("IDLE", log_transitions=False)
    sm.trigger("START")
    sm.trigger("COMPLETE")
    assert sm.state == "COMPLETED"
    sm.reset()
    assert sm.state == "IDLE"
    assert sm.initial_state == "IDLE"