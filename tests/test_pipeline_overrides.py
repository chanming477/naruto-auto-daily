"""test_pipeline_overrides.py — 锁定 pipeline_overrides.py 的关键 invariant (v3 auto-sync)。

回归保护:
    1. 每个 entry 的 override 必须含正确的关键节点(expected/roi/next)
    2. give_energy override 的 ROI 必须覆盖 "一键赠送" / "一键领取" 按钮的真实位置
       (1280x720 模拟器下 y ≈ 630-690,2026-07-15 修复的根因)
    3. 任何 entry 的 "expected" 不能留空(否则 OCR 不工作)
    4. **v3 (2026-07-15)** frontend ``default.json`` 选中 "从奖励中心进入=Yes" 时,
       ``interface.json`` 的 Yes case 8 个 entry override 自动加载,不需要 Python 端 hardcoded

真理源 (2 个文件):
    - ``frontend/MFAAvalonia/interface.json`` option 块 — 所有可选 option 的 cases
    - ``frontend/MFAAvalonia/config/instances/default.json`` ResourceOptionItems — user 选中的值

新增 v3 测试:
    - test_interface_json_options_applied (从 default.json 选中的 option 自动应用)
    - test_frontend_overrides_loaded (8 个 entry 从 frontend 加载)
    - test_hardcoded_overrides_preserved (stronghold + give_energy 保留 hardcoded)
"""

from __future__ import annotations

import json
from pathlib import Path

from maafw_bridge.pipeline_overrides import (
    LEFT_MENU_FIND_ROI_REGULAR,
    LEFT_MENU_FIND_ROI_RETURNING,
    PIPELINE_OVERRIDES_BY_ENTRY,
    get_overrides_for_entry,
)


# ============================================================
# 注册完整性
# ============================================================


def test_all_required_entries_have_override():
    """每个走 忍者指南 的 entry 都必须有 override,否则 OCR 找默认的"装备"。

    v3 后:
        - frontend loaded: group / mission_office / point_race / weekly_win /
          secret_realm / shugyou_no_michi / black_market_merchant / more_gameplay
          (从 default.json "从奖励中心进入=Yes" 触发)
        - hardcoded: stronghold (要塞 = 找组织 tab) / give_energy (ROI 修复)
    """
    expected_entries = {
        # frontend auto-loaded (8 个)
        "group", "mission_office", "point_race", "weekly_win", "secret_realm",
        "shugyou_no_michi", "black_market_merchant", "more_gameplay",
        # hardcoded 保留 (2 个)
        "stronghold", "give_energy",
    }
    for entry in expected_entries:
        ov = get_overrides_for_entry(entry)
        assert ov is not None, f"entry {entry!r} 缺 override"
        assert ov, f"entry {entry!r} 的 override 不能为空 dict"


def test_give_energy_override_has_both_roi_fixes():
    """give_energy 必须同时修 sent_energy 和 get_energy 的 ROI。"""
    ov = get_overrides_for_entry("give_energy")
    assert ov is not None
    assert "sent_energy" in ov, "give_energy 缺 sent_energy ROI 修复"
    assert "get_energy" in ov, "give_energy 缺 get_energy ROI 修复"


# ============================================================
# give_energy ROI 精度 (2026-07-15 bug fix)
# ============================================================


def test_give_energy_sent_energy_roi_covers_button():
    """sent_energy ROI 必须覆盖 "一键赠送" 按钮 (1280x720, y ≈ 635-685)。

    回归保护:之前 ROI=[346,571,131,48] y=571-619,按钮在 ROI 下方 16-66 像素,
    OCR 永远找不到 → 22s 超时。
    """
    ov = get_overrides_for_entry("give_energy")
    assert ov is not None
    roi = ov["sent_energy"]["roi"]
    x, y, w, h = roi
    # 按钮中心 ≈ (390, 660),安全 margin
    assert x <= 340, f"sent_energy ROI 起点 x={x} 太右,应在 340 附近"
    assert y <= 635, f"sent_energy ROI 起点 y={y} 太高,应在 635 附近 (按钮 y=635-685)"
    assert x + w >= 440, f"sent_energy ROI 终点 x={x + w} 应 ≥ 440 覆盖按钮"
    assert y + h >= 685, f"sent_energy ROI 终点 y={y + h} 应 ≥ 685 覆盖按钮"


