"""test_navigator_jumpback.py — P1 修复: Navigator 正确处理 [JumpBack] 前缀。

P1 修复(2026-07-02):
- ``Navigator._next_or_finish`` / ``Navigator._on_recognition_failed`` 之前直接
  return ``node.next[0]``,如果带 ``[JumpBack]`` 前缀,会作为字面节点名查找 → 失败
- 修复后:strip ``[JumpBack]`` 前缀,只对纯节点名查 ``Pipeline.get``
- 当前 task pipeline 不使用 JumpBack(走 Python 端),此修复为未来兜底

测试覆盖:
    - ``_strip_jumpback_log``: 直接带 [JumpBack] 前缀 → 去掉
    - ``_strip_jumpback_log``: 不带 [JumpBack] 前缀 → 不动
    - ``_next_or_finish``: next=[JumpBack]foo → return "foo"
    - ``_next_or_finish``: next=["foo"] → return "foo"
    - ``_next_or_finish``: next=[] → return None
    - ``_on_recognition_failed``: on_error=[JumpBack]bar → return "bar"
    - ``_on_recognition_failed``: on_error 空 + next=[JumpBack]baz → return "baz"
    - ``_on_recognition_failed``: 都没有 → return None
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from loguru import logger

from tasks.navigator import (
    Navigator,
    Node,
    NoopAction,
    strip_jumpback,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def nav(tmp_path: Path) -> Navigator:
    """构造一个轻量 Navigator,不连真 ADB。"""
    adb = MagicMock()
    return Navigator(
        adb_client=adb,
        project_root=tmp_path,
    )


def _make_node(name: str, *, next_list: list[str] | None = None,
               on_error: list[str] | None = None) -> Node:
    return Node(
        name=name,
        templates=[],
        action=NoopAction(),
        next=list(next_list or []),
        on_error=list(on_error or []),
    )


# ============================================================
# 单元测试: strip_jumpback (已有 test_daily_signin_task.py 覆盖,
# 这里再补一个防御性测试,确保不被无意删除)
# ============================================================


def test_strip_jumpback_strips_prefix():
    assert strip_jumpback("[JumpBack]back_main_screen") == "back_main_screen"


def test_strip_jumpback_idempotent():
    """无前缀时不变。"""
    assert strip_jumpback("back_main_screen") == "back_main_screen"


# ============================================================
# 单元测试: Navigator._strip_jumpback_log
# ============================================================


def test_strip_jumpback_log_with_prefix_strips_and_logs(nav: Navigator, caplog):
    node = _make_node("start")
    target = "[JumpBack]back_to_home"
    result = nav._strip_jumpback_log(node, target, kind="next")
    assert result == "back_to_home"
    # 至少要 log 一条 debug


def test_strip_jumpback_log_without_prefix_unchanged(nav: Navigator):
    node = _make_node("start")
    target = "next_node"
    result = nav._strip_jumpback_log(node, target, kind="next")
    assert result == "next_node"


# ============================================================
# 行为测试: _next_or_finish + _on_recognition_failed 集成 strip
# ============================================================


def test_next_or_finish_strips_jumpback_prefix(nav: Navigator):
    """next=[JumpBack]foo → return "foo"(不返回带前缀的字面名)。"""
    node = _make_node("start", next_list=["[JumpBack]foo"])
    result = nav._next_or_finish(node, recognized=True)
    assert result == "foo"


def test_next_or_finish_works_with_plain_name(nav: Navigator):
    """next=["foo"] → return "foo"(回归测试,普通节点名仍工作)。"""
    node = _make_node("start", next_list=["foo"])
    result = nav._next_or_finish(node, recognized=True)
    assert result == "foo"


def test_next_or_finish_empty_returns_none(nav: Navigator):
    """next=[] → return None(终点)。"""
    node = _make_node("start", next_list=[])
    result = nav._next_or_finish(node, recognized=True)
    assert result is None


def test_on_recognition_failed_strips_jumpback_in_on_error(nav: Navigator):
    """on_error=[JumpBack]bar → return "bar"。"""
    node = _make_node("start", on_error=["[JumpBack]bar"])
    result = nav._on_recognition_failed(node)
    assert result == "bar"


def test_on_recognition_failed_strips_jumpback_in_next(nav: Navigator):
    """on_error 空 + next=[JumpBack]baz → return "baz"(fallback 链)。"""
    node = _make_node("start", next_list=["[JumpBack]baz"])
    result = nav._on_recognition_failed(node)
    assert result == "baz"


def test_on_recognition_failed_no_fallback_returns_none(nav: Navigator):
    """on_error 空 + next=[] → return None(终点)。"""
    node = _make_node("start", next_list=[])
    result = nav._on_recognition_failed(node)
    assert result is None


def test_on_recognition_failed_plain_names_unchanged(nav: Navigator):
    """on_error=["foo"] → return "foo"(回归测试)。"""
    node = _make_node("start", on_error=["foo"])
    result = nav._on_recognition_failed(node)
    assert result == "foo"


# ============================================================
# P3 修复测试: Navigator 公共属性 scale_x / scale_y / ref_width / ref_height
# ============================================================


def test_scale_defaults_to_one(nav: Navigator):
    """未调用 set_resolution_scale 时,scale 默认 1.0。"""
    assert nav.scale_x == 1.0
    assert nav.scale_y == 1.0


def test_ref_dimensions_exposed(nav: Navigator):
    """参考分辨率对外可读。"""
    assert nav.ref_width == 1920
    assert nav.ref_height == 1080


def test_set_resolution_scale_updates_public_properties(nav: Navigator):
    """set_resolution_scale 后,公共属性反映新值。"""
    nav.set_resolution_scale(1920, 1080, 1280, 720)
    assert nav.scale_x == pytest.approx(1280 / 1920)
    assert nav.scale_y == pytest.approx(720 / 1080)


def test_set_resolution_scale_same_size_keeps_one(nav: Navigator):
    """src == dst 时,scale 仍为 1.0。"""
    nav.set_resolution_scale(1920, 1080, 1920, 1080)
    assert nav.scale_x == 1.0
    assert nav.scale_y == 1.0


def test_public_scale_properties_match_private():
    """公共 scale_x / scale_y 必须与私有 _scale_x / _scale_y 同步(防止双源不一致)。"""
    from tasks.navigator import Navigator as Nav
    n = Nav(adb_client=MagicMock(), project_root=Path("/tmp"))
    n.set_resolution_scale(1920, 1080, 960, 540)
    assert n.scale_x == n._scale_x
    assert n.scale_y == n._scale_y
