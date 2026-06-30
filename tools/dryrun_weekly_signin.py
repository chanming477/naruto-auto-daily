"""dryrun_weekly_signin — 真机 dry-run 每周签到 task (V1.2 重点验证)。

跑完整 pipeline: 主页 → 活动 → 活动页 → 每月签到 → 签到。
V1.2 真机跑通 (2026-06-26): count 25/30 → 26/30, day 26 红章。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("weekly_signin"))