def test_give_energy_get_energy_roi_covers_button():
    """get_energy ROI 必须覆盖 "一键领取" 按钮 (x ≈ 519-629, y ≈ 630-690)。"""
    ov = get_overrides_for_entry("give_energy")
    assert ov is not None
    roi = ov["get_energy"]["roi"]
    x, y, w, h = roi
    assert x <= 519, f"get_energy ROI 起点 x={x} 应 ≤ 519"
    assert y <= 635, f"get_energy ROI 起点 y={y} 应 ≤ 635"
    assert x + w >= 629, f"get_energy ROI 终点 x={x + w} 应 ≥ 629"
    assert y + h >= 685, f"get_energy ROI 终点 y={y + h} 应 ≥ 685"


def test_give_energy_two_buttons_roi_not_overlap_misclick():
    """sent_energy 和 get_energy 的 ROI 不能重叠,否则 OCR "一键" 命中错按钮。"""
    ov = get_overrides_for_entry("give_energy")
    assert ov is not None
    sx, sy, sw, sh = ov["sent_energy"]["roi"]
    gx, gy, gw, gh = ov["get_energy"]["roi"]
    sent_x_end = sx + sw
    get_x_start = gx
    # 至少留 10 像素间距
    assert get_x_start >= sent_x_end + 10, (
        f"sent_energy (x_end={sent_x_end}) 和 get_energy (x_start={get_x_start})"
        f" 重叠或太近,OCR 命中「一键」会点错按钮"
    )


# ============================================================
# 忍者指南 entry 一致性
# ============================================================


def test_忍者指南_entry_expected_never_empty():
    """所有 entry 的 ninja_guide_find_funtion_entry.expected 都不能是空 list。

    v3 后只剩 stronghold 还走忍者指南 path (frontend 走奖励中心 path 的 entry
    没有 ninja_guide_find_funtion_entry 节点,这个断言依然通过)。
    """
    for entry_name, ov in PIPELINE_OVERRIDES_BY_ENTRY.items():
        if "ninja_guide_find_funtion_entry" in ov:
            cfg = ov["ninja_guide_find_funtion_entry"]
            assert "expected" in cfg, f"{entry_name} 缺 expected"
            assert cfg["expected"], f"{entry_name} expected 不能是空 list"
            assert isinstance(cfg["expected"], list), f"{entry_name} expected 必须是 list"


def test_组织_tab_used_by_stronghold_only():
    """"组织" tab 只应该被 stronghold 用 (都是 忍者指南 找组织)。

    v3 修复后: ``group`` 改走奖励中心 path(用户期望焚香祈福),
    唯一还在用忍者指南 "组织" tab 的是 ``stronghold``。
    """
    users = [
        e for e, ov in PIPELINE_OVERRIDES_BY_ENTRY.items()
        if "ninja_guide_find_funtion_entry" in ov
        and ov["ninja_guide_find_funtion_entry"].get("expected") == ["组织"]
    ]
    assert set(users) == {"stronghold"}, (
        f"v3 修复后只剩 stronghold 应该走忍者指南「组织」tab,实际: {users}"
    )


def test_group_override_走奖励中心_path_v3():
    """v3 修复: group entry 走奖励中心 → 焚香祈福(不是忍者指南 PvP)。

    验证来源: 从 frontend ``interface.json`` 的 "从奖励中心进入" Yes case 自动加载。
    """
    ov = get_overrides_for_entry("group")
    assert ov is not None
    assert "next" in ov, "group override 必须 override entry 的 next"
    nxt = ov["next"]
    # 必须有 group_in_center_enter(奖励中心 → 组织祈福)
    assert "group_in_center_enter" in nxt, (
        f"group v3 修复必须含 group_in_center_enter,实际: {nxt}"
    )
    # 必须有 award_center_enter fallback(不在奖励中心时)
    assert "[JumpBack]award_center_enter" in nxt, (
        f"group v3 修复必须含 [JumpBack]award_center_enter fallback,实际: {nxt}"
    )
    # 不应再走忍者指南 path(group_gameplay_undone 是忍者指南节点)
    assert "group_gameplay_undone" not in nxt, (
        f"group v3 不应再走忍者指南 path,实际: {nxt}"
    )


