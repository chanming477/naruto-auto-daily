"""maafw_bridge.pipeline_overrides — pipeline override 字典 (v3,2026-07-15 auto-sync)。

**真理源** (single source of truth,2 个文件):
    1. ``interface.json`` 的 ``option`` 块 — 包含所有可选 option 的 cases,
       每个 case 有 ``pipeline_override`` 字典(扁平化后 interface.json 在项目根)。
    2. ``config/instances/default.json`` 的 ``ResourceOptionItems`` — 当前 user
       选中的 option 值 (``{"从奖励中心进入": "Yes"}`` 等)。

**合并规则** (v3 auto-sync):
    1. **Frontend overrides** (auto-loaded):
       对 ``default.json`` 的 ``ResourceOptionItems`` 里每个 option,从 ``interface.json``
       找到对应 option,再找选中的 case,把 case 的 ``pipeline_override`` 合并起来。
       例: user 选 ``"从奖励中心进入"="Yes"`` → 自动应用 8 个 entry override
       (group / shugyou_no_michi / mission_office / weekly_win / point_race /
       secret_realm / black_market_merchant / more_gameplay)。
    2. **Hardcoded overrides** (P1-3 保留,frontend 没覆盖的部分):
       - ``give_energy`` ROI 修复 (1280x720 模拟器专用,interface.json 无此 option)
       - ``stronghold`` 忍者指南 path (frontend "从奖励中心进入" 不覆盖要塞,因要塞本身
         就是组织玩法,走忍者指南找"组织"tab)
    3. **合并**: ``PIPELINE_OVERRIDES_BY_ENTRY = {**HARDCODED, **FRONTEND}`` —
       frontend 覆盖 hardcoded,hardcoded 补 frontend 缺口。

**Fallback**: frontend 读不到时 → 只用 hardcoded,保证 Python 端永不死。

**v2 → v3 关键变化**:
    - v2 5 个 entry (group/mission_office/point_race/weekly_win/stronghold) 全部 hardcoded
    - v3 4 个 entry (mission_office/point_race/weekly_win/group) 改走 frontend auto-sync
      (跟 MFAAvalonia 前端用户配置同步),只剩 stronghold 走 hardcoded (frontend 没覆盖)
    - v3 不需要每个 entry 写一遍 ``_make_overrides(...)`` — frontend 改 default.json
      选不同的 case,Python 端自动生效
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

# 前端配置根 (扁平化后 interface.json + config/instances/default.json 在项目根)
_FRONTEND_DIR: Final[Path] = Path(__file__).parent.parent
_INTERFACE_JSON: Final[Path] = _FRONTEND_DIR / "interface.json"
_DEFAULT_JSON: Final[Path] = _FRONTEND_DIR / "config" / "instances" / "default.json"


# v2-shape option 的 pipeline_override 是节点级 (ninja_guide_* / sent_energy / get_energy),
# 跟 entry-level (group / mission_office / point_race 等) 区分。loader 用这个 set 检测
# v2-shape 并跳过(由 C# pipeline 层处理,Python 端用不上)。
# 2026-07-15 review I1 修。
_V2_SHAPE_NODE_KEYS: Final[frozenset[str]] = frozenset({
    "ninja_guide_find_funtion_entry",
    "ninja_guide_in_funtion_entry",
    "ninja_guide_to_funtion_entry",
    "ninja_guide_returning_player_find_funtion_entry",
    "ninja_guide_returning_player_in_funtion_entry",
    "ninja_guide_returning_player_to_funtion_entry",
    "sent_energy",
    "get_energy",
})


def _is_v2_shape_override(po: dict[str, Any]) -> bool:
    """判断 case.pipeline_override 是否 v2-shape (节点级) vs v3-shape (entry 级)。

    v2-shape: keys 全是已知 pipeline 节点名 (ninja_guide_* / sent_energy / get_energy),
              由 MFAAvalonia C# pipeline 层在运行时覆盖,Python 端不需要。

    v3-shape: keys 是 entry 名 (group / mission_office / point_race 等),
              Python 端 post_task(entry, pipeline_override=...) 时用。

    Returns:
        True = v2-shape (loader 跳过,Python 不处理)
        False = v3-shape (loader 正常加载)
    """
    return set(po.keys()) <= _V2_SHAPE_NODE_KEYS


# ============================================================
# Frontend auto-loader: 读 interface.json + default.json
# ============================================================
def _load_overrides_from_frontend() -> dict[str, dict[str, Any]]:
    """读 frontend 两个 JSON,合并 user 选中的 option case 的 pipeline_override。

    只加载 v3-shape override (entry 级)。v2-shape (节点级, 如 ``忍界指引寻找排行榜``)
    跳过 — 由 MFAAvalonia C# pipeline 层处理。

    Returns:
        ``{entry: pipeline_override}`` 字典,失败返 ``{}``。

    Examples:
        ``default.json`` 有 ``{"从奖励中心进入": "Yes"}`` →
        返回 8 个 entry 的 next override (group / shugyou_no_michi / ...)。
    """
    if not _INTERFACE_JSON.exists() or not _DEFAULT_JSON.exists():
        return {}
    try:
        interface = json.loads(_INTERFACE_JSON.read_text(encoding="utf-8"))
        default = json.loads(_DEFAULT_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    options: dict[str, Any] = interface.get("option") or {}
    selected: dict[str, str] = default.get("ResourceOptionItems") or {}
    if not isinstance(options, dict) or not isinstance(selected, dict):
        return {}

    # Fallback (2026-07-16 修正注): MFAAvalonia 启动会重写 default.json,
    # 把 ResourceOptionItems 清空 (用户没动过 GUI 时)。这 3 个核心 option
    # **期望** Yes (无论 interface.json 有无 default_case,我们主动 fallback)。
    # 行为: selected 没选某 option 时 fallback 用 "Yes";selected 选了时尊重 user。
    _FALLBACK_YES_OPTIONS: Final[frozenset[str]] = frozenset({
        "从奖励中心进入",
        "1280x720 模拟器 ROI 修复",
        "从忍者指南寻找组织",
    })

    merged: dict[str, dict[str, Any]] = {}
    skipped_v2: list[str] = []
    for opt_name, opt in options.items():
        if not isinstance(opt, dict):
            continue
        # 选 user 的值;没选则用 fallback
        if opt_name in selected:
            opt_value = selected[opt_name]
        elif opt_name in _FALLBACK_YES_OPTIONS:
            opt_value = "Yes"
        else:
            continue  # user 没选 + 不在 fallback 列表,跳过
        cases = opt.get("cases")
        if not isinstance(cases, list):
            continue
        # 找到 case
        for case in cases:
            if not isinstance(case, dict):
                continue
            if case.get("name") == opt_value:
                po = case.get("pipeline_override")
                if isinstance(po, dict):
                    # v2-shape (节点级): 跳过,Python 端用不上
                    if _is_v2_shape_override(po):
                        skipped_v2.append(opt_name)
                    else:
                        # v3-shape (entry 级): 合并
                        for entry, override in po.items():
                            if not isinstance(override, dict):
                                continue
                            if entry in merged:
                                merged[entry].update(override)
                            else:
                                merged[entry] = dict(override)
                break  # 找到 case 就 break

    if skipped_v2:
        from loguru import logger as _log
        _log.debug(
            "Skipped v2-shape options (C# pipeline layer handles): {}",
            skipped_v2,
        )
    return merged


# ============================================================
# Hardcoded overrides (frontend 没覆盖的部分,补缺口)
# ============================================================
# 忍者指引左侧菜单 tab 找 tab 的 ROI — 来自 narutomobile 真机验证
# - regular 玩家路径(ninja_guide_find_funtion_entry.roi)
LEFT_MENU_FIND_ROI_REGULAR: list[int] = [120, 68, 98, 585]
# - 回归玩家路径(ninja_guide_returning_player_find_funtion_entry.roi)
LEFT_MENU_FIND_ROI_RETURNING: list[int] = [306, 100, 83, 558]


# 哨兵值,用于"不 override ROI"的语义区分
_NO_ROI = object()  # 单例哨兵,身份安全


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
    """
    self_loop_regular = "ninja_guide_to_funtion_entry"
    self_loop_returning = "ninja_guide_returning_player_to_funtion_entry"

    find_regular: dict[str, Any] = {"expected": [tab_text]}
    if roi_regular is not _NO_ROI:
        find_regular["roi"] = roi_regular

    find_returning: dict[str, Any] = {"expected": [tab_text]}
    if roi_returning is not _NO_ROI:
        find_returning["roi"] = roi_returning

    return {
        "ninja_guide_find_funtion_entry": find_regular,
        "ninja_guide_in_funtion_entry": {"expected": [tab_text]},
        "ninja_guide_returning_player_find_funtion_entry": find_returning,
        "ninja_guide_returning_player_in_funtion_entry": {"expected": [tab_text]},
        "ninja_guide_to_funtion_entry": {"next": business_next + [self_loop_regular]},
        "ninja_guide_returning_player_to_funtion_entry": {"next": business_next + [self_loop_returning]},
    }


