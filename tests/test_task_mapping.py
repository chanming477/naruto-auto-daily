"""test_task_mapping.py — 锁定 task_mapping 的 task_id ↔ entry 映射 (v3 auto-sync)。

回归保护:
    1. 所有 1:1 映射必须保持原名(get_copper / survival_challenge / 等)
    2. 改名的 entry(recruit→headhunt, group_signin→group, liveness→liveness_award)
       必须保持稳定
    3. 合并 entry(daily_signin/monthly_signin/weekly_signin → activity)不能拆开
    4. resolve_entry() fallback: 未注册的 task_id 原样返回(允许直接传 entry)
    5. resolve_task_id() 反向查找要正确处理 activity 的"多对一"歧义
    6. **v3 (2026-07-15)** ``default.json`` 是真理源 — 改 default.json 后 Python 端自动同步

真理源: ``frontend/MFAAvalonia/config/instances/default.json`` 的 ``TaskItems`` 数组。
新增了 4 个 v3 测试:
    - test_default_json_is_source_of_truth
    - test_cli_aliases_preserved
    - test_resolve_entry_chinese_name
    - test_resolve_task_id_prefers_cli_alias
"""

from __future__ import annotations

import json
from pathlib import Path

from maafw_bridge.task_mapping import (
    CLI_ALIASES,
    REVERSE_MAPPING,
    SUPPORTED_ENTRIES,
    SUPPORTED_TASK_IDS,
    TASK_MAPPING,
    is_known_entry,
    is_supported,
    list_supported_entries,
    list_supported_tasks,
    resolve_entry,
    resolve_task_id,
)


# ============================================================
# 注册完整性
# ============================================================


def test_get_copper_and_survival_challenge_registered():
    """招财 + 生存挑战 必须在 TASK_MAPPING 里(2026-07-15 新增)。

    TASK_MAPPING 是 Chinese name → entry 映射 (从 default.json 读),
    所以用 "招财" / "生存挑战" 查 key,验证 entry 是 "get_copper" / "survival_challenge"。
    """
    assert "招财" in TASK_MAPPING, "招财 (Chinese name) 没在 TASK_MAPPING 里"
    assert TASK_MAPPING["招财"] == "get_copper", (
        f"招财 应映射到 get_copper entry,实际: {TASK_MAPPING['招财']!r}"
    )
    assert "生存挑战" in TASK_MAPPING, "生存挑战 (Chinese name) 没在 TASK_MAPPING 里"
    assert TASK_MAPPING["生存挑战"] == "survival_challenge", (
        f"生存挑战 应映射到 survival_challenge entry,实际: {TASK_MAPPING['生存挑战']!r}"
    )


def test_total_task_count_includes_new_tasks():
    """TASK_MAPPING 数量 = default.json TaskItems 数量(动态从真理源读,不硬编码)。

    2026-07-15 fix:之前 hardcode 21,但 default.json 加新 entry 后会立刻 fail。
    既然 default.json 是真理源,expected 就该从它算,不能写死。
    """
    import json

    project_root = Path(__file__).resolve().parent.parent
    default_json = project_root / "frontend" / "MFAAvalonia" / "config" / "instances" / "default.json"
    assert default_json.exists(), f"真理源不存在: {default_json}"
    data = json.loads(default_json.read_text(encoding="utf-8"))
    items = data.get("TaskItems", [])
    assert items, "default.json TaskItems 不能为空"

    # default.json 故意有 liveness_award 重复 (F0-5 收尾任务),TASK_MAPPING 按 name dedup
    # → 24 items 但 23 unique names。比较用 unique 数,不写死。
    expected = len({it["name"] for it in items if "name" in it})
    assert len(TASK_MAPPING) == expected, (
        f"任务数应 = {expected} (从 default.json TaskItems 唯一 name 数出来),"
        f"实际 {len(TASK_MAPPING)}"
    )


