"""core package · 核心引擎层 + 日志上下文 (V2 2026-07-18)。

模块清单 (P2 后剩):
    base_task         — BaseTask / TaskResult / TaskStatus / ExecutionContext
    config_manager    — ConfigManager (Pydantic 配置)
    logger            — configure / shutdown
    window_manager    — WindowManager (P2-6 决策 B: --capture-test 仍用)
    screenshot_manager — ScreenshotManager (P2-6 决策 B: --capture-test 仍用)
    state_machine     — 状态机 (P2-6 决策 B: --capture-test 链路需要)
    run_context       — RunContext (Phase 4)

P2 删 (2026-07-18):
    - scheduler  (--smoke-test 命令已删, 0 prod 引用, RunReport 已内联到 task_engine_maafw)
"""

__all__ = [
    "config_manager",
    "logger",
    "window_manager",
    "screenshot_manager",
    "state_machine",
    "base_task",
    "run_context",
]

__version__ = "0.7.0"