# Hardcoded override (P1-3 2026-07-15 保留,frontend 不覆盖的)
_HARDCODED_OVERRIDES: dict[str, dict[str, Any]] = {
    # ===== stronghold: 找"组织" tab (同 group,需要缩窄 ROI) =====
    # frontend "从奖励中心进入" Yes case **不覆盖** stronghold (要塞 = 组织玩法,走忍者指南),
    # 所以保留 hardcoded。
    "stronghold": _make_overrides(
        tab_text="组织",
        business_next=["stronghold_in_stronghold", "stronghold_in_match"],
        roi_regular=[120, 68, 98, 585],
    ),
    # ===== give_energy: 修 narutomobile 默认 ROI (2026-07-15 修复) =====
    # 背景: 用户的 1280x720 模拟器画面里,"一键赠送"按钮 y 中心 ≈ 660,
    # narutomobile 默认 sent_energy.roi=[346,571,131,48] 覆盖 y=571-619,
    # **整个按钮都在 ROI 下方 16-66 像素**,OCR 找不到 → 22s 超时。
    # 同样的问题在 get_energy.roi=[519,575,134,42] 也有("一键领取" y ≈ 660)。
    # 修复: extend ROI y 范围到 630-690,正好覆盖两个按钮所在的底栏。
    # 上游 interface.json 没 override 这两个节点(narutomobile 用的是更高分辨率
    # 模拟器,默认 ROI 没问题),这是 1280x720 模拟器特有的修。
    # 注: merged.json 已同步改 ROI (2026-07-15),这里仍保留 hardcoded 作为
    # defense in depth — 如果用户换模拟器分辨率,可以快速改 Python 端。
    "give_energy": {
        "sent_energy": {"roi": [340, 630, 110, 60]},
        "get_energy": {"roi": [519, 630, 110, 60]},
    },
}


# ============================================================
# 最终 PIPELINE_OVERRIDES_BY_ENTRY = hardcoded + frontend (frontend 优先)
# ============================================================
_FRONTEND_OVERRIDES: dict[str, dict[str, Any]] = _load_overrides_from_frontend()

# 合并:hardcoded 在前(被覆盖),frontend 在后(覆盖)
PIPELINE_OVERRIDES_BY_ENTRY: dict[str, dict[str, Any]] = {
    **_HARDCODED_OVERRIDES,
    **_FRONTEND_OVERRIDES,
}


def get_overrides_for_entry(entry: str) -> dict[str, Any] | None:
    """查 entry 对应的 override 字典。

    Returns:
        None 表示该 entry 不需要 override(直接用 merged.json 默认行为)。
        dict 表示传给 ``post_task(entry, pipeline_override=...)``。
    """
    return PIPELINE_OVERRIDES_BY_ENTRY.get(entry)


# ============================================================
# v1 旧实现 — 2026-07-15 清理删除。历史行为见 git log.
# ============================================================
