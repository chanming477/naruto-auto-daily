"""dryrun_activity — 真机 dry-run 活动 task。

跑完整 pipeline: 主页 → 活动 → 一乐拉面 → 领奖。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("activity"))