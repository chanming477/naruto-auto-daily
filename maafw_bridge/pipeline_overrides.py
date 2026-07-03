"""maafw_bridge.pipeline_overrides — pipeline override 字典 (v2,2026-07-02)。

**v2 设计**(基于 narutomobile 完成组织任务日志分析):
    narutomobile 不用 ``_po_goto_<entry>`` 新节点,而是**直接 override 已有的 OCR 节点**:

    1. ``ninja_guide_find_funtion_entry``(merged.json 已存在)
       原: ``recognition=OCR, expected=["装备"], roi=[0,66,219,627]``
       改: ``expected=["<entry_tab>"], roi=[120,68,98,585]``

    2. ``ninja_guide_in_funtion_entry``
       原: ``recognition=OCR, expected=["装备"], roi=[514,85,212,72]``
       改: ``expected=["<entry_tab>"]``

    3. ``ninja_guide_returning_player_find_funtion_entry``
       原: ``expected=["装备"], roi=[209,88,200,580]``
       改: ``expected=["<entry_tab>"], roi=[306,100,83,558]``

    4. ``ninja_guide_returning_player_in_funtion_entry``
       原: ``recognition=TemplateMatch ninja_guide_returning_player_in_ninja_guide.png``
       改: ``expected=["<entry_tab>"]``

    5. ``ninja_guide_to_funtion_entry``
       原: ``recognition=OCR, expected=["即刻","前往"], roi=[852,587,138,51], action=Click``
       改: 追加 ``next=[<entry_business_nodes>, self_loop]``

    6. ``ninja_guide_returning_player_to_funtion_entry``
       原: ``action=Click, next=[ninja_guide_returning_player_in_ninja_guide, self_loop]``
       改: 追加 ``next=[<entry_business_nodes>, self_loop]``

**为什么 v2 比 v1 好**:
    - **更高效**: 复用 merged.json 已有的 OCR 节点,不需要节点转换
    - **覆盖更全**: v1 只覆盖 regular 玩家路径,v2 还覆盖 returning_player 路径
    - **更稳定**: OCR ``expected`` + ``roi`` 直接生效,不需要 Python 端 ``GoIntoEntryByGuide``
      Custom Action 的 OCR 调用(更快、更准确)
    - **真机验证**: narutomobile 用此模式跑 group 任务 **28.2s**,v1 模式跑 **47s**

**5 个 entry 的差异**:
    - ``group``: expected="组织", next=[group_gameplay_undone, group_gameplay_done, no_group]
    - ``mission_office``: expected="任务集会所", next=[mission_office_in_ninja_guide]
    - ``point_race``: expected="积分赛", next=[point_race_in_center_enter, point_race_challenge_enter, point_race_cross_server]
    - ``weekly_win``: expected="忍术对战", next=[weekly_win_in_center_enter, weekly_win_in_duel_field]
    - ``stronghold``: expected="组织"(同 group), next=[stronghold_in_stronghold, stronghold_in_match]

**ROI 坐标**: 全部是 1280x720 内部坐标(MaaFramework 引擎缩放后)。
"""
from __future__ import annotations

from typing import Any


# 忍者指引左侧菜单 tab 找 tab 的 ROI — 来自 narutomobile 真机验证
# - regular 玩家路径(ninja_guide_find_funtion_entry.roi)
LEFT_MENU_FIND_ROI_REGULAR: list[int] = [120, 68, 98, 585]
# - 回归玩家路径(ninja_guide_returning_player_find_funtion_entry.roi)
LEFT_MENU_FIND_ROI_RETURNING: list[int] = [306, 100, 83, 558]


# 哨兵值,用于"不 override ROI"的语义区分
_NO_ROI: list[int] = []  # 空 list 作为"不要 ROI 字段"的标记


