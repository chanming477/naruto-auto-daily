"""maafw_bridge.task_mapping — 我们 task_id ↔ narutomobile entry 映射。

11 个本项目 task_id 全部能在 narutomobile 36 个 entry 中找到对应。
3 个名字不一样 + 1 个合并(daily_signin / monthly_signin → activity):

    | 我们 task_id       | narutomobile entry  | 备注              |
    |--------------------|---------------------|-------------------|
    | mail               | mail                | 1:1               |
    | recruit            | headhunt            | 改名              |
    | group_signin       | group               | 改名              |
    | liveness           | liveness_award      | 改名              |
    | daily_signin       | activity            | 合并到 activity   |
    | monthly_signin     | activity            | 合并到 activity   |
    | easy_helper        | easy_helper         | 1:1               |
    | rich_room          | rich_room           | 1:1               |
    | ninja_book         | ninja_book          | 1:1               |
    | give_energy        | give_energy         | 1:1               |
    | use_energy         | use_energy          | 1:1               |

注意:
    - ``activity`` 在 narutomobile 是"月签到 + 一乐拉面"合并 entry,
      不能分别跑 ``daily_signin`` 和 ``monthly_signin`` —
      跑一次 activity 即可(对应一个 entry)。
    - **额外 entry** (narutomobile 有但本项目没有):
      elite_instance / team_dash / mission_office / point_race / weekly_win /
      rebel_ninja / stronghold / secret_realm。
      这些是 narutomobile 自带的"高级玩法"任务,本项目暂未单独接入,
      但通过 ``resolve_entry()`` 走 fallback 机制仍可调用。
"""

from __future__ import annotations

from typing import Final

# 我们 task_id → narutomobile entry
TASK_MAPPING: Final[dict[str, str]] = {
    # 7 个 1:1
    "mail": "mail",
    "easy_helper": "easy_helper",
    "rich_room": "rich_room",
    "ninja_book": "ninja_book",
    "give_energy": "give_energy",
    "use_energy": "use_energy",
    # 3 个改名
    "recruit": "headhunt",
    "group_signin": "group",
    "liveness": "liveness_award",
    # 2 个合并到同一个 entry
    "daily_signin": "activity",
    "monthly_signin": "activity",
    # 额外 entry(本项目暂未单独注册,直接传 task_id 也能跑)
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

# 反向映射(narutomobile entry → 我们 task_id,多个时取首个)
REVERSE_MAPPING: Final[dict[str, str]] = {
    entry: tid for tid, entry in TASK_MAPPING.items() if entry not in {"activity"} or tid == "daily_signin"
}
# 显式: activity 反向映射到 daily_signin(第一个用 daily_signin 名字注册的)
# 注: REVERSE_MAPPING 第一个见到的 entry 是 daily_signin(已确保上面 if 保留)

# 列出我们支持的全部 task_id
SUPPORTED_TASK_IDS: Final[frozenset[str]] = frozenset(TASK_MAPPING.keys())

# narutomobile 36 个 entry 中我们用得到的
SUPPORTED_ENTRIES: Final[frozenset[str]] = frozenset(set(TASK_MAPPING.values()))


def resolve_entry(task_id: str) -> str:
    """把我们 task_id 翻译成 narutomobile entry 名。

    Fallback: 如果 task_id 不在映射里,**原样返回** — 假定 caller 传的本来就是 entry。
    这样我们将来加新 task 时不用每次改这个文件。

    Args:
        task_id: 我们的 task_id(``mail`` / ``recruit`` / ``daily_signin`` ...)
                 或 narutomobile entry 名(``headhunt`` / ``activity`` ...)。

    Returns:
        narutomobile entry 名。

    Examples:
        >>> resolve_entry("mail")
        'mail'
        >>> resolve_entry("recruit")
        'headhunt'
        >>> resolve_entry("activity")  # 直接传 entry 也 OK
        'activity'
    """
    return TASK_MAPPING.get(task_id, task_id)


def resolve_task_id(entry: str) -> str | None:
    """narutomobile entry → 我们 task_id(找不到返 None)。"""
    return REVERSE_MAPPING.get(entry)


def list_supported_tasks() -> list[str]:
    """返回支持的 task_id 列表(按插入顺序)。"""
    return list(TASK_MAPPING.keys())


def list_supported_entries() -> list[str]:
    """返回用得到的 narutomobile entry 列表(去重,按首次出现顺序)。"""
    seen: set[str] = set()
    out: list[str] = []
    for entry in TASK_MAPPING.values():
        if entry not in seen:
            seen.add(entry)
            out.append(entry)
    return out


def is_supported(task_id: str) -> bool:
    """task_id 是否在我们的映射里。"""
    return task_id in SUPPORTED_TASK_IDS


def is_known_entry(entry: str) -> bool:
    """是否是用得到的 narutomobile entry。"""
    return entry in SUPPORTED_ENTRIES
