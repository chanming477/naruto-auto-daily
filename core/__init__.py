"""core package · 核心引擎层 + 日志上下文 (V3 2026-07-19)。

模块清单 (V3 OPT-1 后):
    config_manager    — ConfigManager (Pydantic 配置)
    logger            — configure / shutdown
    app_paths         — get_resource_root / get_user_data_dir
    run_context       — RunContext (Phase 4 日志上下文)
    task_result       — TaskStatus / TaskResult (从 base_task.py 拆出)

V3 (2026-07-19 OPT-1) 删:
    - base_task.py        (BaseTask 0 实现, ExecutionContext 仅 --capture-test 引用 → 也删)
    - window_manager.py   (--capture-test 已删)
    - screenshot_manager.py (--capture-test 已删)
    - state_machine.py    (--capture-test 链路已删)
    旧自研调度框架全删,统一走 MaaFramework pipeline。
"""

__all__ = [
    "app_paths",
    "config_manager",
    "logger",
    "run_context",
    "task_result",
]

__version__ = "0.7.0"
