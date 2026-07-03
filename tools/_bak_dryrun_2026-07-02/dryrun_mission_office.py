"""dryrun_mission_office — 真机 dry-run 任务集会所 task (2026-06-30 抄自 narutomobile)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dryrun_runner import run_task

if __name__ == "__main__":
    sys.exit(run_task("mission_office"))
