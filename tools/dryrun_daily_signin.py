"""dryrun_daily_signin — 真机 dry-run 每日签到 task。

跑完整 pipeline: 主页 → 奖励 → 每日签到页 → 签到/关闭。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("daily_signin"))