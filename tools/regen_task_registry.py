"""tools.regen_task_registry — 从 default.json TaskItems 重新生成 task_registry.yaml。

**为什么**: 2026-07-21 R2 review I1 指出, ``config/task_registry.yaml`` 8 个
任务的元数据跟实际 ``config/instances/default.json`` 43 个 TaskItems
严重脱节,``main.py --check`` step 3 报"注册了 8 个任务"误导用户。

**用法**:
    python tools/regen_task_registry.py            # 干跑, 打印 diff 不写
    python tools/regen_task_registry.py --write    # 实际写文件

**行为**:
    1. 读 ``config/instances/default.json`` 的 ``TaskItems`` (真理源)
    2. 对每个 entry,从现有的 ``config/task_registry.yaml`` 读元数据
       (enabled / display_order / category / description / ...)
    3. 如果元数据存在 → 保留(尊重人工决策)
       如果元数据不存在 → 用 entry 名生成默认元数据
    4. 不在 ``default.json`` 的旧 task (recruit / daily_signin / activity / weekly_signin /
       monthly_signin) → 标记 ``enabled: false``, 留历史记录但不参与新流水线
    5. 输出: 重写后的 ``task_registry.yaml``, 头部说明它不再是真理源
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = PROJECT_ROOT / "config" / "instances" / "default.json"
REGISTRY_YAML = PROJECT_ROOT / "config" / "task_registry.yaml"

# 手动元数据覆盖 (从原 task_registry.yaml 继承, 后续人工调整)
# key = task_id (CLI 别名或 default.json 的 Chinese name)
_LEGACY_OVERRIDES: dict[str, dict[str, Any]] = {
    "recruit":         {"display_order": 6, "category": "daily"},
    "weekly_signin":   {"display_order": 7, "category": "weekly",
                        "description": "每周签到 (P0-1 2026-06-29 模板 weekly_sign.png 移入 deprecated, "
                                       "当前 best-effort 跳过, 需补采)"},
    "activity":        {"display_order": 8, "category": "weekly",
                        "description": "一乐外卖活动签到 (需采集 activity/ramen.png 等内部模板, 部分已采)"},
    "monthly_signin":  {"display_order": 9, "category": "monthly",
                        "description": "每月签到 (活动页左侧菜单'每月签到' tab, 通过 OCR 引导)"},
}

# 旧 task (不在 default.json) 的元数据保留 (留作历史参考, enabled=false)
_LEGACY_TASKS: dict[str, dict[str, Any]] = {
    "daily_signin": {
        "enabled": False, "display_order": 5, "category": "daily",
        "description": "[已废弃] 每日签到 (旧 entry, 现并入 activity)",
        "estimated_time_sec": 30, "retry_on_failure": True, "max_retries": 2,
        "config_options": {},
    },
    "mail": {
        "enabled": False, "display_order": 2, "category": "daily",
        "description": "[已废弃] 邮件领取 (Phase 6 旧实现, 现走 mail entry)",
        "estimated_time_sec": 20, "retry_on_failure": True, "max_retries": 1,
        "config_options": {},
    },
    "liveness": {
        "enabled": False, "display_order": 3, "category": "daily",
        "description": "[已废弃] 活跃奖励 (现走 liveness_award entry)",
        "estimated_time_sec": 25, "retry_on_failure": True, "max_retries": 2,
        "config_options": {},
    },
    "group_signin": {
        "enabled": False, "display_order": 4, "category": "daily",
        "description": "[已废弃] 组织签到 (现走 group entry)",
        "estimated_time_sec": 25, "retry_on_failure": True, "max_retries": 1,
        "config_options": {},
    },
    "recruit": {
        "enabled": False, "display_order": 6, "category": "daily",
        "description": "[已废弃] 招募 (现走 headhunt entry, templates 共享)",
        "estimated_time_sec": 25, "retry_on_failure": True, "max_retries": 1,
        "config_options": {},
    },
    "weekly_signin": {
        "enabled": False, "display_order": 7, "category": "weekly",
        "description": "[已废弃] 每周签到 (现并入 activity entry, best-effort 跳过)",
        "estimated_time_sec": 20, "retry_on_failure": False, "max_retries": 0,
        "config_options": {},
    },
    "activity": {
        "enabled": False, "display_order": 8, "category": "weekly",
        "description": "[已废弃] 一乐外卖活动 (现走 activity entry)",
        "estimated_time_sec": 30, "retry_on_failure": True, "max_retries": 1,
        "config_options": {},
    },
    "monthly_signin": {
        "enabled": False, "display_order": 9, "category": "monthly",
        "description": "[已废弃] 每月签到 (现并入 activity entry, 通过左侧菜单 tab)",
        "estimated_time_sec": 25, "retry_on_failure": True, "max_retries": 1,
        "config_options": {},
    },
}


def _load_default_json() -> list[dict[str, Any]]:
    """读 default.json 的 TaskItems, 返回 list[{name, entry, ...}]"""
    if not DEFAULT_JSON.is_file():
        print(f"FAIL  default.json 不存在: {DEFAULT_JSON}", file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL  default.json 解析失败: {exc}", file=sys.stderr)
        sys.exit(2)
    items = data.get("TaskItems", [])
    if not isinstance(items, list):
        print("FAIL  default.json TaskItems 不是 list", file=sys.stderr)
        sys.exit(2)
    return [it for it in items if isinstance(it, dict)]


def _load_existing_registry() -> dict[str, dict[str, Any]]:
    """读现有 task_registry.yaml 全部 task_id 元数据。失败返 {}。"""
    if not REGISTRY_YAML.is_file():
        return {}
    try:
        import yaml
        data = yaml.safe_load(REGISTRY_YAML.read_text(encoding="utf-8")) or {}
        return data.get("tasks", {}) or {}
    except Exception:
        return {}


def _build_entry(item: dict[str, Any], existing: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """从 default.json 一个 TaskItem + 现有元数据构建新 entry。

    Returns:
        (task_id, entry_dict)
        task_id 优先用 entry 名 (跟 CLI 习惯一致), 缺则用 Chinese name
    """
    entry_name = item.get("entry", "")
    chinese_name = item.get("name", "")
    task_id = entry_name or chinese_name
    if not task_id:
        return "", {}

    # 现有元数据: 找 task_id 或 entry_name 命中的
    prior = existing.get(task_id) or existing.get(entry_name) or {}

    # 继承 enabled / display_order / category / config_options, 其它用默认
    merged: dict[str, Any] = {
        "enabled": prior.get("enabled", True),
        "display_order": prior.get("display_order", 0),
        "category": prior.get("category", "uncategorized"),
        "description": prior.get("description", f"{chinese_name or entry_name} (从 default.json TaskItems 加载)"),
        "estimated_time_sec": prior.get("estimated_time_sec", 30),
        "retry_on_failure": prior.get("retry_on_failure", True),
        "max_retries": prior.get("max_retries", 1),
        "config_options": prior.get("config_options", {}),
    }

    # 手动覆盖优先 (from _LEGACY_OVERRIDES, 留作过渡期参考)
    if task_id in _LEGACY_OVERRIDES:
        for k, v in _LEGACY_OVERRIDES[task_id].items():
            merged[k] = v

    return task_id, merged


def _build_yaml(new_tasks: dict[str, dict[str, Any]]) -> str:
    """生成 task_registry.yaml 完整内容。"""
    lines: list[str] = [
        "# ============================================================",
        "# naruto-auto-daily · 任务注册表 (元数据,非真理源) — 自动生成 2026-07-21",
        "#",
        "# 真理源: ``config/instances/default.json`` 的 ``TaskItems`` 数组",
        "# (扁平化后路径,原 frontend/MFAAvalonia/config/instances/default.json)",
        "# 改任务入口请改 default.json, 改元数据 (enabled/display_order/category/description)",
        "# 请编辑本文件 + 跑 ``python tools/regen_task_registry.py --write`` 同步。",
        "#",
        "# 用 ``python tools/regen_task_registry.py --write`` 重生成本文件;",
        "# 不用 ``--write`` 只打印 diff, 不会写盘。",
        "#",
        "# P2-6 2026-07-18 已删 core.scheduler (含 _NoopTask), 任务元数据统一由 MaaTaskEngine",
        "# 走 default.json TaskItems 自动加载, 本文件只是元数据展示 + 命令行任务列表。",
        "#",
        "# 字段说明(按 task_id 为 key):",
        "#   enabled            : bool, 是否默认启用 (手动决策)",
        "#   display_order      : int, 排序键 (手动决策)",
        "#   category           : 分类字符串 (daily / weekly / pvp / shop / mail ...)",
        "#   description        : 一句话说明",
        "#   estimated_time_sec : 预估耗时 (仅展示用)",
        "#   retry_on_failure   : bool, 失败是否重试",
        "#   max_retries        : int, 最大重试次数",
        "#   config_options     : dict, 任务级参数",
        "# ============================================================",
        "",
        "tasks:",
    ]
    for tid in sorted(new_tasks):
        entry = new_tasks[tid]
        lines.append(f"  {tid}:")
        lines.append(f"    enabled: {str(entry['enabled']).lower()}")
        lines.append(f"    display_order: {entry['display_order']}")
        lines.append(f"    category: {entry['category']!r}")
        # description 含中文 / 特殊字符,用 YAML 单引号
        desc = str(entry['description']).replace("'", "''")
        lines.append(f"    description: '{desc}'")
        lines.append(f"    estimated_time_sec: {entry['estimated_time_sec']}")
        lines.append(f"    retry_on_failure: {str(entry['retry_on_failure']).lower()}")
        lines.append(f"    max_retries: {entry['max_retries']}")
        lines.append(f"    config_options: {{}}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="从 default.json 重新生成 task_registry.yaml")
    parser.add_argument("--write", action="store_true", help="实际写盘 (默认只打印)")
    args = parser.parse_args()

    items = _load_default_json()
    existing = _load_existing_registry()

    # 1. 从 default.json 构建主表
    new_tasks: dict[str, dict[str, Any]] = {}
    for it in items:
        tid, entry = _build_entry(it, existing)
        if tid:
            new_tasks[tid] = entry

    # 2. 保留 _LEGACY_TASKS (历史参考, enabled=false)
    for tid, entry in _LEGACY_TASKS.items():
        if tid not in new_tasks:
            new_tasks[tid] = entry

    new_content = _build_yaml(new_tasks)
    print(f"TaskItems: {len(items)} (从 default.json)")
    print(f"生成 task: {len(new_tasks)} (含 {len(_LEGACY_TASKS)} 个 legacy 标记)")
    print()
    if args.write:
        REGISTRY_YAML.write_text(new_content, encoding="utf-8")
        print(f"[OK] 已写: {REGISTRY_YAML}")
    else:
        print("--- DRY RUN (加 --write 实际写) ---")
        print(new_content[:1500])
        if len(new_content) > 1500:
            print(f"\n... ({len(new_content) - 1500} more chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
