"""core package · Phase 1 核心引擎层。

依赖方向（自上而下）：
    main
      └── core.scheduler
            └── core.base_task
                  ├── core.config_manager
                  ├── core.logger
                  ├── core.window_manager
                  ├── core.screenshot_manager
                  └── core.state_machine

Phase 1 仅交付以上 7 个模块 + main.py。
"""

__all__ = [
    "config_manager",
    "logger",
    "window_manager",
    "screenshot_manager",
    "state_machine",
    "base_task",
    "scheduler",
]

__version__ = "0.1.0"