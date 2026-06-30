"""dryrun_recruit — 真机 dry-run 招募 task。

跑完整 pipeline: 主页 → 招募 → 高级招募 → 免费 1 抽 → 跳过动画 → 关闭。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("recruit"))