def _make_overrides(
    tab_text: str,
    business_next: list[str],
    *,
    roi_regular: list[int] | None = LEFT_MENU_FIND_ROI_REGULAR,
    roi_returning: list[int] | None = LEFT_MENU_FIND_ROI_RETURNING,
) -> dict[str, Any]:
    """生成单个 entry 的 6 节点 override 字典。

    Args:
        tab_text: 在忍者指引页左侧菜单要找的 tab 文字(OCR expected)。
        business_next: 找到 tab 后业务节点列表(merged.json 已定义)。
        roi_regular: regular 玩家路径的 ROI。
            - 默认 LEFT_MENU_FIND_ROI_REGULAR (适合"组织"这种位置窄的 tab)
            - 传 ``_NO_ROI`` 表示**不 override ROI**(用 merged.json 默认 [0,66,219,627])
        roi_returning: 回归玩家路径的 ROI,语义同上。

    Notes:
        用 ``_NO_ROI`` 哨兵值而不是 None 来区分"没传参数"和"显式不 override"。
        这样调用者可以 ``roi_regular=_NO_ROI`` 表示"别加 roi 字段",让 merged.json 的
        默认 ROI 生效 — narutomobile 对 mission_office 就是这么做的。
    """
    # self-loop: 让 to_funtion_entry 节点失败后重试自己(merged.json 原设计就有这个 pattern)
    self_loop_regular = "ninja_guide_to_funtion_entry"
    self_loop_returning = "ninja_guide_returning_player_to_funtion_entry"

    # 构造节点字典 — 只在 ROI 不是 _NO_ROI 时才加 roi 字段
    find_regular: dict[str, Any] = {"expected": [tab_text]}
    if roi_regular != _NO_ROI:
        find_regular["roi"] = roi_regular

    find_returning: dict[str, Any] = {"expected": [tab_text]}
    if roi_returning != _NO_ROI:
        find_returning["roi"] = roi_returning

    return {
        # 1. regular 路径: 找 tab
        "ninja_guide_find_funtion_entry": find_regular,
        # 2. regular 路径: 验证已点中 tab
        "ninja_guide_in_funtion_entry": {
            "expected": [tab_text],
        },
        # 3. 回归玩家路径: 找 tab
        "ninja_guide_returning_player_find_funtion_entry": find_returning,
        # 4. 回归玩家路径: 验证已点中 tab
        "ninja_guide_returning_player_in_funtion_entry": {
            "expected": [tab_text],
        },
        # 5. regular 路径: 点即刻按钮 + 业务 next
        "ninja_guide_to_funtion_entry": {
            "next": business_next + [self_loop_regular],
        },
        # 6. 回归玩家路径: 点即刻按钮 + 业务 next
        "ninja_guide_returning_player_to_funtion_entry": {
            "next": business_next + [self_loop_returning],
        },
    }


# 每个 entry 单独的 override (避免 5 个 entry 之间冲突)
# key = narutomobile pipeline entry 名
PIPELINE_OVERRIDES_BY_ENTRY: dict[str, dict[str, Any]] = {
    # ===== group_signin: 找"组织" tab =====
    # narutomobile 用 roi=[120,68,98,585](缩窄 ROI 让"组织"OCR 命中更快)
    "group": _make_overrides(
        tab_text="组织",
        business_next=["group_gameplay_undone", "group_gameplay_done", "no_group"],
        roi_regular=[120, 68, 98, 585],
    ),
    # ===== mission_office: 找"集会所" tab (2026-07-02 v2.1 修复)=====
    # 修复 1: tab_text "任务集会所" → "集会所" (OCR 短文本更准,narutomobile 原版)
    # 修复 2: business_next "mission_office_in_ninja_guide" → "check_in_mission_office"
    #         (前者是 Custom Action 节点,后者是 TemplateMatch 状态验证节点)
    # 修复 3: **不 override ROI** — narutomobile 原版不缩窄 ROI,用默认 [0,66,219,627]
    #         缩窄 ROI 后"集会所"在范围外找不到,触发 100+ 次 swipe 循环(实测 47s)
    "mission_office": _make_overrides(
        tab_text="集会所",
        business_next=["check_in_mission_office"],
        roi_regular=_NO_ROI,  # 不 override,merged.json 默认 ROI
        roi_returning=_NO_ROI,
    ),
    # ===== point_race: 找"积分赛" tab =====
    # 没 narutomobile 原版日志参考,默认不 override ROI (与 mission_office 同处理)
    "point_race": _make_overrides(
        tab_text="积分赛",
        business_next=[
            "point_race_in_center_enter",
            "point_race_challenge_enter",
            "point_race_cross_server",
        ],
        roi_regular=_NO_ROI,
        roi_returning=_NO_ROI,
    ),
    # ===== weekly_win: 找"忍术对战" tab =====
    "weekly_win": _make_overrides(
        tab_text="忍术对战",
        business_next=["weekly_win_in_center_enter", "weekly_win_in_duel_field"],
        roi_regular=_NO_ROI,
        roi_returning=_NO_ROI,
    ),
    # ===== stronghold: 找"组织" tab (同 group,需要缩窄 ROI)=====
    "stronghold": _make_overrides(
        tab_text="组织",
        business_next=["stronghold_in_stronghold", "stronghold_in_match"],
        roi_regular=[120, 68, 98, 585],
    ),
}