def test_all_one_to_one_mappings_preserved():
    """所有 1:1 entry 必须保持原名(不能错改成 narutomobile 的其他 entry)。

    TASK_MAPPING 是 Chinese name → entry 映射,key 是 Chinese name。
    """
    one_to_one = {
        "邮件领取": "mail",        # mail entry
        "一键助手": "easy_helper",
        "丰饶之间": "rich_room",
        "忍术对战": "ninja_book",
        # 2026-07-19: 赠送体力 task 已删 (F0-3 spec 写合并 send_energy_combined,
        # 但 default.json 实际只有领取体力→use_energy, 1:1 保留)
        "领取体力": "use_energy",
        "招财": "get_copper",
        "生存挑战": "survival_challenge",
    }
    for chinese_name, expected_entry in one_to_one.items():
        assert chinese_name in TASK_MAPPING, (
            f"{chinese_name} 应在 TASK_MAPPING 里 (1:1 entry)"
        )
        assert TASK_MAPPING[chinese_name] == expected_entry, (
            f"{chinese_name} 应 1:1 映射到 {expected_entry} entry,"
            f"实际: {TASK_MAPPING[chinese_name]!r}"
        )


def test_renamed_mappings_preserved():
    """CLI 别名改名映射(recruit→headhunt, group_signin→group, liveness→liveness_award)
    必须保持稳定 — 这些是 CLI 命令行 user 的术语习惯,改了就破坏 user 接口。

    这些是 CLI 别名,放在 CLI_ALIASES 里(不是 TASK_MAPPING)。
    """
    assert CLI_ALIASES["recruit"] == "headhunt", "recruit → headhunt 别名被破坏"
    assert CLI_ALIASES["group_signin"] == "group", "group_signin → group 别名被破坏"
    assert CLI_ALIASES["liveness"] == "liveness_award", "liveness → liveness_award 别名被破坏"


def test_merged_activity_entry_unchanged():
    """"activity" entry 必须被 daily_signin / monthly_signin / weekly_signin 三个 CLI 别名共用。
    拆开就破坏"一乐外卖+月签到"合并语义。
    """
    assert CLI_ALIASES["daily_signin"] == "activity"
    assert CLI_ALIASES["monthly_signin"] == "activity"
    assert CLI_ALIASES["weekly_signin"] == "activity"


# ============================================================
# v3 新增: auto-sync 真理源验证
# ============================================================


def test_default_json_is_source_of_truth():
    """``default.json`` 的 TaskItems 是真理源,改它 Python 端自动同步。

    验证: 读 default.json,跟 TASK_MAPPING 逐项匹配。
    """
    project_root = Path(__file__).resolve().parent.parent
    default_json = project_root / "frontend" / "MFAAvalonia" / "config" / "instances" / "default.json"
    assert default_json.exists(), f"真理源不存在: {default_json}"
    data = json.loads(default_json.read_text(encoding="utf-8"))
    items = data.get("TaskItems", [])
    assert items, "default.json TaskItems 不能为空"

    # 跟 TASK_MAPPING 匹配
    truth = {it["name"]: it["entry"] for it in items if "name" in it and "entry" in it}
    assert TASK_MAPPING == truth, (
        f"TASK_MAPPING 跟 default.json TaskItems 不一致!\n"
        f"default.json 说: {truth}\n"
        f"Python 端有:  {dict(TASK_MAPPING)}"
    )


def test_cli_aliases_preserved():
    """CLI 别名(英文/旧名)独立于真理源保留,不被 default.json 覆盖。"""
    assert "recruit" in CLI_ALIASES, "recruit → headhunt 别名丢失"
    assert "group_signin" in CLI_ALIASES, "group_signin → group 别名丢失"
    assert "liveness" in CLI_ALIASES, "liveness → liveness_award 别名丢失"
    assert "daily_signin" in CLI_ALIASES, "daily_signin → activity 别名丢失"
    assert "monthly_signin" in CLI_ALIASES, "monthly_signin → activity 别名丢失"
    assert "weekly_signin" in CLI_ALIASES, "weekly_signin → activity 别名丢失"

    # 别名都指向合法的 entry
    for cli_name, entry in CLI_ALIASES.items():
        assert entry in SUPPORTED_ENTRIES, (
            f"CLI 别名 {cli_name} → {entry},但 {entry} 不在 SUPPORTED_ENTRIES"
        )


