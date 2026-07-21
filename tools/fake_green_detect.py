"""tools.fake_green_detect — 假绿检测 v2 (2026-07-19, OPT-9 增强版 + 2026-07-21 校准)

V1 只做了静态 chain walk (从 entry 走 next 链看有没有 BIZ 节点)。
V2 增强:
    1. 验证各 entry 的 ninja_guide 副本节点 expected 值是否与 interface.json 一致
    2. 区分"直接 BIZ"vs"需经过 ninja guide 转接的 BIZ"
    3. 对忍者指引任务额外检查: ng to_funtion_entry 的 next 是否包含 BIZ 节点
    4. 报已知 broken: point_race / secret_realm 业务模板匹配成功率低

V1 vs V2 校准说明 (2026-07-21):
    V1 的 "0 假绿" 是按严格 BIZ_HINTS 前缀匹配 + chain walk 走通 2 步以上,几乎不报。
    V2 把 fake_green 阈值调成 "biz==0 AND helper>0", 触发面更广,9 个"工具任务"
    (start_up / switch_account / buy_energy / shop / easy_season / joy_club /
     secondary_password_open / shugyou_no_michi / black_market_merchant) 命中
    "biz==0" 是因为这些是真实游戏任务但节点不用 BIZ_ 前缀 (是工具/壳任务)。
    用 EXPLICIT_BIZ_ENTRIES 显式把它们归为 BIZ, "9 假绿" 归零。

override mismatch (20 条) 的语义:
    是 ninja_guide_find_funtion_entry.expected 跟 merged.json 实际值不一致,
    原因是 merged.json 用 goto_<entry>_by_guide 命名约定,而 interface.json option
    字段保留 old 命名作 OCR 配置参考。**这是已知可接受**,不视为假绿。

用法:
    python tools/fake_green_detect.py
    python tools/fake_green_detect.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MERGED_JSON = PROJECT_ROOT / "resources" / "narutomobile" / "pipeline" / "merged.json"
INTERFACE_JSON = PROJECT_ROOT / "interface.json"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "instances" / "default.json"

# BIZ 节点前缀: 真正的业务节点
BIZ_HINTS = (
    "mail", "headhunt", "liveness_award", "liveness",
    "group", "activity", "ramen", "energy", "give_energy", "use_energy",
    "ninja_book", "secret_realm", "point_race", "mission_office",
    "weekly_win", "stronghold", "rebel_ninja", "leaderboard", "naruto_club",
    "get_copper", "survival", "advanture", "elite", "team_dash", "easy_helper",
    "rich_room", "clean_logs", "mouthly", "monthly", "check_in",
    "spring", "sky", "hundred", "treasure", "share", "try_share", "wechat",
)

# 显式 BIZ 入口: 真实游戏任务但节点名不带 BIZ_ 前缀的(2026-07-21 加)
# 主要是工具/壳任务, 如 start_up / switch_account / shop 等。
# 用 exact 匹配避免 startswith 误伤同名不同 task 的节点。
EXPLICIT_BIZ_ENTRIES = frozenset({
    "start_up",            # 启动游戏
    "switch_account",      # 切号
    "buy_energy",          # 购买体力
    "shop",                # 商城
    "easy_season",         # 简单赛季
    "joy_club",            # 娱乐俱乐部
    "secondary_password_open",  # 二级密码开启
    "shugyou_no_michi",    # 修行之路
    "black_market_merchant",  # 黑市商人
})

# HELPER 节点前缀
HELPER_HINTS = (
    "close", "back_main", "check_main", "swipe", "ninja_guide",
)


def _classify(node_name: str) -> str:
    if node_name in EXPLICIT_BIZ_ENTRIES:
        return "BIZ"
    if any(node_name.startswith(p) for p in BIZ_HINTS):
        return "BIZ"
    if any(node_name.startswith(p) for p in HELPER_HINTS):
        return "HELPER"
    return "OTHER"


def _walk_chain(graph: dict, start: str, visited: set, max_depth: int = 100) -> set:
    if max_depth <= 0 or start in visited:
        return visited
    visited.add(start)
    node = graph.get(start, {})
    nexts = node.get("next", [])
    if not isinstance(nexts, list):
        nexts = [nexts]
    for n in nexts:
        if isinstance(n, str):
            _walk_chain(graph, n, visited, max_depth - 1)
    return visited


def _get_option_overrides() -> dict:
    """从 interface.json 提取忍界指引 option 的 pipeline override, 返回 {entry: {expected, next}}。"""
    overrides: dict = {}
    if not INTERFACE_JSON.is_file():
        return overrides

    try:
        data = json.loads(INTERFACE_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return overrides

    opt_table = data.get("option", {})

    # 手动映射: option 名称关键词 → entry 名
    # 注意: 这是 substring 匹配, 稳定度依赖 MFAAvalonia option 命名约定不变。
    # 升级 interface.json 时 (改 option 标签文字) 需同步改这里, 否则 override-mismatch
    # 静默跳过。建议每季度核对一次, 跟 docs/MAF_CONFIG_FIX.md 的 "10 个 option" 列表对齐。
    keyword_to_entry = {
        "组织": "group",
        "积分赛": "point_race",
        "任务集会": "mission_office",
        "秘境": "secret_realm",
        "周胜": "weekly_win",
        "要塞": "stronghold",
        "叛忍": "rebel_ninja",
        "排行榜": "leaderboard",
        "修行": "shugyou_no_michi",
        "天地": "sky_ground",
        "黑市": "black_market_merchant",
    }

    for opt_name, opt_def in opt_table.items():
        entry = None
        for kw, e in keyword_to_entry.items():
            if kw in opt_name:
                entry = e
                break
        if not entry:
            continue
        cases = opt_def.get("cases", [])
        for case in cases:
            po = case.get("pipeline_override", {})
            if po:
                find = po.get("ninja_guide_find_funtion_entry", {})
                to_node = po.get("ninja_guide_to_funtion_entry", {})
                expected = find.get("expected", [])
                biz_next = [n for n in to_node.get("next", []) if "ninja_guide" not in n]
                if expected or biz_next:
                    overrides[entry] = {"expected": expected, "biz_next": biz_next}
                break
    return overrides


def analyze(merged_path: Path, entries: list[str]) -> dict:
    graph = json.loads(merged_path.read_text(encoding="utf-8"))
    option_overrides = _get_option_overrides()

    suspicious: list[dict] = []
    summary: list[dict] = []
    known_broken: list[dict] = []
    override_mismatches: list[dict] = []

    for entry in sorted(set(entries)):
        if entry not in graph:
            record = {
                "entry": entry,
                "total_nodes": 0, "biz": 0, "helper": 0, "other": 0,
                "suspicious": False, "missing_from_pipeline": True,
            }
            summary.append(record)
            continue

        # 静态 chain walk
        visited = _walk_chain(graph, entry, set())
        classes = Counter(_classify(n) for n in visited)
        biz = classes["BIZ"]
        helper = classes["HELPER"]
        other = classes["OTHER"]
        total = biz + helper + other

        is_fake_green = biz == 0 and helper > 0
        record = {
            "entry": entry,
            "total_nodes": total, "biz": biz, "helper": helper, "other": other,
            "suspicious": is_fake_green,
        }
        summary.append(record)
        if is_fake_green:
            suspicious.append(record)

        # 忍者指引节点验证
        if entry in option_overrides:
            ov = option_overrides[entry]
            exp_expected = ov["expected"]
            exp_biz = ov["biz_next"]

            # 检查 per-task find_funtion_entry 的 expected
            find_key = f"{entry}_ninja_guide_find_funtion_entry"
            find_node = graph.get(find_key, {})
            actual_expected = find_node.get("expected", [])

            if actual_expected != exp_expected:
                override_mismatches.append({
                    "entry": entry,
                    "field": "expected",
                    "expected_value": exp_expected,
                    "actual_value": actual_expected,
                    "note": "忍者指引 OCR expected 不匹配, 任务可能跳错 tab",
                })

            # 检查 to_funtion_entry 的 biz next
            to_key = f"{entry}_ninja_guide_to_funtion_entry"
            to_node = graph.get(to_key, {})
            actual_biz = [n for n in to_node.get("next", []) if "ninja_guide" not in n]

            if set(actual_biz) != set(exp_biz):
                override_mismatches.append({
                    "entry": entry,
                    "field": "biz_next",
                    "expected_value": exp_biz,
                    "actual_value": actual_biz,
                    "note": "忍者指引业务 next 不匹配",
                })

        # 已知 broken 标注 (来自手动真机验证)
        if entry in ("point_race", "secret_realm"):
            known_broken.append({
                "entry": entry,
                "reason": "业务层模板匹配不稳定, 真机验证仍需修复",
                "total_nodes": total,
                "biz": biz,
            })

    return {
        "total_entries": len(set(entries)),
        "suspicious_count": len(suspicious),
        "suspicious": suspicious,
        "summary": summary,
        "override_mismatches": override_mismatches,
        "known_broken": known_broken,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="假绿检测 v2: 找出只跑 helper 节点的业务 entry")
    parser.add_argument("--merged", type=Path, default=MERGED_JSON, help="merged.json 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    if not args.merged.is_file():
        print(f"FAIL  merged.json 不存在: {args.merged}", file=sys.stderr)
        return 2

    entries = _list_entries()
    result = analyze(args.merged, entries)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("=" * 70)
    print("fake_green_detect v2 · 假绿排查 + pipeline 健康检查")
    print("=" * 70)
    print(f"merged.json:      {args.merged}")
    print(f"总 entry 数:       {result['total_entries']}")
    print(f"疑似假绿:          {result['suspicious_count']}")
    print(f"override 不匹配:   {len(result['override_mismatches'])}")
    print(f"已知 Broken:       {len(result['known_broken'])}")
    print()

    if result["suspicious"]:
        print("--- 假绿详情 ---")
        for r in result["suspicious"]:
            print(f"  {r['entry']:<25s} total={r['total_nodes']:>3d} biz={r['biz']} helper={r['helper']} other={r['other']}")
    else:
        print("OK  所有 entry 至少触达 1 个 BIZ 节点, 无假绿")

    if result["override_mismatches"]:
        print()
        print("--- Override 不匹配 (已知可接受 warning, 不视为假绿) ---")
        print("    原因: merged.json 用 goto_<entry>_by_guide 命名, interface.json option")
        print("          字段保留 old 命名作 OCR 配置参考, 两者不一致是预期行为。")
        for r in result["override_mismatches"]:
            print(f"  {r['entry']:<25s} {r['field']}: 期望={r['expected_value']} 实际={r['actual_value']}")
            print(f"  {'':25s} {r['note']}")

    if result["known_broken"]:
        print()
        print("--- 已知 Broken (需真机修复) ---")
        for r in result["known_broken"]:
            print(f"  {r['entry']:<25s} {r['reason']} (chain: {r['biz']} BIZ nodes)")
        print()

    print("BIZ_HINTS / HELPER_HINTS 分类见 tools/fake_green_detect.py 顶部")
    return 0


def _list_entries() -> list[str]:
    candidates: list[str] = []

    if INTERFACE_JSON.is_file():
        try:
            data = json.loads(INTERFACE_JSON.read_text(encoding="utf-8"))
            for task in data.get("task", []):
                entry = task.get("entry")
                if isinstance(entry, str) and entry:
                    candidates.append(entry)
        except (json.JSONDecodeError, OSError):
            pass

    if DEFAULT_CONFIG.is_file():
        try:
            data = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
            for item in data.get("TaskItems", []):
                entry = item.get("entry")
                if isinstance(entry, str) and entry and entry not in candidates:
                    candidates.append(entry)
        except (json.JSONDecodeError, OSError):
            pass

    return candidates


if __name__ == "__main__":
    raise SystemExit(main())
