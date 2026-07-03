"""dryrun_easy_helper — 真机 dry-run(2026-06-30 抄自新版 MaaAutoNaruto)。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("easy_helper"))