def test_left_menu_roi_constants_match_narutomobile():
    """LEFT_MENU_FIND_ROI 常量来自 narutomobile 真机验证,不应随便改。"""
    # narutomobile 默认是 [0, 66, 219, 627] (全左侧菜单)
    # 我们对 group/stronghold 缩窄到 [120, 68, 98, 585]
    assert LEFT_MENU_FIND_ROI_REGULAR == [120, 68, 98, 585]
    assert LEFT_MENU_FIND_ROI_RETURNING == [306, 100, 83, 558]


# ============================================================
# get_overrides_for_entry 行为
# ============================================================


def test_get_overrides_for_unknown_entry_returns_none():
    """未注册的 entry 返 None(走默认 merged.json),不应抛异常。"""
    assert get_overrides_for_entry("mail") is None
    assert get_overrides_for_entry("recruit") is None
    assert get_overrides_for_entry("nonexistent_entry") is None


def test_get_overrides_for_entry_returns_dict():
    """注册的 entry 返 dict,不能是 None 也不能是空 dict。"""
    for entry in [
        "group", "mission_office", "point_race", "weekly_win", "stronghold",
        "give_energy", "secret_realm", "shugyou_no_michi",
    ]:
        ov = get_overrides_for_entry(entry)
        assert isinstance(ov, dict), f"{entry} override 必须是 dict,实际 {type(ov)}"
        assert ov, f"{entry} override 不能是空 dict"


# ============================================================
# v3 新增: frontend auto-sync 验证
# ============================================================


def test_frontend_overrides_loaded():
    """``interface.json`` 的 option case 的 pipeline_override 自动加载到 PIPELINE_OVERRIDES_BY_ENTRY。

    当 ``default.json`` 的 ``ResourceOptionItems`` 选了 "从奖励中心进入"=Yes 时,
    8 个 entry 的 next override (group / shugyou_no_michi / mission_office / weekly_win /
    point_race / secret_realm / black_market_merchant / more_gameplay) 自动应用。
    """
    # 这 8 个 entry 必须存在
    expected_from_frontend = {
        "group", "shugyou_no_michi", "mission_office", "weekly_win",
        "point_race", "secret_realm", "black_market_merchant", "more_gameplay",
    }
    for entry in expected_from_frontend:
        ov = get_overrides_for_entry(entry)
        assert ov is not None, f"frontend 应该加载 {entry} 的 override"
        assert "next" in ov, f"{entry} 从 frontend 加载的 override 必须有 next 字段"
        # 走奖励中心 path 必须有 in_center_enter 节点
        nxt = ov["next"]
        assert any("_in_center_enter" in n for n in nxt), (
            f"{entry} 应该走奖励中心 path (含 _in_center_enter 节点),实际: {nxt}"
        )


def test_hardcoded_overrides_preserved():
    """frontend 没覆盖的 entry 仍保留 hardcoded 兜底(stronghold + give_energy)。

    stronghold: frontend "从奖励中心进入" 不覆盖(要塞=组织玩法,走忍者指南找组织 tab)
    give_energy: 1280x720 模拟器 ROI 修复,frontend interface.json 无此 option
    """
    # stronghold 仍走忍者指南
    stronghold_ov = get_overrides_for_entry("stronghold")
    assert stronghold_ov is not None
    assert "ninja_guide_find_funtion_entry" in stronghold_ov, (
        "stronghold 必须保留忍者指南 hardcoded override"
    )

    # give_energy ROI 修复保留
    energy_ov = get_overrides_for_entry("give_energy")
    assert energy_ov is not None
    assert "sent_energy" in energy_ov
    assert "get_energy" in energy_ov
    assert energy_ov["sent_energy"]["roi"] == [340, 630, 110, 60]
    assert energy_ov["get_energy"]["roi"] == [519, 630, 110, 60]


