"""批量跑 4 个核心任务:mail / headhunt / group / liveness_award。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")  # 静默 info/debug,只看 WARNING+

from core.config_manager import ConfigManager

cfg = ConfigManager(Path("."), auto_load=True)
print(f"[OK] ConfigManager loaded")

from tasks.task_engine_maafw import MaaTaskEngine

engine = MaaTaskEngine(cfg)
print(f"[OK] MaaTaskEngine init OK")

# 4 核心任务
CORE_TASKS = ["mail", "recruit", "group_signin", "liveness"]
results = []
for tid in CORE_TASKS:
    print(f"\n[TASK] {tid} -> entry={tid}")
    try:
        result = engine.run_task(tid)
    except Exception as e:
        print(f"  [EXC] {type(e).__name__}: {str(e)[:200]}")
        results.append((tid, "EXCEPTION", 0, str(e)[:200]))
        continue
    status = result.status.value if hasattr(result.status, "value") else result.status
    rec = result.extra.get("recognition_count", "?")
    act = result.extra.get("action_count", "?")
    best_effort = result.extra.get("best_effort", False)
    msg = (result.message or "")[:60]
    print(
        f"  status={status} dur={result.duration_sec:.2f}s rec={rec} act={act} be={best_effort} msg='{msg}'"
    )
    results.append((tid, status, result.duration_sec, result.message))

# 汇总
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
for tid, status, dur, msg in results:
    print(f"  {tid:18s} {status:10s} {dur:6.2f}s  {msg[:60] if msg else ''}")
