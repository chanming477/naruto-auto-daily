"""诊断脚本: 跑可疑 task,每个 task 独立 sink 收集命中节点"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from core.config_manager import ConfigManager
from maafw_bridge import (
    MaaEventSink,
    MaaTaskerSingleton,
    get_tasker,
    reset_tasker,
    resolve_entry,
)
from maafw_bridge.pipeline_overrides import PIPELINE_OVERRIDES

# 业务节点特征:有这些前缀的算"业务命中"(真干活)
BIZ_HINTS = (
    "mail_",
    "headhunt_",
    "liveness_award_",
    "activity_",
    "easy_helper_",
    "rich_room_",
    "ninja_book_",
    "energy_",
    "use_energy_",
    "advanture_",
    "elite_instance_",
    "team_dash_",
    "mission_office_",
    "point_race_",
    "weekly_win_",
    "rebel_ninja_",
    "stronghold_",
    "secret_realm_",
    # 忍者指引通用业务
    "ninja_guide_find_funtion_entry",
    "up_swipe_for_ninja_guide",
    "down_swipe_for_ninja_guide",
)

# 弹窗/helper 节点特征
HELPER_HINTS = (
    "close_",
    "check_has_x",
    "check_main_screen",
    "back_main_screen",
    "leave_the_team",
    "level_up",
    "shut_social_media",
    "shut_qq",
    "im_come_back",
    "im_come_back_award",
    "naruto_club_x",
    "text_notice",
    "group_notice",
    "christmas_stocking",
    "direct_hit_quit",
    "weekly_sign",  # close weekly sign popup
)


def classify(name: str) -> str:
    if any(name.startswith(h) or name == h for h in HELPER_HINTS):
        return "HELPER"
    if any(name.startswith(b) or name == b for b in BIZ_HINTS):
        return "BIZ"
    return "OTHER"


# 6 个可疑 task(都通过 ninja_guide 路径,可能找不到入口就兜底)
TARGETS = ["group_signin", "liveness", "mission_office", "point_race", "weekly_win", "stronghold"]


def main() -> int:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    cfg = ConfigManager(PROJECT_ROOT, auto_load=True)
    reset_tasker()
    singleton = get_tasker()
    singleton.init(cfg)
    print("init done\n")

    # 2026-07-02 注入 pipeline override(全局覆盖 merged.json 里 5 个 entry 的 next 链
    # + 新增 5 个 _po_goto_* 节点)。Maafw 5.10.4 的 post_task 级别 override 不支持
    # inline dict 节点,必须用 Resource.override_pipeline() 全局注册。
    ok = singleton.resource.override_pipeline(PIPELINE_OVERRIDES)
    print(f"pipeline override applied: {ok} (覆盖 {len(PIPELINE_OVERRIDES)} 节点)\n")

    results = []
    for our_tid in TARGETS:
        entry = resolve_entry(our_tid)
        # 每个 task 独立 sink + 清空 tasker 全局 sink
        singleton.tasker.clear_context_sinks()
        sink = MaaEventSink(task_id=our_tid)
        singleton.tasker.add_context_sink(sink)

        print(f"=== {our_tid} → {entry} ===")
        t0 = time.monotonic()
        # 2026-07-02 全局 override 已在 init 后注入(见上面 override_pipeline 调用)
        # post_task 不需要再传 override — 全局生效
        try:
            job = singleton.run_task(entry)
            detail = job.wait().get()
            elapsed = time.monotonic() - t0
            status_obj = getattr(detail, "status", None)
            succeeded = getattr(status_obj, "succeeded", False) if status_obj else False
            failed = getattr(status_obj, "failed", False) if status_obj else False
            done = getattr(status_obj, "done", False) if status_obj else False
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        # 分类节点
        biz_nodes = set()
        helper_nodes = set()
        other_nodes = set()
        for n in sink.nodes:
            kind = classify(n.get("name", ""))
            name = n.get("name", "")
            if kind == "BIZ":
                biz_nodes.add(name)
            elif kind == "HELPER":
                helper_nodes.add(name)
            else:
                other_nodes.add(name)

        # 检查状态
        status_label = "Succeeded" if succeeded else ("Stopped(best-effort)" if done and failed else "Failed")

        verdict = (
            "✓ 真干活"
            if biz_nodes
            else ("✗ ** 假绿(只跑 helper) **" if (helper_nodes or done) else "? 未识别")
        )

        print(f"  status: {status_label} (succeeded={succeeded} failed={failed} done={done})")
        print(f"  elapsed: {elapsed:.1f}s")
        print(f'  业务节点({len(biz_nodes)}): {sorted(biz_nodes) or "(NONE)"}')
        print(f"  helper 节点({len(helper_nodes)}): {sorted(helper_nodes)[:8]}...")
        if other_nodes:
            print(f"  other 节点({len(other_nodes)}): {sorted(other_nodes)[:8]}...")
        print(f"  → {verdict}\n")

        results.append(
            {
                "task_id": our_tid,
                "entry": entry,
                "status": status_label,
                "biz_count": len(biz_nodes),
                "biz": sorted(biz_nodes),
                "helper_count": len(helper_nodes),
                "elapsed": round(elapsed, 1),
            }
        )

    # summary
    print("=" * 70)
    print(f'{"task_id":<20s} {"status":<25s} {"biz":>4s} {"verdict"}')
    print("-" * 70)
    for r in results:
        verdict = "✓ 真干活" if r["biz_count"] > 0 else "✗ ** 假绿 **"
        print(f'{r["task_id"]:<20s} {r["status"]:<25s} {r["biz_count"]:>4d} {verdict}')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