def test_interface_json_options_applied(tmp_path, monkeypatch):
    """验证 MFAAvalonia 清空 ``ResourceOptionItems`` 后,_FALLBACK_YES_OPTIONS 仍生效。

    2026-07-18 改: 原测试假设 ``default.json`` 有 "从奖励中心进入"=Yes,
    但 MFAAvalonia 启动会清空 ``ResourceOptionItems`` (用户没动过 GUI 时)。
    代码用 ``_FALLBACK_YES_OPTIONS`` 自动 fallback 3 个核心 option 为 Yes,
    本测试验证这个 fallback 行为正确 (用 tmp_path + monkeypatch 模拟清空的 default.json)。

    关键 invariant:
        - 即使用户 ResourceOptionItems={} (空),3 个 _FALLBACK_YES_OPTIONS
          仍按 Yes 处理,8 个 entry 的 override 仍被加载
    """
    from maafw_bridge import pipeline_overrides as po

    # 读真实 interface.json
    project_root = Path(__file__).resolve().parent.parent
    interface_json = project_root / "frontend" / "MFAAvalonia" / "interface.json"
    assert interface_json.exists(), f"interface.json 不存在: {interface_json}"
    interface_data = json.loads(interface_json.read_text(encoding="utf-8"))

    # 写空 ResourceOptionItems 的 default.json 到 tmp_path
    test_default = tmp_path / "default.json"
    test_default.write_text(
        json.dumps({"ResourceOptionItems": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    test_interface = tmp_path / "interface.json"
    test_interface.write_text(
        json.dumps(interface_data, ensure_ascii=False), encoding="utf-8",
    )

    # monkeypatch 模块级 path 指向测试文件
    monkeypatch.setattr(po, "_DEFAULT_JSON", test_default)
    monkeypatch.setattr(po, "_INTERFACE_JSON", test_interface)

    # 触发 reload (重新读 + 解析)
    result = po._load_overrides_from_frontend()

    # 验证:interface.json 的 "从奖励中心进入"=Yes case 的 entry override 都被加载
    opt = interface_data["option"]["从奖励中心进入"]
    yes_case = next(c for c in opt["cases"] if c["name"] == "Yes")
    expected_overrides = yes_case["pipeline_override"]

    assert result, "fallback 应该让 _load_overrides_from_frontend 返非空 (至少 1 个 entry)"
    for entry, expected_ov in expected_overrides.items():
        assert entry in result, (
            f"fallback 时 {entry} 应该在 result 里(实际 keys: {list(result.keys())})"
        )
        for node in expected_ov.get("next", []):
            assert node in result[entry].get("next", []), (
                f"fallback 时 {entry} 缺 next 节点: {node},"
                f"实际: {result[entry].get('next')}"
            )


def test_merged_json_sent_energy_roi_NOT_modified():
    """方案 A (2026-07-15) 起: merged.json 不允许改 ROI — 修复走 interface.json option 块。

    之前 P1-7 (2026-07-15 上午) 我直接改过 merged.json ROI,后来方案 A 要求"必须
    全部搬到 interface.json option 块",所以 merged.json 保持 narutomobile 原版
    ROI 不动。Python 端 override + interface.json option 块双轨覆盖 ROI 修复。

    回归保护: 防止有人误改 merged.json ROI (绕过方案 A 设计)。
    """
    merged_path = Path(__file__).resolve().parent.parent / "resources" / "narutomobile" / "pipeline" / "merged.json"
    assert merged_path.exists(), f"merged.json 不存在: {merged_path}"
    merged = json.loads(merged_path.read_text(encoding="utf-8"))

    # merged.json 的 ROI 必须保持 narutomobile 原版 (P1-7 之前是 P0-修复,但方案 A revert 了)
    EXPECTED_NARUTOMOBILE_SENT_ROI = [346, 571, 131, 48]
    EXPECTED_NARUTOMOBILE_GET_ROI = [519, 575, 134, 42]
    assert merged["sent_energy"]["roi"] == EXPECTED_NARUTOMOBILE_SENT_ROI, (
        f"merged.json sent_energy.roi 被改成 {merged['sent_energy']['roi']}。"
        f"方案 A 要求 merged.json 不动,ROI 修复走 interface.json option 块。"
        f"如果坚持要改,先确认 Agent 模式 + Direct API 模式都还能跑通。"
    )
    assert merged["get_energy"]["roi"] == EXPECTED_NARUTOMOBILE_GET_ROI, (
        f"merged.json get_energy.roi 被改成 {merged['get_energy']['roi']},同上"
    )
