"""agent.utils.logger — Agent 模式日志（移植 narutomobile 轮转/压缩/UTF-8 方案）。

**双 logger 模式**:
    - ``maafw_bridge`` 模块用 loguru 全局 logger,日志写到 ``logs/`` (项目自带 logger)
    - ``agent`` 子进程用独立 logger,日志写到 ``debug/custom/`` (独立于 MFAAvalonia)

**生产级特性** (2026-07-20 升级):
    - 每日 00:00 轮转新文件
    - 旧文件 zip 压缩 (节省磁盘)
    - 保留 2 周
    - enqueue=True 线程安全 (MaFramework 在 worker thread 调 logger)
    - UTF-8 编码 (Windows charmap 兼容)
    - 控制台日志级别可动态调整
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger as _loguru

# 日志目录: workdir/debug/custom/ (扁平化后 workdir=项目根)
DEFAULT_LOG_DIR = Path("debug/custom")
DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)

_agent_log = None


def _format_level(record):
    """自定义日志级别简称: INFO->info, ERROR->err, WARNING->warn。"""
    level_map = {
        "INFO": "info",
        "ERROR": "err",
        "WARNING": "warn",
        "DEBUG": "debug",
        "CRITICAL": "critical",
        "SUCCESS": "success",
        "TRACE": "trace",
    }
    record["extra"]["level_short"] = level_map.get(
        record["level"].name, record["level"].name.lower()
    )
    return True


def setup_agent_logger(
    log_dir: Path | None = None,
    console_level: str = "INFO",
) -> _loguru:
    """配置 Agent 模式 logger, 返回 loguru 根 logger (全局唯一配置)。

    Args:
        log_dir: 日志目录, 默认 ``debug/custom/``
        console_level: 控制台日志级别

    调用方: ``agent/main.py`` 启动时调一次。
    """
    global _agent_log
    if _agent_log is not None:
        return _agent_log

    if log_dir is None:
        log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # 清掉所有现有 handler,避免重复输出
    _loguru.remove()

    # 1. 控制台: 彩色 + 简短格式
    _loguru.add(
        sys.stdout,
        format="<level>{extra[level_short]}</level>: <level>{message}</level>",
        colorize=True,
        level=console_level,
        filter=_format_level,
    )

    # 2. 文件: 完整格式 + 每日轮转 + zip 压缩 + 保留 2 周 + 线程安全
    _loguru.add(
        log_dir / "{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="2 weeks",
        compression="zip",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module}:{line} | {message}",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    _agent_log = _loguru
    return _loguru


def change_console_level(level: str = "DEBUG") -> None:
    """动态调整控制台日志级别 (重新初始化 logger)。"""
    global _agent_log
    _agent_log = None  # 强制重新 setup
    log = setup_agent_logger(console_level=level)
    log.info(f"控制台日志等级已更改为: {level}")


def get_agent_logger() -> _loguru:
    """获取已配置的 logger。

    如果 ``setup_agent_logger`` 没调过 (在 main 之前 import agent.custom 等模块),
    返回一个临时 fallback logger 写 stdout (不写文件, 避免 main 启动前就创建文件)。
    """
    if _agent_log is not None:
        return _agent_log
    # Fallback: 简单 stdout logger (文件 logger 等 main 启动后再开)
    _loguru.remove()
    _loguru.add(
        sys.stdout,
        level="DEBUG",
        format="[{time:HH:mm:ss.SSS}][{level}][{name}] {message}",
    )
    return _loguru