def get_overrides_for_entry(entry: str) -> dict[str, Any] | None:
    """查 entry 对应的 override 字典。

    Returns:
        None 表示该 entry 不需要 override(直接用 merged.json 默认行为)。
        dict 表示传给 ``post_task(entry, pipeline_override=...)``。
    """
    return PIPELINE_OVERRIDES_BY_ENTRY.get(entry)


# ============================================================
# v1 旧实现 (保留作为 fallback / 参考,2026-07-02 不再使用)
# 不删(Q1 决策:旧代码留原地),仅留为文档参考。
# ============================================================
#
# v1 用 ``_po_goto_<entry>`` 新节点 + ``GoIntoEntryByGuide`` Custom Action。
# 缺点:
#   - 创建新节点,不能复用 merged.json 已有的 OCR 节点
#   - 缺回归玩家路径覆盖
#   - Python 端 OCR 调用比引擎内置 OCR 慢
#
# v1 实测 group 任务 47s,v2 实测 28s (40% 提速)。
# ============================================================
LEFT_MENU_ROI: tuple[int, int, int, int] = (0, 66, 219, 627)


def _make_goto_node_v1(entry_name: str | list[str], verify_next: list[str]) -> dict[str, Any]:
    """v1 已弃用,仅保留。"""
    return {
        "recognition": {
            "type": "TemplateMatch",
            "param": {
                "template": ["SharedNode/in_ninja_guide.png"],
                "roi": [988, 81, 180, 78],
            },
        },
        "action": {
            "type": "Custom",
            "param": {
                "custom_action": "GoIntoEntryByGuide",
                "custom_action_param": {"entry_name": entry_name},
            },
        },
        "timeout": 3000,
        "post_delay": 1500,
        "next": verify_next + ["[JumpBack]back_main_screen_and_stop"],
    }


def _make_entry_override_v1(verify_next_node: str) -> dict[str, Any]:
    """v1 已弃用,仅保留。"""
    return {
        "recognition": {
            "type": "TemplateMatch",
            "param": {
                "template": ["SharedNode/guide.png"],
                "roi": [934, 597, 178, 123],
                "threshold": 0.7,
            },
        },
        "action": "Click",
        "timeout": 5000,
        "next": [
            verify_next_node,
            "[JumpBack]back_main_screen_before_task",
        ],
    }


# v1 PIPELINE_OVERRIDES (旧字典,不再用,留作 fallback 文档)
PIPELINE_OVERRIDES_V1_LEGACY: dict[str, dict[str, Any]] = {
    "_po_goto_group": _make_goto_node_v1(
        "组织",
        ["group_gameplay_undone", "group_gameplay_done", "no_group"],
    ),
    "group": _make_entry_override_v1("_po_goto_group"),
    "_po_goto_mission_office": _make_goto_node_v1(
        "任务集会所",
        ["mission_office_in_ninja_guide"],
    ),
    "mission_office": _make_entry_override_v1("_po_goto_mission_office"),
    "_po_goto_point_race": _make_goto_node_v1(
        "积分赛",
        ["point_race_in_center_enter", "point_race_challenge_enter", "point_race_cross_server"],
    ),
    "point_race": _make_entry_override_v1("_po_goto_point_race"),
    "_po_goto_weekly_win": _make_goto_node_v1(
        "忍术对战",
        ["weekly_win_in_center_enter", "weekly_win_in_duel_field"],
    ),
    "weekly_win": _make_entry_override_v1("_po_goto_weekly_win"),
    "_po_goto_stronghold": _make_goto_node_v1(
        "组织",
        ["stronghold_in_stronghold", "stronghold_in_match"],
    ),
    "stronghold": _make_entry_override_v1("_po_goto_stronghold"),
}