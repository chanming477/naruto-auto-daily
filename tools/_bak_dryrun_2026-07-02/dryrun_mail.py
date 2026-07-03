"""dryrun_mail — 真机 dry-run 邮件 task。

跑完整 pipeline: 主页 → 邮件信封 → 邮件页 → 一键提取 → 关闭 → 主页。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("mail"))