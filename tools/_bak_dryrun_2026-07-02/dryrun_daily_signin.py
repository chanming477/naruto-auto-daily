"""dryrun_daily_signin — 真机 dry-run 每日签到 task。

2026-07-01 改写:A 计划验证"每日签到 = 活动页→每月签到 tab",路径已切到 monthly 路径。
跑完整 pipeline: 主页 → 活动入口(headhunt)→ 活动页 → 左侧菜单下滑 → 每月签到 tab → 签到 → 回主页。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("daily_signin"))