"""dryrun_liveness — 真机 dry-run 活跃度 task。

跑完整 pipeline: 主页 → 奖励 → 活跃度 tab → 领奖箱。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("liveness"))