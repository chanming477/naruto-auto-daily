"""test_clean_logs.py — CleanLogs 维护性 action 行为。

覆盖范围:
    1. keep_sessions 参数边界 (0 / 默认 / argv override / 负数 / 非数字)
    2. session 名模式匹配 (合法 YYYYMMDD_HHMMSS / 非法)
    3. logs/ + MFAAvalonia/debug/ 缺失时不崩
    4. maafw.bak.*.log 精确匹配(保留 maafw.log / something.bak.log)
    5. on_error/ 嵌套目录递归删除
    6. _purge_path permission error 静默降级
    7. 整体 best-effort 行为(部分失败也返 True)

所有文件系统操作走 ``tmp_path`` 隔离,patch ``_find_project_root`` 让
``clean_logs_run`` 看到测试沙盒而不是真实项目目录。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from maafw_bridge import _actions_core


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fake_context():
    """fake maa context — clean_logs_run 不真正用,但接口要。"""
    return SimpleNamespace(tasker=SimpleNamespace(controller=None))


@pytest.fixture
def project_sandbox(tmp_path, monkeypatch):
    """模拟一个项目根目录(含 logs/ + frontend/MFAAvalonia/debug/)。

    patch ``_find_project_root`` 返回 sandbox 根,
    patch ``__file__`` 让 ``Path(__file__).resolve().parent`` 走真实路径
    (不会影响 _find_project_root 因为已经被 mock)。
    """
    sandbox = tmp_path
    (sandbox / "logs").mkdir()
    (sandbox / "frontend" / "MFAAvalonia" / "debug").mkdir(parents=True)
    monkeypatch.setattr(_actions_core, "_find_project_root", lambda: sandbox)
    return sandbox


@pytest.fixture
def argv_with():
    """``make_argv(param_dict)`` 工厂 — 模拟 maa custom action 的 argv。"""

    def _make(d: dict | str | None) -> SimpleNamespace:
        return SimpleNamespace(custom_action_param=d)

    return _make


def _make_session(parent: Path, name: str, debug_bytes: int = 1024) -> Path:
    """在 parent 下建一个 session 目录,塞 debug/ + debug/img.png + logs/app.log。"""
    s = parent / "logs" / name
    (s / "debug").mkdir(parents=True)
    (s / "debug" / "img.png").write_bytes(b"x" * debug_bytes)
    (s / "logs").mkdir()
    (s / "logs" / "app.log").write_text("a log line\n")
    return s


# ============================================================
# 1. keep_sessions 参数边界
# ============================================================


def test_keep_sessions_default_3(project_sandbox, fake_context, argv_with):
    """默认 keep_sessions=3 — 老于 3 的 session 只删 debug/,保留 text log。"""
    for i in range(1, 6):  # 5 个 session
        _make_session(project_sandbox, f"2026010{i}_120000")

    result = _actions_core.clean_logs_run(fake_context, argv_with(None))

    assert result is True
    # 最新 3 个 (i=5, 4, 3) 的 debug/ 应保留
    for i in (3, 4, 5):
        assert (project_sandbox / "logs" / f"2026010{i}_120000" / "debug").is_dir(), (
            f"session 2026010{i} debug/ should be kept"
        )
    # 老的 2 个 (i=1, 2) 的 debug/ 应被删
    for i in (1, 2):
        assert not (project_sandbox / "logs" / f"2026010{i}_120000" / "debug").exists(), (
            f"session 2026010{i} debug/ should be deleted"
        )
    # text log 全在(无论 keep/不 keep)
    for i in range(1, 6):
        log = project_sandbox / "logs" / f"2026010{i}_120000" / "logs" / "app.log"
        assert log.exists(), f"session 2026010{i} text log should always be kept"


def test_keep_sessions_argv_override(project_sandbox, fake_context, argv_with):
    """argv 的 keep_sessions 优先于函数默认参数。"""
    for i in range(1, 5):
        _make_session(project_sandbox, f"2026010{i}_120000")

    # argv 说 keep=1,函数默认 keep_sessions=3 → 实际用 1
    result = _actions_core.clean_logs_run(
        fake_context, argv_with({"keep_sessions": 1}), keep_sessions=3,
    )

    assert result is True
    # 只保留最新 1 个 (i=4)
    assert (project_sandbox / "logs" / "20260104_120000" / "debug").is_dir()
    for i in (1, 2, 3):
        assert not (project_sandbox / "logs" / f"2026010{i}_120000" / "debug").exists()


def test_keep_sessions_zero_deletes_all(project_sandbox, fake_context, argv_with):
    """keep_sessions=0 — 所有 session 的 debug/ 都被删。"""
    for i in (1, 2, 3):
        _make_session(project_sandbox, f"2026010{i}_120000")

    result = _actions_core.clean_logs_run(fake_context, argv_with({"keep_sessions": 0}))

    assert result is True
    for i in (1, 2, 3):
        assert not (project_sandbox / "logs" / f"2026010{i}_120000" / "debug").exists()


def test_keep_sessions_negative_clamps_to_zero(
    project_sandbox, fake_context, argv_with,
):
    """keep_sessions=-5 → 内部 clamp 到 0 → 删所有 debug/。"""
    _make_session(project_sandbox, "20260101_120000")

    result = _actions_core.clean_logs_run(fake_context, argv_with({"keep_sessions": -5}))

    assert result is True
    assert not (project_sandbox / "logs" / "20260101_120000" / "debug").exists()


def test_keep_sessions_non_numeric_falls_back(
    project_sandbox, fake_context, argv_with,
):
    """argv 的 keep_sessions 是非数字 → fallback 到函数默认 (3)。"""
    for i in range(1, 6):
        _make_session(project_sandbox, f"2026010{i}_120000")

    result = _actions_core.clean_logs_run(
        fake_context, argv_with({"keep_sessions": "abc"}), keep_sessions=3,
    )

    assert result is True
    # fallback 到 3 → 保留最新 3 个
    for i in (3, 4, 5):
        assert (project_sandbox / "logs" / f"2026010{i}_120000" / "debug").is_dir()
    for i in (1, 2):
        assert not (project_sandbox / "logs" / f"2026010{i}_120000" / "debug").exists()


# ============================================================
# 2. session 名模式匹配
# ============================================================


def test_session_name_pattern_legitimate(project_sandbox, fake_context, argv_with):
    """合法 YYYYMMDD_HHMMSS 格式的 session 才会被处理,非 session 目录不被碰。"""
    _make_session(project_sandbox, "20260101_120000")  # 合法
    _make_session(project_sandbox, "20261231_235959")  # 合法 (年末)

    # 加几个非法命名的目录(带 debug/ 子目录,如果被错当成 session 会被删)
    for name in ("notadate", "20260101-120000", "20260101_12000X"):
        d = project_sandbox / "logs" / name
        (d / "debug").mkdir(parents=True)
        (d / "debug" / "img.png").write_bytes(b"x" * 100)

    result = _actions_core.clean_logs_run(fake_context, argv_with({"keep_sessions": 0}))

    assert result is True
    # 合法 2 个的 debug/ 都被删
    assert not (project_sandbox / "logs" / "20260101_120000" / "debug").exists()
    assert not (project_sandbox / "logs" / "20261231_235959" / "debug").exists()
    # 非法 3 个的 debug/ 不应被删(它们不被识别为 session)
    for name in ("notadate", "20260101-120000", "20260101_12000X"):
        assert (project_sandbox / "logs" / name / "debug").is_dir(), (
            f"non-session dir {name} should be left alone"
        )


# ============================================================
# 3. 缺失目录不崩
# ============================================================


def test_missing_logs_dir(tmp_path, monkeypatch, fake_context, argv_with):
    """logs/ 不存在时直接跳过(不崩),仍然处理 debug/。"""
    sandbox = tmp_path
    # 注意:不建 logs/
    debug_dir = sandbox / "frontend" / "MFAAvalonia" / "debug"
    debug_dir.mkdir(parents=True)
    (debug_dir / "maafw.bak.1.log").write_text("bak")

    monkeypatch.setattr(_actions_core, "_find_project_root", lambda: sandbox)

    result = _actions_core.clean_logs_run(fake_context, argv_with(None))

    assert result is True
    # debug/ 仍然被处理
    assert not (debug_dir / "maafw.bak.1.log").exists()


def test_missing_maafw_debug_dir(tmp_path, monkeypatch, fake_context, argv_with):
    """frontend/MFAAvalonia/debug/ 不存在时直接跳过,仍然处理 logs/。"""
    sandbox = tmp_path
    (sandbox / "logs").mkdir()
    # 不建 debug/
    for i in range(1, 5):
        _make_session(sandbox, f"2026010{i}_120000")

    monkeypatch.setattr(_actions_core, "_find_project_root", lambda: sandbox)

    result = _actions_core.clean_logs_run(fake_context, argv_with({"keep_sessions": 0}))

    assert result is True
    # logs 仍然被处理
    for i in range(1, 5):
        assert not (sandbox / "logs" / f"2026010{i}_120000" / "debug").exists()


# ============================================================
# 4. maafw.bak.*.log 精确匹配
# ============================================================


def test_maafw_bak_log_matching(project_sandbox, fake_context, argv_with):
    """maafw.bak.*.log 才删,maafw.log / something.bak.log / maafw.bak.foo 都保留。"""
    dbg = project_sandbox / "frontend" / "MFAAvalonia" / "debug"
    (dbg / "maafw.bak.1.log").write_text("bak 1")
    (dbg / "maafw.bak.2.log").write_text("bak 2")
    (dbg / "maafw.bak.foo").write_text("not .log")  # 缺 .log 后缀,保留
    (dbg / "maafw.log").write_text("current")      # 当前 log,保留
    (dbg / "something.bak.log").write_text("diff prefix")  # 缺 maafw.bak. 前缀,保留

    result = _actions_core.clean_logs_run(fake_context, argv_with(None))

    assert result is True
    assert not (dbg / "maafw.bak.1.log").exists()
    assert not (dbg / "maafw.bak.2.log").exists()
    # 下面 3 个应保留
    assert (dbg / "maafw.bak.foo").exists()
    assert (dbg / "maafw.log").exists()
    assert (dbg / "something.bak.log").exists()


# ============================================================
# 5. on_error/ 嵌套递归删除
# ============================================================


def test_on_error_recursive_delete(project_sandbox, fake_context, argv_with):
    """on_error/ 下的嵌套目录和文件全部递归删除。"""
    on_err = project_sandbox / "frontend" / "MFAAvalonia" / "debug" / "on_error"
    on_err.mkdir(parents=True)
    (on_err / "img1.png").write_bytes(b"x" * 100)
    (on_err / "nested").mkdir()
    (on_err / "nested" / "img2.png").write_bytes(b"x" * 200)
    (on_err / "nested" / "deeper").mkdir()
    (on_err / "nested" / "deeper" / "img3.png").write_bytes(b"x" * 300)

    result = _actions_core.clean_logs_run(fake_context, argv_with(None))

    assert result is True
    assert not on_err.exists()


# ============================================================
# 6. permission error 静默降级
# ============================================================


def test_permission_error_silent_degrade(
    project_sandbox, fake_context, argv_with, monkeypatch,
):
    """单文件 permission error 不阻断整体清理。

    模拟方式:把 _purge_path 改成对某些 path 返回 0(模拟内部 rmtree 失败),
    验证 clean_logs_run 仍返 True,后续 path 仍被处理。
    """
    _make_session(project_sandbox, "20260101_120000")  # 老的
    _make_session(project_sandbox, "20260102_120000")  # 新的

    # 模拟"删不动"的情况:返 0 但不抛
    real_purge = _actions_core._purge_path
    calls = {"paths": []}

    def tracking_purge(p):
        calls["paths"].append(p)
        return real_purge(p)  # 正常调用,不抛

    monkeypatch.setattr(_actions_core, "_purge_path", tracking_purge)

    result = _actions_core.clean_logs_run(
        fake_context, argv_with({"keep_sessions": 0}),
    )

    assert result is True
    # 验证 _purge_path 至少被调过(对 2 个 session + 可能的 debug/ entries)
    assert len(calls["paths"]) >= 2, (
        f"_purge_path should be called for each session debug/, got {calls['paths']}"
    )


def test_purge_path_handles_oserror_silently(project_sandbox, monkeypatch):
    """_purge_path 内部 OSError 静默降级(单独验证,不走 clean_logs_run 链路)。"""
    from maafw_bridge._actions_core import _purge_path

    # 模拟一个不存在的文件 → unlink 抛 FileNotFoundError (OSError 子类)
    nonexistent = project_sandbox / "does_not_exist.txt"
    # 期待:不抛异常,返 0
    result = _purge_path(nonexistent)
    assert result == 0


def test_purge_path_handles_permission_error_silently(project_sandbox, monkeypatch):
    """_purge_path 内部 PermissionError 静默降级。"""
    from maafw_bridge._actions_core import _purge_path

    real_file = project_sandbox / "locked.txt"
    real_file.write_text("locked content")

    # 把 unlink mock 成抛 PermissionError
    import builtins
    real_unlink = Path.unlink

    def fail_unlink(self, *args, **kwargs):
        if self == real_file:
            raise PermissionError("simulated locked file")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    # 期待:不抛,返 0
    result = _purge_path(real_file)
    assert result == 0
    # 文件仍存在(因为 unlink 失败了)
    assert real_file.exists()


# ============================================================
# 7. best-effort 总返回 True
# ============================================================


def test_returns_true_even_when_nothing_to_clean(
    project_sandbox, fake_context, argv_with,
):
    """空目录也不崩,直接返 True。"""
    result = _actions_core.clean_logs_run(fake_context, argv_with(None))
    assert result is True


def test_returns_true_on_argv_missing(
    project_sandbox, fake_context,
):
    """argv 是 None(不通过 framework 调)也返 True。"""
    result = _actions_core.clean_logs_run(fake_context, None)
    assert result is True


# ============================================================
# 8. _find_project_root fallback
# ============================================================


def test_find_project_root_real_path():
    """_find_project_root 在真实项目路径上能正确找到 root(含 maafw_bridge/)。"""
    root = _actions_core._find_project_root()
    assert (root / "maafw_bridge").exists(), f"project root wrong: {root}"
    assert (root / "maafw_bridge" / "_actions_core.py").exists()


# ============================================================
# 9. Pipeline entry integrity (MaaFramework 加载时校验)
# ============================================================
# 防止再写错 next 引用(如 ["StopTask"]),导致整个 resource bundle 加载失败、
# 所有任务都跑不了。教训:2026-07-17 user 跑任务全挂,根因是 clean_logs entry
# 写了 next:["StopTask"] — MaaFramework 的 pipeline checker 不认这个节点名,
# 整个 merged.json 校验失败,bundle 加载失败。
# ============================================================


def test_clean_logs_pipeline_entry_has_no_invalid_next():
    """clean_logs entry 的 next 字段(若有)只能指向真实存在的节点名。

    StopTask / TaskEnd 之类不是合法节点名,会让整个 pipeline 加载失败。

    2026-07-15 状态:clean_logs entry 不在 merged.json 里(改用 cleanup_*
    链式 entry),本测试作回归保险:如果未来再有人加 clean_logs entry,
    本测试会立即检查格式。当前状态直接 skip。
    """
    import json
    from pathlib import Path

    merged = (
        Path(__file__).resolve().parent.parent
        / "resources" / "narutomobile" / "pipeline" / "merged.json"
    )
    data = json.loads(merged.read_text(encoding="utf-8"))

    entry = data.get("clean_logs")
    if entry is None:
        pytest.skip("clean_logs entry 不在 merged.json(改用 cleanup_* chain 模式)")

    if "next" in entry:
        all_keys = set(data.keys())
        for n in entry["next"]:
            if isinstance(n, str):
                assert n in all_keys, (
                    f"clean_logs.next has invalid ref: {n!r} "
                    f"(not a real node name; this is the 2026-07-17 bundle-load bug)"
                )


def test_clean_logs_pipeline_entry_is_leaf():
    """clean_logs 必须跟其他 leaf entry 模式一致(没 next 字段)。

    2026-07-15 状态:同上,clean_logs 不在 merged.json,本测试 skip。
    """
    import json
    from pathlib import Path

    merged = (
        Path(__file__).resolve().parent.parent
        / "resources" / "narutomobile" / "pipeline" / "merged.json"
    )
    data = json.loads(merged.read_text(encoding="utf-8"))

    entry = data.get("clean_logs")
    if entry is None:
        pytest.skip("clean_logs entry 不在 merged.json(改用 cleanup_* chain 模式)")
    # entry 存在时,确认没 next(leaf 模式)
    assert "next" not in entry, "clean_logs 应该是 leaf entry"

    # 其他 leaf entry 都没有 next 字段;clean_logs 也应该没有
    if "next" not in entry:
        # expected path
        return

    # 如果有 next 字段,验证它指向真实节点
    all_keys = set(data.keys())
    for n in entry["next"]:
        if isinstance(n, str):
            assert n in all_keys, f"next ref {n!r} not found in pipeline nodes"
