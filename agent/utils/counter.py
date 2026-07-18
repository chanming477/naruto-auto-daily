"""agent.utils.counter — 任务执行计数 (持久化到 counter.json)。

用途: 记录每个 task 今天/本周/本月执行了几次,IsCounterOverflow CustomRecognition 用来
判断 "今天已经跑过 X 次了,跳过"。

**状态 (2026-07-15)**: 占位,merged.json 暂不引用,实际不需要计数逻辑。
等用户说要按天/周限制任务执行次数时再实现。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

COUNTER_FILE = Path("debug/custom/counter.json")


def load_counter() -> dict[str, dict[str, int]]:
    """从 counter.json 读计数器。

    Returns:
        ``{task_id: {date_str: count}}`` 字典,日期格式 YYYY-MM-DD。
        文件不存在返 ``{}``。
    """
    if not COUNTER_FILE.exists():
        return {}
    try:
        return json.loads(COUNTER_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_counter(counter: dict[str, dict[str, int]]) -> None:
    """写计数器到 counter.json。

    Args:
        counter: ``{task_id: {date_str: count}}`` 字典。
    """
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(
        json.dumps(counter, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def increment(task_id: str) -> int:
    """给指定 task_id 今天计数 +1,返回新值。

    Args:
        task_id: 任务名 (e.g. "mail" / "headhunt" / "activity")。

    Returns:
        今天的执行次数(递增后)。
    """
    counter = load_counter()
    today = datetime.now().strftime("%Y-%m-%d")
    task_dict = counter.setdefault(task_id, {})
    task_dict[today] = task_dict.get(today, 0) + 1
    save_counter(counter)
    return task_dict[today]


def get_count(task_id: str, date: str | None = None) -> int:
    """查 task_id 在指定日期的执行次数(默认今天)。

    Args:
        task_id: 任务名。
        date: 日期字符串 YYYY-MM-DD,None 表示今天。

    Returns:
        该 task 在该日的执行次数,无记录返 0。
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    counter = load_counter()
    return counter.get(task_id, {}).get(date, 0)