def test_resolve_entry_chinese_name():
    """resolve_entry 支持 Chinese name (从 default.json 读到的 key)。"""
    # 这些 Chinese name 来自 default.json TaskItems
    assert resolve_entry("每日签到") == "activity"
    assert resolve_entry("邮件领取") == "mail"
    assert resolve_entry("组织签到") == "group"
    assert resolve_entry("招财") == "get_copper"
    assert resolve_entry("生存挑战") == "survival_challenge"
    # 同样支持英文 entry 直传
    assert resolve_entry("activity") == "activity"
    assert resolve_entry("get_copper") == "get_copper"


def test_resolve_task_id_prefers_cli_alias():
    """resolve_task_id 优先返回 CLI 英文别名(命令行 user 习惯),没有别名时返 Chinese name。

    例: headhunt → recruit (不是 "招募"),activity → daily_signin (不是 "每日签到"),
        mail → 邮件领取 (没有 CLI 别名,只能用 Chinese name)。
    """
    # 有 CLI 别名 → 用别名
    assert resolve_task_id("headhunt") == "recruit"
    assert resolve_task_id("group") == "group_signin"
    assert resolve_task_id("liveness_award") == "liveness"
    assert resolve_task_id("activity") == "daily_signin"
    # 没 CLI 别名 → 用 Chinese name
    assert resolve_task_id("mail") == "邮件领取"
    assert resolve_task_id("get_copper") == "招财"
    assert resolve_task_id("survival_challenge") == "生存挑战"


# ============================================================
# resolve_entry 行为
# ============================================================


def test_resolve_entry_known_task():
    """已知 task_id 翻译成 entry(CLI 别名 + Chinese name 都覆盖)。"""
    # CLI 别名
    assert resolve_entry("recruit") == "headhunt"
    assert resolve_entry("group_signin") == "group"
    assert resolve_entry("liveness") == "liveness_award"
    # Chinese name (从 default.json)
    assert resolve_entry("招财") == "get_copper"
    assert resolve_entry("生存挑战") == "survival_challenge"
    # 1:1 Chinese name
    assert resolve_entry("邮件领取") == "mail"


def test_resolve_entry_unknown_falls_back_to_self():
    """未注册的 task_id 原样返回(允许 caller 直接传 narutomobile entry 名)。"""
    assert resolve_entry("activity") == "activity"
    assert resolve_entry("headhunt") == "headhunt"
    assert resolve_entry("elite_instance") == "elite_instance"
    assert resolve_entry("nonexistent_entry") == "nonexistent_entry"


# ============================================================
# resolve_task_id 反向
# ============================================================


def test_resolve_task_id_known_entries():
    """entry → task_id 翻译要正确(CLI 别名优先,没别名用 Chinese name)。"""
    # 有 CLI 别名
    assert resolve_task_id("headhunt") == "recruit"
    assert resolve_task_id("liveness_award") == "liveness"
    assert resolve_task_id("activity") == "daily_signin"
    # 没 CLI 别名
    assert resolve_task_id("mail") == "邮件领取"
    assert resolve_task_id("get_copper") == "招财"
    assert resolve_task_id("survival_challenge") == "生存挑战"


def test_resolve_task_id_activity_ambiguity():
    """"activity" entry 被 3 个 task_id 共享 (daily_signin / monthly_signin / weekly_signin),
    反向查找时取 CLI_ALIASES 里第一个声明的 (daily_signin)。
    """
    assert resolve_task_id("activity") == "daily_signin", (
        "activity 反向应指向 daily_signin (CLI_ALIASES 里第一个声明)"
    )


# ============================================================
# 列表 API
# ============================================================


