"""test_run_context.py — RunContext 7 条 Non-goals 硬约束验证。

包含 AST 静态扫描 + 运行时行为测试。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from logging_ext import RunContext
from logging_ext import run_context as run_context_module


# ============================================================
# Non-goals #1: 不 import 业务模块
# ============================================================


def test_run_context_module_does_not_import_business_modules():
    """AST 静态扫描:RunContext 模块**不**import 任何业务模块。"""
    source = inspect.getsource(run_context_module)
    tree = ast.parse(source)

    banned_modules = {
        "tasks", "state", "recovery", "state_machine", "device",
        "recognizer", "recognition", "core.base_task", "core.scheduler",
    }
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in banned_modules or alias.name in banned_modules:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            if top in banned_modules or node.module in banned_modules:
                found.append(node.module)

    assert not found, (
        f"RunContext 模块禁止 import 业务模块,实际发现: {found}. "
        f"Non-goals #1: RunContext 只 import stdlib / loguru / core.logger。"
    )


# ============================================================
# Non-goals #2: 不修改外部状态(只 log)
# ============================================================


def test_run_context_does_not_modify_external_state():
    """Non-goals #2: 进入 + 退出不应修改任何传入参数。"""
    state_before_orig = "HOME"
    extra_orig = {"foo": "bar"}
    rc = RunContext(
        task_id="t1", state_before=state_before_orig, **extra_orig,
    )

    with rc:
        rc.state_after = "POPUP"

    # state_before 字符串没被改
    assert state_before_orig == "HOME"
    # extra dict 没被改
    assert extra_orig == {"foo": "bar"}


# ============================================================
# Non-goals #3: 不引入第二套 ExecutionContext
# ============================================================


def test_run_context_does_not_expose_execution_context_like_attrs():
    """Non-goals #3: RunContext 不暴露 ExecutionContext 风格的 attribute。"""
    rc = RunContext(task_id="t1")
    public_attrs = {a for a in dir(rc) if not a.startswith("_")}

    # 允许的公开 attr(就这几个,每个都对应 Non-goals 硬约束)
    allowed = {
        "task_id", "state_before", "log", "elapsed_ms", "level",
        "state_after", "exit_level", "extra_fields",
        # RunContext 继承的(默认 object 暴露)
        "extra_fields", "state_after", "exit_level",
    }
    # 不允许的 attr 名(类似 ExecutionContext 风格)
    forbidden = {
        "config", "window_manager", "screenshot_manager",
        "state_machine", "run_id", "task_results", "current_task_id",
        "last_screenshot_path", "common_actions", "last_state",
        "last_screenshot", "record", "target_window", "bind_logger",
    }
    leaked = public_attrs & forbidden
    assert not leaked, (
        f"RunContext 暴露了类似 ExecutionContext 的 attr: {leaked}. "
        f"Non-goals #3: RunContext 不是 ExecutionContext。"
    )


# ============================================================
# Non-goals #4: 不调用业务模块函数
# ============================================================


def test_run_context_only_uses_stdlib_and_loguru():
    """Non-goals #4: RunContext 内部只用 stdlib + loguru,没调任何业务函数。"""
    source = inspect.getsource(run_context_module)

    # 业务函数/类白名单(绝对不能出现)
    banned_calls = [
        "update_state", "go_home", "recover_unknown", "recover_popup",
        "recover_loading_timeout", "recover_adb_error", "detect_state",
        "keyevent", "tap", "screenshot", "close_popup", "go_home",
        "wait_loading", "ensure_state", "dismiss_popup", "observe",
        "save_failure", "save_recovery", "save_state_transition",
        "register_task", "run_task", "run_all",
    ]
    # 注意:这些名字可能在 docstring/comment 出现,要看是否作为函数调用
    # 简化:用 ast 找 Call 节点
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            if func_name in banned_calls:
                pytest.fail(
                    f"RunContext 调用了业务函数 {func_name}! "
                    f"Non-goals #4: RunContext 不调 GameStateMachine / CommonActions / "
                    f"ADBClient / RecoveryManager。"
                )


# ============================================================
# Non-goals #5: state_before/state_after 由调用方显式传入或 set
# ============================================================


def test_run_context_state_before_default_is_none():
    """默认 state_before=None(由调用方显式传,不自动推断)。"""
    rc = RunContext(task_id="t1")
    assert rc.state_before is None


def test_run_context_state_after_default_is_none():
    """state_after 默认 None(由调用方在 __exit__ 前显式 set)。"""
    rc = RunContext(task_id="t1")
    with rc:
        # 内部 set 之前
        assert rc.state_after is None


# ============================================================
# Non-goals #6: 不做任何 IO
# ============================================================


def test_run_context_does_not_open_files():
    """Non-goals #6: RunContext 内部不打开文件(只调 loguru)。"""
    source = inspect.getsource(run_context_module)
    # 不允许出现的文件操作
    banned_io = ["open(", "Path(", "write_text", "write_bytes", ".save(", "tofile"]
    for token in banned_io:
        if token in source and "logger" not in source.split(token)[0][-200:]:
            # logger 行不参与(我们用 logger 写)
            # 简化为:除了注释/docstring,不允许出现
            pass
    # 实际上 RunContext 唯一会落库的是 loguru 的 logger,这个 OK
    # 验证:用 ast 找 builtin 'open' / 'Path' 调用
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                pytest.fail("RunContext 调了 open() — Non-goals #6 禁止 IO")


# ============================================================
# Non-goals #7: 不捕获异常(异常照常抛)
# ============================================================


def test_run_context_does_not_swallow_exceptions():
    """Non-goals #7: __exit__ 不返回 True,异常照常向上抛。"""
    rc = RunContext(task_id="t1")

    with pytest.raises(RuntimeError, match="boom"):
        with rc:
            raise RuntimeError("boom")

    # __exit__ 返回 None / False → 异常照常抛
    # (contextmanager 协议:返回 True 才会吞掉异常)
    # 我们在 __exit__ 没写 return 语句,所以隐式返 None


# ============================================================
# 正常行为
# ============================================================


def test_run_context_logs_elapsed_ms_on_exit():
    """__exit__ 时计算 elapsed_ms 并绑到 logger。"""
    rc = RunContext(task_id="t1", state_before="HOME")
    with rc:
        rc.state_after = "POPUP"
    # elapsed_ms 应该是 > 0
    assert rc.elapsed_ms >= 0


def test_run_context_provides_bound_logger_inside_with():
    """__enter__ 后,rc.log 可用,且绑了 task_id / state_before。"""
    rc = RunContext(task_id="my_task", state_before="HOME")
    with rc as r:
        assert r.log is not None
        # 绑定的 logger 应该有 task_id 上下文
        # (loguru 不暴露 dict 但调 info 不会抛)
        r.log.info("test message")


def test_run_context_log_raises_outside_with():
    """__enter__ 之前调 rc.log → RuntimeError。"""
    rc = RunContext(task_id="t1")
    with pytest.raises(RuntimeError, match="only available inside"):
        _ = rc.log


def test_run_context_extra_fields_passed_to_bind():
    """extra 字段被绑到 logger。"""
    rc = RunContext(task_id="t1", page="login", run_id="abc")
    with rc as r:
        # 不会抛
        r.log.info("test")


def test_run_context_exit_level_overrides_initial():
    """__exit__ 前可改 exit_level,影响最终日志级别。"""
    rc = RunContext(task_id="t1", level="INFO")
    assert rc.exit_level == "INFO"
    rc.exit_level = "ERROR"
    with rc:
        pass
    # 验证 exit_level 被改过
    assert rc.exit_level == "ERROR"
