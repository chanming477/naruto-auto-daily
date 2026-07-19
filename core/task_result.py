"""core.task_result — TaskStatus / TaskResult 数据类 (2026-07-19 OPT-1 拆分)。

V2 (2026-07-19): 从 core/base_task.py 拆出。原 base_task.py 整体被 OPT-1 删
(ExecutionContext / BaseTask / WindowManager 依赖全死),只留 TaskResult/TaskStatus
这两个真有 consumer 的 dataclass。

Consumers:
    - maafw_bridge.event_sink (把 maafw 回调包装成 TaskResult)
    - tasks.task_engine_maafw (调度链产出 TaskResult,统计进 RunReport)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = ["TaskStatus", "TaskResult"]


class TaskStatus:
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    RETRY = "RETRY"
    SKIP = "SKIP"
    #: 2026-07-02: task 主流程失败但选择"接受失败,返 SUCCESS 以避免阻塞调度"
    #: (mail / liveness / recruit / activity / daily_signin / weekly_signin 等
    #: best-effort 任务)。
    BEST_EFFORT = "BEST_EFFORT"


@dataclass
class TaskResult:
    task_id: str
    status: str = TaskStatus.FAIL
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_sec: float = 0.0
    attempts: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in (TaskStatus.SUCCESS, TaskStatus.BEST_EFFORT)

    @property
    def is_failure(self) -> bool:
        return self.status in (TaskStatus.FAIL, TaskStatus.RETRY)

    @property
    def is_skip(self) -> bool:
        return self.status == TaskStatus.SKIP

    @property
    def is_best_effort(self) -> bool:
        return self.status == TaskStatus.BEST_EFFORT

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_sec": round(self.duration_sec, 3),
            "attempts": self.attempts,
            "extra": self.extra,
        }
