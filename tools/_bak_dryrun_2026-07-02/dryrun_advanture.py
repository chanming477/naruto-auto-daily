"""dryrun_<task_id> — 真机 dry-run wrapper(2026-06-30 抄自新版 MaaAutoNaruto)。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("advanture"))
