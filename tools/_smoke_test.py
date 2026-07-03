"""临时验证脚本:smoke test task_engine_maafw init。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config_manager import ConfigManager

cfg = ConfigManager(Path("."), auto_load=True)
print(f"[OK] ConfigManager loaded")
print(f"[INFO] project_root: {cfg.project_root}")
print(f"[INFO] maafw config: {cfg.app.maafw}")
print(f"[INFO] narutomobile_resource_path: '{cfg.app.maafw.narutomobile_resource_path}'")
print(f"[INFO] data_dir: {cfg.app.maafw.data_dir}")

# 单独测 resource load
from maafw_bridge.resource import load_narutomobile_resource, verify_resource_path
ok, msg = verify_resource_path(cfg.project_root / "resources" / "narutomobile")
print(f"[OK] verify: ok={ok} msg={msg}")
res = load_narutomobile_resource(str(cfg.project_root / "resources" / "narutomobile"))
print(f"[OK] Resource loaded: {type(res).__name__}")

# 试 init maafw singleton (预期 ADB 失败)
from maafw_bridge import get_tasker
singleton = get_tasker()
try:
    singleton.init(cfg)
    print(f"[OK] init OK! inited={singleton.is_ready}")
except Exception as e:
    print(f"[EXPECTED] init failed at: {type(e).__name__}: {str(e)[:300]}")

# 看 maa.pipeline 提供的 API
import maa.pipeline as mp
print(f"[INFO] maa.pipeline exports: {[x for x in dir(mp) if not x.startswith('_')]}")