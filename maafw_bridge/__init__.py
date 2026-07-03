"""maafw_bridge — MaaFramework 桥接层。

本模块用 MaaFramework + narutomobile 模板替代自研识别/导航引擎。

模块构成:
    - resource.py       load_narutomobile_resource() — 加载 narutomobile 模板 + pipeline
    - task_mapping.py   我们 task_id ↔ narutomobile entry 名称映射
    - event_sink.py     MaaEventSink(ContextEventSink) — 接管 maafw 回调 → TaskResult
    - tasker.py         MaaFramework Tasker 单例(连接 ADB + 加载 resource + 启动)

不在本模块做的事:
    - GUI 显示(TaskEngine / main_window 负责)
    - 任务元数据注册(沿用现有 BaseTask + task_registry.yaml)
    - 调度决策(由 core.scheduler.Scheduler 负责)
"""

from __future__ import annotations

from .event_sink import MaaEventSink
from .resource import load_narutomobile_resource, verify_resource_path
from .task_mapping import (
    REVERSE_MAPPING,
    TASK_MAPPING,
    is_known_entry,
    is_supported,
    list_supported_entries,
    list_supported_tasks,
    resolve_entry,
    resolve_task_id,
)
from .tasker import MaaTaskerSingleton, get_tasker, reset_tasker

__all__ = [
    # resource
    "load_narutomobile_resource",
    "verify_resource_path",
    # mapping
    "TASK_MAPPING",
    "REVERSE_MAPPING",
    "resolve_entry",
    "resolve_task_id",
    "list_supported_tasks",
    "list_supported_entries",
    "is_supported",
    "is_known_entry",
    # tasker
    "MaaTaskerSingleton",
    "get_tasker",
    "reset_tasker",
    # sink
    "MaaEventSink",
]
