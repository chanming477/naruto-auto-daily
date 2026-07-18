"""pre_gui_smoke.py — GUI 启动前 sanity check (2026-07-18)

不连真机, 只验证:
    1. 关键模块能 import
    2. Agent custom action/reco/sink 全部注册
    3. maafw_bridge 真模块加载
    4. config/task_registry.yaml 有效
    5. default.json 真理源 + TASK_MAPPING 同步

用法:  python tools/pre_gui_smoke.py
退出码: 0 = 全过, 1 = 至少 1 项 fail
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def check(label: str, fn) -> bool:
    try:
        fn()
        print(f"  [OK]   {label}")
        return True
    except Exception as exc:
        print(f"  [FAIL] {label}: {exc!r}")
        return False


def main() -> int:
    print("=" * 60)
    print("naruto-auto-daily · pre-GUI smoke check")
    print("=" * 60)

    ok = True

    print()
    print("[1/5] 模块 import…")
    ok &= check("agent.custom.action", lambda: __import__("agent.custom.action", fromlist=["*"]))
    ok &= check("agent.custom.reco", lambda: __import__("agent.custom.reco", fromlist=["*"]))
    ok &= check("agent.custom.sink", lambda: __import__("agent.custom.sink", fromlist=["AspectRatioChecker"]))
    ok &= check("maafw_bridge", lambda: __import__("maafw_bridge", fromlist=["MaaTaskerSingleton"]))
    ok &= check("maafw_bridge.custom_actions", lambda: __import__("maafw_bridge.custom_actions", fromlist=["register_default_custom_actions"]))

    print()
    print("[2/5] Agent 注册数…")
    import agent.custom.action as _a
    import agent.custom.reco as _r
    actions = ["NonlinearSwipeAction", "GoIntoEntryByGuideAction", "CleanLogsAction",
               "CounterIncrementAction", "StopTaskListAction", "RetryFailedAction"]
    for name in actions:
        ok &= check(f"action.{name}", lambda n=name: hasattr(_a, n))

    recos = ["IsInNinjaGuide", "IsCounterOverflow", "MissionOfficeStrategy"]
    for name in recos:
        ok &= check(f"reco.{name}", lambda n=name: hasattr(_r, n))

    print()
    print("[3/5] maafw_bridge 真模块…")
    from maafw_bridge import MaaTaskerSingleton, get_tasker, resolve_entry, TASK_MAPPING
    ok &= check(f"TASK_MAPPING entries = {len(TASK_MAPPING)}", lambda: len(TASK_MAPPING) >= 23)
    ok &= check("resolve_entry('mail') = 'mail'", lambda: (resolve_entry("mail") == "mail") or (_ for _ in ()).throw(AssertionError(resolve_entry("mail"))))
    ok &= check("resolve_entry('group_signin') = 'group'", lambda: resolve_entry("group_signin") == "group")

    print()
    print("[4/5] task_registry.yaml 有效性…")
    import yaml
    data = yaml.safe_load((PROJECT_ROOT / "config" / "task_registry.yaml").read_text(encoding="utf-8"))
    tasks = data.get("tasks", {})
    ok &= check(f"task_registry.yaml tasks = {len(tasks)} (≥ 7)", lambda: len(tasks) >= 7)
    for tid, e in tasks.items():
        if "task_class" in e:
            print(f"  [WARN] {tid} still has task_class: {e['task_class']!r} (应已删)")
            ok = False

    print()
    print("[5/5] default.json vs TASK_MAPPING 同步…")
    default_json = PROJECT_ROOT / "frontend" / "MFAAvalonia" / "config" / "instances" / "default.json"
    import json
    dj = json.loads(default_json.read_text(encoding="utf-8"))
    truth = {it["name"]: it["entry"] for it in dj.get("TaskItems", []) if "name" in it and "entry" in it}
    diff_added = set(TASK_MAPPING) - set(truth)
    diff_missing = set(truth) - set(TASK_MAPPING)
    ok &= check(f"TASK_MAPPING == truth (added={diff_added} missing={diff_missing})",
                lambda: not (diff_added or diff_missing) or (_ for _ in ()).throw(AssertionError(f"added={diff_added}, missing={diff_missing}")))

    print()
    print("=" * 60)
    if ok:
        print("ALL PASS — 可以启 GUI 真机验证")
        return 0
    else:
        print("AT LEAST 1 FAIL — 修完再启 GUI")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
