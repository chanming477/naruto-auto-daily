"""tools.fake_green_detect — 假绿检测 (OPT-9, 2026-07-19)。

目标:
    任务报 SUCCESS 但可能只跑了 helper 节点 (close_* / back_main_* / check_main_* /
    swipe_* / ninja_guide_*),实际业务节点 (mail_* / headhunt_* / group_* / energy_* /
    liveness_award_* ...) 1 个都没触发 — "假绿"。

原理 (V1, 离线分析):
    1. 读 resources/narutomobile/pipeline/merged.json
    2. 按节点名前缀分两类: BIZ_HINTS / HELPER_HINTS
    3. 对每个 entry 找其 pipeline chain (从 entry 节点出发, 跟 next 链接),
       收集触达的所有节点
    4. 如果触达集合里 0 个 BIZ 节点 + ≥ 1 个 HELPER 节点 → 疑似假绿

V1 限制 (TODO, 后续可加):
    - 仅离线分析, 不接 MaaEventSink
    - 假绿阈值保守: 0 BIZ 触发 = 假绿, 1 个 BIZ 触发 = OK (但实际可能 BIZ
      触发后 helper 处理失败也算假绿, 需要更细的统计)

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

# BIZ 节点前缀: 真正的业务节点,触达表示任务真干活了
BIZ_HINTS = (
    "mail", "headhunt", "liveness_award", "liveness",
    "group", "activity", "ramen", "energy", "give_energy", "use_energy",
    "ninja_book", "secret_realm", "point_race", "mission_office",
    "weekly_win", "stronghold", "rebel_ninja", "leaderboard", "naruto_club",
    "get_copper", "survival", "advanture", "elite", "team_dash", "easy_helper",
    "rich_room", "clean_logs", "mouthly", "monthly", "weekly", "check_in",
    "spring", "sky", "hundred", "treasure",
)

# HELPER 节点前缀: 通用辅助节点, 不算"业务进展"
HELPER_HINTS = (
    "close", "back_main", "check_main", "swipe", "ninja_guide",
    "ninja_guide_returning", "ninja_guide_in_ninja_guide", "ninja_guide_swipes",
)


def _classify(node_name: str) -> str:
    """返回节点分类: 'BIZ' / 'HELPER' / 'OTHER'。"""
    if any(node_name.startswith(p) for p in BIZ_HINTS):
        return "BIZ"
    if any(node_name.startswith(p) for p in HELPER_HINTS):
        return "HELPER"
    return "OTHER"


def _walk_chain(graph: dict, start: str, visited: set, max_depth: int = 100) -> set:
    """DFS 从 start 节点出发, 跟 next 链接, 收集触达的所有节点。"""
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


def _list_entries(merged_path: Path) -> list[str]:
    """从 interface.json / default.json / merged.json 收集所有 entry 名。

    优先级: interface.json (GUI 真理源) → default.json (TaskItems entry) → merged.json
    (顶层有 next 字段的根节点)。
    """
    candidates: list[str] = []

    # 1. interface.json
    interface = PROJECT_ROOT / "frontend" / "MFAAvalonia" / "interface.json"
    if interface.is_file():
        try:
            data = json.loads(interface.read_text(encoding="utf-8"))
            for task in data.get("task", []):
                entry = task.get("entry")
                if isinstance(entry, str) and entry:
                    candidates.append(entry)
        except (json.JSONDecodeError, OSError):
            pass

    # 2. default.json TaskItems
    default = PROJECT_ROOT / "frontend" / "MFAAvalonia" / "config" / "instances" / "default.json"
    if default.is_file():
        try:
            data = json.loads(default.read_text(encoding="utf-8"))
            for item in data.get("TaskItems", []):
                entry = item.get("entry")
                if isinstance(entry, str) and entry and entry not in candidates:
                    candidates.append(entry)
        except (json.JSONDecodeError, OSError):
            pass

    return candidates


def analyze(merged_path: Path, entries: list[str]) -> dict:
    """分析每个 entry 的 pipeline chain, 找假绿 entry。"""
    graph = json.loads(merged_path.read_text(encoding="utf-8"))

    suspicious: list[dict] = []
    summary: list[dict] = []

    for entry in sorted(set(entries)):
        if entry not in graph:
            # entry 不在 merged.json 里 (例如老 entry 被删了)
            record = {
                "entry": entry,
                "total_nodes": 0,
                "biz": 0,
                "helper": 0,
                "other": 0,
                "suspicious": False,
                "missing_from_pipeline": True,
            }
            summary.append(record)
            continue

        visited = _walk_chain(graph, entry, set())
        classes = Counter(_classify(n) for n in visited)
        biz = classes["BIZ"]
        helper = classes["HELPER"]
        other = classes["OTHER"]
        total = biz + helper + other

        is_fake_green = biz == 0 and helper > 0
        record = {
            "entry": entry,
            "total_nodes": total,
            "biz": biz,
            "helper": helper,
            "other": other,
            "suspicious": is_fake_green,
            "missing_from_pipeline": False,
        }
        summary.append(record)
        if is_fake_green:
            suspicious.append(record)

    return {
        "total_entries": len(set(entries)),
        "suspicious_count": len(suspicious),
        "suspicious": suspicious,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="假绿检测: 找出只跑 helper 节点的业务 entry")
    parser.add_argument("--merged", type=Path, default=MERGED_JSON, help="merged.json 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    if not args.merged.is_file():
        print(f"FAIL  merged.json 不存在: {args.merged}", file=sys.stderr)
        return 2

    entries = _list_entries(args.merged)
    result = analyze(args.merged, entries)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 人类可读输出
    print("=" * 70)
    print("fake_green_detect · 假绿 entry 排查")
    print("=" * 70)
    print(f"merged.json: {args.merged}")
    print(f"总 entry 数: {result['total_entries']}")
    print(f"疑似假绿:    {result['suspicious_count']}")
    print()
    if result["suspicious"]:
        print("--- 假绿详情 ---")
        for r in result["suspicious"]:
            print(f"  {r['entry']:<25s} total={r['total_nodes']:>3d} biz={r['biz']} helper={r['helper']} other={r['other']}")
    else:
        print("OK  所有 entry 至少触达 1 个 BIZ 节点, 无假绿")
    print()
    print("(BIZ_HINTS / HELPER_HINTS 分类见 tools/fake_green_detect.py 顶部)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
