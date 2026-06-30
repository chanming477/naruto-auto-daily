"""core.logger — 全局日志系统（Loguru）。

设计要点：
- 单一全局 logger 实例（idempotent setup，多次调用安全）。
- 三个 sink：
    1. 控制台（彩色，按 console_level 过滤）
    2. 每日滚动文件（全等级，按 file_level 过滤）
    3. 错误专用文件（仅 ERROR+）
- structured context 通过 `logger.bind(...)` 注入；常用字段：
      task_id, run_id, page, elapsed
- Phase 1 不引入异步 / 远程 sink，避免增加复杂度。

公开 API：
    configure(config: LoggerConfig, project_root: Path) -> None
    get_logger(name: str | None = None) -> loguru.Logger
    shutdown() -> None
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger as _loguru_logger

from core.config_manager import LoggerConfig

__all__ = ["configure", "get_logger", "shutdown"]

_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
)


_configured = False


def configure(config: LoggerConfig, project_root: Path) -> None:
    """初始化全局 logger。多次调用安全（会先 remove 旧 sink）。"""
    global _configured

    # 始终先清空旧 sink，避免重复调用导致重复输出。
    _loguru_logger.remove()

    log_dir = project_root / config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1) 控制台 sink —— 始终存在；级别由 console_level 控制。
    _loguru_logger.add(
        sys.stderr,
        level=config.console_level,
        format=_DEFAULT_FORMAT,
        colorize=True,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )

    # 2) 每日滚动文件 sink —— 全等级；按 rotation 触发，按 retention 清理。
    rotation = f"{int(config.rotation_mb)} MB"
    retention = f"{int(config.retention_days)} days"
    _loguru_logger.add(
        log_dir / "{time:YYYY-MM-DD}.log",
        level=config.file_level,
        format=_FILE_FORMAT,
        rotation=rotation,
        retention=retention,
        compression="zip" if config.compression else None,
        enqueue=False,
        encoding="utf-8",
        backtrace=True,
        diagnose=False,
    )

    # 3) 错误专用文件 sink —— 仅 ERROR+。
    _loguru_logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format=_FILE_FORMAT,
        rotation=rotation,
        retention=retention,
        compression="zip" if config.compression else None,
        enqueue=False,
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    _configured = True
    _loguru_logger.debug(
        "logger configured: console={}, file={}, retention={}d",
        config.console_level,
        config.file_level,
        config.retention_days,
    )


def get_logger(name: str | None = None) -> Any:
    """获取 logger 实例。

    Phase 1 使用全局 singleton。在 configure() 之前调用时不会向 stderr
    注入任何 sink，依赖 loguru 默认 WARNING+ 行为 —— 这样 ConfigManager
    等早期模块即使调 logger.debug 也不会污染控制台输出。
    """
    if name:
        return _loguru_logger.bind(component=name)
    return _loguru_logger


def shutdown() -> None:
    """关闭所有 sink（测试 / 退出时调用）。"""
    global _configured
    _loguru_logger.remove()
    _configured = False