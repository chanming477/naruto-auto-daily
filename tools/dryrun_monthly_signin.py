"""dryrun_monthly_signin — 真机 dry-run 每月签到 task。

跑完整 pipeline: 主页 → 活动卷轴 → 活动页 → 左侧菜单下滑找"每月签到" → 签到 → 关活动页 → 回主页。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("monthly_signin"))
