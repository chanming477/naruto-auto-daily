"""maafw_bridge.task_mapping — 我们 task_id ↔ narutomobile entry 映射 (auto-sync)。

真理源 (single source of truth):
    ``config/instances/default.json`` 的 ``TaskItems`` 数组
    (扁平化后从 ``frontend/MFAAvalonia/config/instances/default.json`` 移到项目根)。

该 JSON 同时被:
    1. **MFAAvalonia 前端** 渲染任务列表 / checkbox (双击启动时读)
    2. **Python 端** ``maafw_bridge.task_mapping`` 在 module load 时解析

两边自动同步 — 改 ``default.json`` 一处,Python ``TASK_MAPPING`` / CLI / 测试全部生效。

**加载策略** (defense in depth):
    1. 优先读 ``config/instances/default.json`` 的 ``TaskItems`` —
       这是 MFAAvalonia GUI 实际渲染的列表,新加任务不需要改 Python 端。
    2. 读不到时 (文件不存在 / JSON 损坏) → fallback 到 ``_HARDCODED_FALLBACK`` —
       保证即使 frontend 文件丢了 Python 端仍能跑批。
    3. ``CLI_ALIASES`` (英文别名 / 兼容旧名) 始终从 hardcoded 加载,不被 frontend 覆盖 —
       CLI 命令行约定独立于 GUI 配置。

**CLI 别名 → entry 翻译链**:
    ``resolve_entry(task_id)`` 内部:
        1. 查 ``CLI_ALIASES`` (英文别名/旧名) → 拿 entry
        2. 查 ``TASK_MAPPING`` (Chinese name → entry) — 反向用 GUI Chinese name 查
        3. 原样返回 (假定 caller 传的就是 entry)

**REVERSE_MAPPING** (entry → 我们 task_id):
    构建规则:
        - 每个 entry 选 1 个代表 task_id
        - 优先 CLI 别名 (英文: ``recruit→headhunt`` 而不是 ``招募→headhunt``)
        - 没有 CLI 别名时用 GUI Chinese name (``招募``)

这样 ``resolve_task_id("headhunt")`` 返回 ``"recruit"`` 而不是 ``"招募"`` —
跟命令行 user 习惯一致 (user 通常在命令行打英文)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

# 前端默认任务列表 (扁平化后直接在项目根 config/instances/ 下)
_FRONTEND_DEFAULT_JSON: Final[Path] = Path(
    __file__).parent.parent / "config" / "instances" / "default.json"


# ============================================================
# CLI 别名 / 旧名 (始终从 hardcoded 加载,跟 GUI 配置解耦)
# ============================================================
# Python CLI 内部约定 — 跟 Chinese name 平行,user 习惯用哪个都行
# 新加 task 时这里也加一行 (但 ``default.json`` 也要加)
CLI_ALIASES: Final[dict[str, str]] = {
    # 英文别名 (CLI 习惯)
    "recruit": "headhunt",
    "group_signin": "group",
    "liveness": "liveness_award",
    # 旧名合并 (历史 task_id 全部路由到 activity entry)
    "daily_signin": "activity",
    "monthly_signin": "activity",
    "weekly_signin": "activity",
}


# ============================================================
# 硬编码 fallback (frontend 读不到时用,保证 Python 端永不死)
# ============================================================
_HARDCODED_FALLBACK: Final[dict[str, str]] = {
    # 9 个 1:1
    "mail": "mail",
    "easy_helper": "easy_helper",
    "rich_room": "rich_room",
    "ninja_book": "ninja_book",
    "give_energy": "give_energy",
    "use_energy": "use_energy",
    "get_copper": "get_copper",
    "survival_challenge": "survival_challenge",
    # 3 个改名
    "recruit": "headhunt",
    "group_signin": "group",
    "liveness": "liveness_award",
    # 3 个合并到同一个 entry
    "daily_signin": "activity",
    "monthly_signin": "activity",
    "weekly_signin": "activity",
    # 额外 entry
    "advanture": "advanture",
    "elite_instance": "elite_instance",
    "team_dash": "team_dash",
    "mission_office": "mission_office",
    "point_race": "point_race",
    "weekly_win": "weekly_win",
    "rebel_ninja": "rebel_ninja",
    "stronghold": "stronghold",
    "secret_realm": "secret_realm",
}


# ============================================================
# 真理源加载: default.json → TASK_MAPPING (Chinese name → entry)
# ============================================================
def _load_from_frontend() -> dict[str, str] | None:
    """读 ``frontend/MFAAvalonia/config/instances/default.json`` 的 ``TaskItems``。

    Returns:
        ``{chinese_name: entry}`` 字典 (从 GUI 渲染列表构建),失败返 ``None``。

    Examples:
        >>> _load_from_frontend()
        {'每日签到': 'activity', '邮件领取': 'mail', '招财': 'get_copper', ...}
    """
    if not _FRONTEND_DEFAULT_JSON.exists():
        return None
    try:
        data = json.loads(_FRONTEND_DEFAULT_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    items = data.get("TaskItems")
    if not isinstance(items, list) or not items:
        return None
    mapping: dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        name = it.get("name")
        entry = it.get("entry")
        if isinstance(name, str) and isinstance(entry, str) and name and entry:
            mapping[name] = entry
    return mapping or None


# 我们 task_id (Chinese name) → narutomobile entry
# 真理源 = frontend default.json TaskItems;fallback = _HARDCODED_FALLBACK
TASK_MAPPING: Final[dict[str, str]] = _load_from_frontend() or dict(_HARDCODED_FALLBACK)


# 反向映射 (narutomobile entry → 我们 task_id,优先 CLI 别名)
def _build_reverse_mapping() -> dict[str, str]:
    """entry → task_id。优先 CLI 别名 (英文),没别名时用 Chinese name。

    关键: 多个 task_id 指向同一 entry 时,选哪个作"代表"由优先级决定:
        1. CLI_ALIASES 的 key (英文) — 优先 (user 命令行习惯)
        2. TASK_MAPPING 里第一个出现 (通常是 Chinese name)
    """
    # 先收 entry → 所有候选 task_id
    candidates: dict[str, list[str]] = {}
    # CLI 别名优先 (遍历 CLI_ALIASES,因为它 key 是英文 task_id)
    for cli_name, entry in CLI_ALIASES.items():
        candidates.setdefault(entry, []).append(cli_name)
    # 然后 TASK_MAPPING 的 Chinese name
    for chinese_name, entry in TASK_MAPPING.items():
        if entry in candidates:
            # 已有 CLI 别名,跳过(避免 Chinese name 覆盖)
            continue
        candidates.setdefault(entry, []).append(chinese_name)
    # 第一个出现的就是代表
    return {entry: tids[0] for entry, tids in candidates.items()}


REVERSE_MAPPING: Final[dict[str, str]] = _build_reverse_mapping()


# 列出我们支持的全部 task_id (CLI 别名 + Chinese name + entry 直传 = 输入空间全集)
# - CLI 别名: recruit, group_signin, liveness, daily_signin, monthly_signin, weekly_signin
# - Chinese name (从 default.json): 招财, 生存挑战, 邮件领取, ...
# - entry 直传: mail, get_copper, survival_challenge, ... (daily.json 实际用法)
SUPPORTED_TASK_IDS: Final[frozenset[str]] = frozenset(
    set(CLI_ALIASES.keys()) | set(TASK_MAPPING.keys()) | {v for v in TASK_MAPPING.values()})


# narutomobile 用得到的 entry 列表(去重)
SUPPORTED_ENTRIES: Final[frozenset[str]] = frozenset(
    {v for v in CLI_ALIASES.values()} | {v for v in TASK_MAPPING.values()})


# ============================================================
# 翻译 API
# ============================================================
def resolve_entry(task_id: str) -> str:
    """把我们 task_id / entry 翻译成 narutomobile entry 名。

    翻译链:
        1. ``CLI_ALIASES`` 命中 (英文别名 / 旧名) → 直接用别名映射的 entry
        2. ``TASK_MAPPING`` 命中 (Chinese name) → 用 GUI entry
        3. 都不命中 → **原样返回** (假定 caller 传的就是 entry)

    Args:
        task_id: 我们的 task_id / entry (English / Chinese 都行)。

    Returns:
        narutomobile entry 名。

    Examples:
        >>> resolve_entry("recruit")        # CLI 别名
        'headhunt'
        >>> resolve_entry("招募")           # Chinese name (GUI)
        'headhunt'
        >>> resolve_entry("headhunt")      # entry 直传
        'headhunt'
        >>> resolve_entry("daily_signin")  # 旧名
        'activity'
    """
    # 1. CLI 别名
    if task_id in CLI_ALIASES:
        return CLI_ALIASES[task_id]
    # 2. Chinese name → entry (GUI 真理源)
    if task_id in TASK_MAPPING:
        return TASK_MAPPING[task_id]
    # 3. Fallback: 原样返回 (假定是 entry 直传)
    return task_id


def resolve_task_id(entry: str) -> str | None:
    """narutomobile entry → 我们 task_id(优先 CLI 英文别名,找不到返 None)。

    Examples:
        >>> resolve_task_id("headhunt")
        'recruit'        # CLI 别名优先
        >>> resolve_task_id("activity")
        'daily_signin'   # CLI 别名里的旧名
        >>> resolve_task_id("mail")
        '邮件领取'        # 没 CLI 别名时用 Chinese name
    """
    return REVERSE_MAPPING.get(entry)


def list_supported_tasks() -> list[str]:
    """返回支持的 task_id 列表(CLI 别名在前,Chinese name 在后,去重)。"""
    seen: set[str] = set()
    out: list[str] = []
    for k in list(CLI_ALIASES.keys()) + list(TASK_MAPPING.keys()):
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def list_supported_entries() -> list[str]:
    """返回用得到的 narutomobile entry 列表(去重,按首次出现顺序)。"""
    seen: set[str] = set()
    out: list[str] = []
    for entry in list(CLI_ALIASES.values()) + list(TASK_MAPPING.values()):
        if entry not in seen:
            seen.add(entry)
            out.append(entry)
    return out


def is_supported(task_id: str) -> bool:
    """task_id 是否在我们的映射里(CLI 别名 或 Chinese name)。"""
    return task_id in SUPPORTED_TASK_IDS


def is_known_entry(entry: str) -> bool:
    """是否是用得到的 narutomobile entry。"""
    return entry in SUPPORTED_ENTRIES
