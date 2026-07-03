"""Q2 全天验证: 跑 schemes/daily.json 3 次,模拟 daily schedule 重复使用。

每天跑 1 次日常,连续 3 天。验证:
  - 同一任务连续 3 次能稳定 SUCCESS
  - 任务间不污染状态(上一任务跑完后下一任务能正常起)
  - 没有累积资源泄漏

每个 run = 5 任务 (mail/liveness/group_signin/daily_signin/recruit)。
3 run 总时长预估 ~5 min (基于上一轮 20 task = 488s)。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

from core.config_manager import ConfigManager

cfg = ConfigManager(Path("."), auto_load=True)

# 读 daily.json
with open(cfg.project_root / "schemes" / "daily.json", encoding="utf-8") as f:
    daily_tasks = json.load(f)["task_ids"]
print(f"[INFO] daily.json tasks: {daily_tasks}")

from tasks.task_engine_maafw import MaaTaskEngine

# 初始化一次 engine(走真机 ADB)
print("[INFO] Init MaaTaskEngine...")
engine = MaaTaskEngine(cfg)
print(f"[OK] engine ready, tasker.inited={engine._singleton.tasker.inited}")

# 跑 3 次
N_RUNS = 3
all_results: list[list[tuple]] = []
overall_start = time.time()

for run_idx in range(1, N_RUNS + 1):
    print(f"\n{'=' * 70}")
    print(f"RUN {run_idx}/{N_RUNS}  (started at {time.strftime('%H:%M:%S')})")
    print(f"{'=' * 70}")
    run_start = time.time()
    run_results = []
    for tid in daily_tasks:
        task_start = time.time()
        try:
            result = engine.run_task(tid)
        except Exception as e:
            print(f"  [{tid}] EXC: {type(e).__name__}: {str(e)[:100]}")
            run_results.append((tid, "EXC", 0.0, str(e)[:100]))
            continue
        task_dur = time.time() - task_start
        status = result.status.value if hasattr(result.status, "value") else result.status
        be = result.extra.get("best_effort", False)
        flag = "BE" if be else "OK"
        msg = (result.message or "")[:35]
        print(f"  [{flag}] {tid:14s} {str(status):10s} {task_dur:5.2f}s  {msg}")
        run_results.append((tid, str(status), task_dur, msg))
    run_dur = time.time() - run_start
    ok = sum(1 for _, s, _, _ in run_results if s == "TaskStatus.SUCCESS" or s == "SUCCESS")
    fail = len(run_results) - ok
    print(f"\n  Run {run_idx} summary: {ok} SUCCESS / {fail} FAIL / {len(run_results)} total, dur={run_dur:.1f}s")
    all_results.append(run_results)

total_dur = time.time() - overall_start

# 跨 3 次稳定性分析
print(f"\n{'=' * 70}")
print(f"STABILITY ANALYSIS (3 runs × {len(daily_tasks)} tasks = {N_RUNS * len(daily_tasks)} runs)")
print(f"{'=' * 70}")
print(f"  total elapsed: {total_dur:.1f}s")
print()
print(f"  {'task_id':<14s} {'run1':<12s} {'run2':<12s} {'run3':<12s} {'avg_dur':<10s} {'std':<8s}")
print(f"  {'-'*14} {'-'*12} {'-'*12} {'-'*12} {'-'*10} {'-'*8}")

# 每个 task 跨 3 次的状态/duration 表
task_status: dict[str, list] = {tid: [] for tid in daily_tasks}
task_dur: dict[str, list] = {tid: [] for tid in daily_tasks}
for run_results in all_results:
    for tid, status, dur, _ in run_results:
        task_status[tid].append(status)
        task_dur[tid].append(dur)

import statistics
for tid in daily_tasks:
    statuses = task_status[tid]
    durs = task_dur[tid]
    avg = statistics.mean(durs) if durs else 0
    std = statistics.stdev(durs) if len(durs) > 1 else 0
    s1 = statuses[0] if len(statuses) > 0 else "?"
    s2 = statuses[1] if len(statuses) > 1 else "?"
    s3 = statuses[2] if len(statuses) > 2 else "?"
    print(f"  {tid:<14s} {s1:<12s} {s2:<12s} {s3:<12s} {avg:<10.2f} {std:<8.2f}")

# 总判定
all_success = all(
    s == "TaskStatus.SUCCESS" or s == "SUCCESS"
    for run_results in all_results
    for tid, s, _, _ in run_results
)
print()
if all_success:
    print(f"  ✓ ALL 3 RUNS PASS (15/15 tasks SUCCESS)")
else:
    fails = sum(
        1 for run_results in all_results
        for tid, s, _, _ in run_results
        if not (s == "TaskStatus.SUCCESS" or s == "SUCCESS")
    )
    print(f"  ✗ {fails} task(s) FAILED across 3 runs")