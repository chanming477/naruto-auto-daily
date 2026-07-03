"""临时验证脚本:检查 merged.json + task_mapping 对齐。"""

import json
import sys
from pathlib import Path

# 确保项目根在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maafw_bridge import TASK_MAPPING

merged = json.loads(Path("resources/narutomobile/pipeline/merged.json").read_text(encoding="utf-8"))
all_keys = list(merged.keys())
print(f"[INFO] total pipeline nodes: {len(all_keys)}")

# 检查每个 mapping 的 target entry 是否存在
missing = []
for tid, entry in TASK_MAPPING.items():
    if entry not in merged:
        missing.append((tid, entry))

if missing:
    print(f"[FAIL] missing entries:")
    for tid, entry in missing:
        print(f"  {tid} -> {entry}")
else:
    print(f"[OK] all {len(TASK_MAPPING)} mapped entries exist in merged.json")

# 看 mail 节点结构
mail_node = merged.get("mail")
if mail_node and isinstance(mail_node, dict):
    print(f"[INFO] mail node keys: {list(mail_node.keys())}")
    if "next" in mail_node:
        nxt = mail_node["next"]
        print(f"[INFO] mail.next: {nxt[:5] if isinstance(nxt, list) else nxt}")

# 检查有没有 entry 风格(顶层 entry 节点)
entry_like = [
    k
    for k in all_keys
    if k
    in {
        "mail",
        "headhunt",
        "group",
        "liveness_award",
        "activity",
        "easy_helper",
        "rich_room",
        "ninja_book",
        "give_energy",
        "use_energy",
    }
]
print(f"[INFO] entry-style nodes found: {entry_like}")
