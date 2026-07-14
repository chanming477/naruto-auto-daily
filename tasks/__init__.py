"""tasks package — 业务 task 模块。

包含 (2026-07-14 精简后):
    task_engine_maafw  — MaaTaskEngine (MaaFramework 5.10.4 + narutomobile 模板)

历史 (2026-07-14 删除):
    common_actions      — 旧自研 Navigator 通用动作,被 MaaFramework 取代
    task_engine         — 旧自研 Scheduler 包装,被 MaaTaskEngine 取代
    *_task.py (27 个)   — 旧自研 Task 子类,从未被 import
    weekly_signin_task  — 唯一活的,被 cmd_weekly_signin_real 引用,跟着迁移到 MaaFW 后删
    assembly / pure_actions / navigator / pipeline_runner — 旧 Navigator 框架, 27 个死 task 唯一用户
"""

__all__ = [
    "task_engine_maafw",
]
__version__ = "0.7.0"
