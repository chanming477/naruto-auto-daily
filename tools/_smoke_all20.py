"""跑全部 20 个映射任务验证全链路。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")  # 静默 info/debug

from core.config_manager import ConfigManager

cfg = ConfigManager(Path("."), auto_load=True)
print(f"[OK] ConfigManager loaded")

from tasks.task_engine_maafw import MaaTaskEngine

engine = MaaTaskEngine(cfg)
print(f"[OK] MaaTaskEngine init OK")

from maafw_bridge import list_supported_tasks

ALL_TASKS = list_supported_tasks()
print(f"[INFO] {len(ALL_TASKS)} tasks to run: {ALL_TASKS}")

results = []
overall_start = time.time()
for tid in ALL_TASKS:
    print(f"\n[TASK] {tid}")
    task_start = time.time()
    try:
        result = engine.run_task(tid)
    except Exception as e:
        print(f"  [EXC] {type(e).__name__}: {str(e)[:200]}")
        results.append((tid, "EXCEPTION", 0.0, str(e)[:200]))
        continue
    task_dur = time.time() - task_start
    status = result.status.value if hasattr(result.status, "value") else result.status
    rec = result.extra.get("recognition_count", "?")
    act = result.extra.get("action_count", "?")
    best_effort = result.extra.get("best_effort", False)
    msg = (result.message or "")[:50]
    flag = "BE" if best_effort else "OK"
    print(f"  [{flag:3s}] {status:10s} dur={task_dur:6.2f}s rec={rec} act={act} msg='{msg}'")
    results.append((tid, status, task_dur, msg))

total_dur = time.time() - overall_start
print("\n" + "=" * 80)
print(f"SUMMARY  (total: {total_dur:.1f}s)")
print("=" * 80)
print(f"  {'task_id':<20s} {'status':<12s} {'duration':<10s} {'message':<35s}")
print(f"  {'-'*20} {'-'*12} {'-'*10} {'-'*35}")
ok_count = 0
fail_count = 0
for tid, status, dur, msg in results:
    print(f"  {tid:<20s} {status:<12s} {dur:6.2f}s   {msg[:35] if msg else ''}")
    if str(status) == "TaskStatus.SUCCESS" or status == "SUCCESS":
        ok_count += 1
    else:
        fail_count += 1
print(f"\n  TOTAL: {ok_count} SUCCESS / {fail_count} FAIL / {len(results)} total")
