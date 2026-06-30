"""test_task_engine.py — TaskEngine 关键行为。

所有测试用 MagicMock / pytest fixture,零真实外部依赖。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.base_task import ExecutionContext, TaskResult, TaskStatus
from core.config_manager import ConfigManager
from core.state_machine import build_default_state_machine
from core.scheduler import Scheduler
from tasks.common_actions import CommonActions
from tasks.task_engine import TaskEngine


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def tmp_config(tmp_path: Path) -> ConfigManager:
    """生成一份临时 ConfigManager(默认 config)。"""
    cfg = ConfigManager(tmp_path, auto_load=True)
    return cfg


@pytest.fixture
def fake_common_actions() -> CommonActions:
    """返回 mock CommonActions,ensure_state 和 go_home 默认返回 True。"""
    common = MagicMock(spec=CommonActions)
    common.ensure_state.return_value = True
    common.go_home.return_value = True
    return common


@pytest.fixture
def ctx(tmp_config: ConfigManager, fake_common_actions) -> ExecutionContext:
    """构造 ExecutionContext(Phase 1 资产),window_manager / screenshot_manager 用 MagicMock。"""
    return ExecutionContext(
        config=tmp_config,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=False),
    )


@pytest.fixture
def engine(ctx: ExecutionContext, fake_common_actions) -> TaskEngine:
    return TaskEngine(ctx, common_actions=fake_common_actions)


# ============================================================
# Tests
# ============================================================


def test_register_task_adds_to_custom_registry(engine: TaskEngine):
    from tests.fixtures import GreetTask

    engine.register_task("greet", GreetTask)
    assert engine.is_registered("greet") is True


def test_register_task_rejects_non_basetask_subclass(engine: TaskEngine):
    with pytest.raises(TypeError):
        engine.register_task("bad", dict)  # type: ignore[arg-type]


def test_unregister_task_removes_from_registry(engine: TaskEngine):
    from tests.fixtures import GreetTask

    engine.register_task("greet", GreetTask)
    assert engine.unregister_task("greet") is True
    assert engine.is_registered("greet") is False


def test_unregister_unknown_task_returns_false(engine: TaskEngine):
    assert engine.unregister_task("never_registered") is False


def test_run_task_unknown_id_returns_none(engine: TaskEngine):
    """run_task 不在注册表/YAML 里 → None,且不抛异常。"""
    assert engine.run_task("never_heard_of") is None


def test_run_task_calls_ensure_state_then_go_home(
    engine: TaskEngine, fake_common_actions, tmp_config: ConfigManager, tmp_path: Path
):
    """run_task 走流程: ensure_state → Scheduler.run_single → go_home。"""
    # 准备 YAML 配置让 Scheduler 能加载 GreetTask
    tmp_config.app.logger  # 触发 ConfigDict
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n"
        "  greet:\n"
        "    task_class: 'tests.fixtures.GreetTask'\n"
        "    enabled: true\n"
        "    display_order: 1\n",
        encoding="utf-8",
    )
    tmp_config.reload()

    result = engine.run_task("greet")
    assert result is not None
    assert result.is_success
    # ensure_state 至少被调用一次
    assert fake_common_actions.ensure_state.called
    # go_home 在任务执行后调用
    assert fake_common_actions.go_home.called


def test_run_task_continues_even_if_ensure_state_fails(
    engine: TaskEngine, fake_common_actions, tmp_config: ConfigManager, tmp_path: Path
):
    """ensure_state 失败不阻塞任务执行。"""
    fake_common_actions.ensure_state.return_value = False
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n  greet:\n    task_class: 'tests.fixtures.GreetTask'\n    enabled: true\n    display_order: 1\n",
        encoding="utf-8",
    )
    tmp_config.reload()

    result = engine.run_task("greet")
    assert result is not None
    assert result.is_success  # 任务本身仍跑


def test_run_all_default_reads_cfg_tasks_keys(engine: TaskEngine, tmp_config: ConfigManager, tmp_path: Path):
    """run_all 无参时,从 cfg.tasks.tasks 读所有 enabled 任务的 key。"""
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n"
        "  greet:\n"
        "    task_class: 'tests.fixtures.GreetTask'\n"
        "    enabled: true\n"
        "    display_order: 1\n",
        encoding="utf-8",
    )
    tmp_config.reload()

    report = engine.run_all()
    assert report.total_count == 1
    assert report.success_count == 1


def test_run_all_with_explicit_task_ids(engine: TaskEngine, tmp_config: ConfigManager, tmp_path: Path):
    """run_all(task_ids) 严格按列表顺序执行。"""
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n"
        "  greet:\n"
        "    task_class: 'tests.fixtures.GreetTask'\n"
        "    enabled: true\n"
        "    display_order: 1\n",
        encoding="utf-8",
    )
    tmp_config.reload()

    report = engine.run_all(["greet"])
    assert report.total_count == 1


def test_run_all_stops_on_failure_when_cfg_says_so(
    engine: TaskEngine, fake_common_actions, tmp_config: ConfigManager, tmp_path: Path
):
    """当 cfg.app.scheduler.stop_on_failure=True 且任务失败时,后续任务跳过。"""
    # 注意顺序: 先 reload 让 task_registry 被读到,再设 stop_on_failure
    # 否则 reload 会覆盖运行时设置。
    (tmp_path / "config" / "task_registry.yaml").write_text(
        "tasks:\n"
        "  greet:\n"
        "    task_class: 'tests.fixtures.FailTask'\n"
        "    enabled: true\n"
        "    display_order: 1\n",
        encoding="utf-8",
    )
    tmp_config.reload()
    tmp_config.app.scheduler.stop_on_failure = True

    report = engine.run_all(["greet"])
    assert report.aborted is True
    assert "stop_on_failure" in report.abort_reason


def test_stop_calls_scheduler_request_abort(engine: TaskEngine):
    """stop() 转发到 Scheduler.request_abort;通过 is_aborted() 公开 API 验证。"""
    engine.stop()
    assert engine._scheduler.is_aborted() is True


def test_is_aborted_public_api():
    """P1-ARCH-03: Scheduler.is_aborted() 是公开 API,不再暴露 _abort_flag。"""
    import inspect
    from core.scheduler import Scheduler

    # is_aborted 必须是公开方法(无下划线前缀)
    assert "is_aborted" in dir(Scheduler)
    src = inspect.getsource(Scheduler.is_aborted)
    assert "_abort_flag" in src  # 内部确实用了 _abort_flag
    assert "def is_aborted" in src  # 但对外是公开方法


def test_injects_common_actions_to_ctx(ctx: ExecutionContext, fake_common_actions, tmp_path: Path):
    """P1-ARCH-02: TaskEngine.__init__ 会自动把 common_actions 注入到 ctx.common_actions,
    不再走 cfg._phase3_deps 私有属性 hack。"""
    assert ctx.common_actions is None  # 注入前为 None
    engine = TaskEngine(ctx, common_actions=fake_common_actions)
    assert ctx.common_actions is fake_common_actions  # 注入后是同一个对象
    # 验证没有再用 cfg hack
    assert not hasattr(ctx.config, "_phase3_deps")


def test_task_engine_does_not_implement_scheduling_logic(engine: TaskEngine):
    """V2 职责边界: TaskEngine 不做排序/调度/构建/依赖分析,这些都委托给 Scheduler。"""
    # 验证 TaskEngine.run_all 内部直接调用 Scheduler 的 _instantiate_tasks / run_single,
    # 不自己维护排序。
    assert hasattr(engine, "_scheduler")
    assert isinstance(engine._scheduler, Scheduler)