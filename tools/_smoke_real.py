"""临时验证脚本:跑一个真实任务验证全链路。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

from core.config_manager import ConfigManager

cfg = ConfigManager(Path("."), auto_load=True)
print(f"[OK] ConfigManager loaded")

from tasks.task_engine_maafw import MaaTaskEngine

print(f"[INFO] Creating MaaTaskEngine...")

try:
    engine = MaaTaskEngine(cfg)
    print(f"[OK] MaaTaskEngine init OK")
except Exception as e:
    print(f"[FAIL] MaaTaskEngine init: {type(e).__name__}: {e}")
    sys.exit(1)

# 跑 mail 任务
print(f"\n[INFO] Running task: mail")
result = engine.run_task("mail")
print(f"\n[RESULT] mail: status={result.status.value if hasattr(result.status, 'value') else result.status}")
print(f"  duration_sec: {result.duration_sec:.2f}")
print(f"  message: {result.message}")
print(f"  extra keys: {list(result.extra.keys())}")
print(f"  recognition_count: {result.extra.get('recognition_count', '?')}")
print(f"  action_count: {result.extra.get('action_count', '?')}")
print(f"  best_effort: {result.extra.get('best_effort', '?')}")