def test_list_supported_tasks_includes_new():
    """list_supported_tasks 必须包含 get_copper 和 survival_challenge (Chinese name)。

    list_supported_tasks 返 CLI 别名 + Chinese name (按各自插入顺序)。
    """
    tasks = list_supported_tasks()
    assert "招财" in tasks, "Chinese name '招财' 不在 list_supported_tasks"
    assert "生存挑战" in tasks, "Chinese name '生存挑战' 不在 list_supported_tasks"
    # 也要包含 CLI 别名
    assert "recruit" in tasks
    assert "daily_signin" in tasks


def test_list_supported_entries_dedupes_activity():
    """list_supported_entries 去重,activity 出现一次。"""
    entries = list_supported_entries()
    assert entries.count("activity") == 1, f"activity 应去重,实际出现 {entries.count('activity')} 次"


def test_is_supported_and_is_known_entry():
    """is_supported / is_known_entry helper 函数。"""
    # Chinese name
    assert is_supported("招财") is True
    assert is_supported("生存挑战") is True
    # CLI 别名
    assert is_supported("recruit") is True
    # 不存在
    assert is_supported("nonexistent") is False
    # entry
    assert is_known_entry("get_copper") is True
    assert is_known_entry("survival_challenge") is True
    assert is_known_entry("nonexistent_entry") is False


# ============================================================
# frozenset 完整性
# ============================================================


def test_supported_task_ids_includes_cli_and_chinese_and_entry():
    """SUPPORTED_TASK_IDS = CLI 别名 ∪ Chinese name ∪ entry (输入空间全集)。

    v3 变更: 旧 test_supported_task_ids_matches_mapping 期望
    ``SUPPORTED_TASK_IDS == TASK_MAPPING.keys()``, 但 v3 加入了 CLI 别名 + entry 直传。
    取代旧测试。
    """
    expected = (
        set(CLI_ALIASES.keys())
        | set(TASK_MAPPING.keys())
        | set(TASK_MAPPING.values())  # entry 直传
    )
    assert set(SUPPORTED_TASK_IDS) == expected


def test_supported_entries_includes_cli_and_mapping():
    """SUPPORTED_ENTRIES = CLI 别名 entry ∪ TASK_MAPPING entry,去重。"""
    expected = set(CLI_ALIASES.values()) | set(TASK_MAPPING.values())
    assert set(SUPPORTED_ENTRIES) == expected


# ============================================================
# config/schedule.json 完整性
# ============================================================


def test_daily_json_all_task_ids_valid():
    """config/schedule.json 里的 task_id 必须都在 SUPPORTED_TASK_IDS 里。

    防止 config/schedule.json 加新 task 但忘了注册 TASK_MAPPING(或反过来),
    跑 --daily-all 时报"unknown task_id"。
    """
    daily_path = Path(__file__).resolve().parent.parent / "config" / "schedule.json"
    assert daily_path.exists(), f"config/schedule.json 不存在: {daily_path}"

    daily = json.loads(daily_path.read_text(encoding="utf-8"))
    assert "task_ids" in daily, "daily.json 必须有 task_ids 字段"
    task_ids: list[str] = daily["task_ids"]
    assert task_ids, "daily.json task_ids 不能为空"

    for tid in task_ids:
        assert tid in SUPPORTED_TASK_IDS, (
            f"daily.json 里的 task_id {tid!r} 没在 SUPPORTED_TASK_IDS 里,"
            f"跑 --daily-all 会报 unknown task_id"
        )


def test_daily_json_includes_get_copper_and_survival():
    """"招财" 和 "生存挑战" 必须出现在 daily.json(2026-07-15 加进日常跑批)。

    daily.json 用的 task_id 是 entry 名 (mail / get_copper / survival_challenge) 或
    CLI 别名 (liveness / group_signin / daily_signin / recruit) — 输入空间全集。
    """
    daily_path = Path(__file__).resolve().parent.parent / "config" / "schedule.json"
    daily = json.loads(daily_path.read_text(encoding="utf-8"))
    task_ids = set(daily["task_ids"])
    # entry 名直传
    assert "get_copper" in task_ids, "招财 (get_copper) 必须出现在 daily.json"
    assert "survival_challenge" in task_ids, "生存挑战 (survival_challenge) 必须出现在 daily.json"
