"""test_scheme_manager.py — SchemeManager 单元测试。

覆盖:
- list_schemes
- load / save / delete
- 容错(坏 JSON / 缺字段 / IO 失败)
- 多实例读取一致性
- 非法 name 拒绝
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.scheme_manager import SchemeError, SchemeManager


@pytest.fixture
def schemes_dir(tmp_path: Path) -> Path:
    """空 schemes 目录(SchemeManager 会自动 seed 3 个默认)。"""
    d = tmp_path / "schemes"
    d.mkdir()
    return d


@pytest.fixture
def mgr(schemes_dir: Path) -> SchemeManager:
    return SchemeManager(schemes_dir)


# ============================================================
# 基础
# ============================================================


def test_scheme_manager_seeds_default_schemes(mgr, schemes_dir):
    """启动时 seed 3 个默认方案(daily / weekly / event)。"""
    names = mgr.list_schemes()
    assert "daily" in names
    assert "weekly" in names
    assert "event" in names
    # 3 个文件实际存在
    for n in names:
        assert (schemes_dir / f"{n}.json").is_file()


def test_scheme_manager_default_daily_has_daily_signin(mgr):
    """默认 daily.json 包含 daily_signin。"""
    assert mgr.load("daily") == ["daily_signin"]


def test_scheme_manager_list_returns_sorted(mgr):
    """list_schemes 按字母序。"""
    names = mgr.list_schemes()
    assert names == sorted(names)


# ============================================================
# save / load
# ============================================================


def test_scheme_manager_save_and_load_roundtrip(mgr, schemes_dir):
    """保存 → 加载 往返一致。"""
    mgr.save("custom", ["task_a", "task_b"])
    assert mgr.load("custom") == ["task_a", "task_b"]
    # 文件内容
    raw = (schemes_dir / "custom.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data == {"task_ids": ["task_a", "task_b"]}


def test_scheme_manager_save_empty_list_is_legal(mgr):
    """空 task_ids 列表合法(允许空方案)。"""
    mgr.save("empty", [])
    assert mgr.load("empty") == []


def test_scheme_manager_save_overwrites_existing(mgr):
    """save 覆盖现有方案。"""
    mgr.save("daily", ["old_task"])
    assert mgr.load("daily") == ["old_task"]
    mgr.save("daily", ["new_task"])
    assert mgr.load("daily") == ["new_task"]


def test_scheme_manager_load_missing_returns_none(mgr):
    """加载不存在的方案 → None(不抛)。"""
    assert mgr.load("never_existed") is None


def test_scheme_manager_exists(mgr):
    """exists 正确反映文件是否存在。"""
    assert mgr.exists("daily") is True
    assert mgr.exists("nonexistent") is False


# ============================================================
# delete
# ============================================================


def test_scheme_manager_delete_removes_file(mgr, schemes_dir):
    """delete 删文件 + list 看不见。"""
    assert mgr.delete("weekly") is True
    assert not (schemes_dir / "weekly.json").exists()
    assert "weekly" not in mgr.list_schemes()


def test_scheme_manager_delete_missing_returns_false(mgr):
    """delete 不存在的方案 → False。"""
    assert mgr.delete("ghost") is False


# ============================================================
# 容错
# ============================================================


def test_scheme_manager_rejects_invalid_json(mgr, schemes_dir):
    """坏 JSON 加载 → SchemeError。"""
    (schemes_dir / "broken.json").write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(SchemeError, match="invalid JSON"):
        mgr.load("broken")


def test_scheme_manager_rejects_missing_field(mgr, schemes_dir):
    """缺 task_ids 字段 → SchemeError。"""
    (schemes_dir / "no_field.json").write_text(
        json.dumps({"name": "no_field"}), encoding="utf-8",
    )
    with pytest.raises(SchemeError, match="missing required 'task_ids'"):
        mgr.load("no_field")


def test_scheme_manager_rejects_wrong_field_type(mgr, schemes_dir):
    """task_ids 不是 list[str] → SchemeError。"""
    (schemes_dir / "wrong_type.json").write_text(
        json.dumps({"task_ids": "not_a_list"}), encoding="utf-8",
    )
    with pytest.raises(SchemeError, match="must be list"):
        mgr.load("wrong_type")


def test_scheme_manager_rejects_top_level_not_dict(mgr, schemes_dir):
    """top-level 不是 dict → SchemeError。"""
    (schemes_dir / "list_root.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )
    with pytest.raises(SchemeError, match="top-level must be dict"):
        mgr.load("list_root")


# ============================================================
# 非法 name
# ============================================================


def test_scheme_manager_save_rejects_empty_name(mgr):
    """空名 → ValueError。"""
    with pytest.raises(ValueError, match="non-empty"):
        mgr.save("", ["x"])


def test_scheme_manager_save_rejects_path_traversal(mgr):
    """含路径分隔符的名字 → ValueError。"""
    with pytest.raises(ValueError, match="illegal characters"):
        mgr.save("../escape", ["x"])


def test_scheme_manager_save_rejects_non_alnum(mgr):
    """非字母数字字符 → ValueError。"""
    with pytest.raises(ValueError, match="alphanumeric"):
        mgr.save("bad name!", ["x"])


def test_scheme_manager_save_rejects_non_string_task_ids(mgr):
    """task_ids 含非 str → SchemeError。"""
    with pytest.raises(SchemeError, match="list"):
        mgr.save("bad", ["a", 2, "c"])


# ============================================================
# 多实例
# ============================================================


def test_scheme_manager_persists_across_instances(schemes_dir):
    """实例 A 存,实例 B 读 → 一致。"""
    a = SchemeManager(schemes_dir)
    a.save("persistent", ["x", "y"])
    # 销毁 a,新建 b
    b = SchemeManager(schemes_dir)
    assert b.load("persistent") == ["x", "y"]
    assert "persistent" in b.list_schemes()


def test_scheme_manager_works_with_empty_dir(tmp_path):
    """空目录(seed 之前)也能正常工作。"""
    d = tmp_path / "empty_schemes"
    d.mkdir()
    mgr = SchemeManager(d)
    assert "daily" in mgr.list_schemes()
