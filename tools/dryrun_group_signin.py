"""dryrun_group_signin — 真机 dry-run 组织签到 task。

跑完整 pipeline: 主页 → 忍界指引/奖励中心 → 组织签到 → 4 子链路。
V1.2 待重构: 入口在用户当前 UI 可能不在主页(待 §1.2.2 真机验证)。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("group_signin"))