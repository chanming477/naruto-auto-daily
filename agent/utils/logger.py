"""agent.utils.logger — 写 debug/custom/YYYY-MM-DD.log,跟 MFAAvalonia 日志分开。

**双 logger 模式**:
    - ``maafw_bridge`` 模块用 loguru 全局 logger,日志写到 ``logs/`` (项目自带 logger)
    - ``agent`` 子进程用独立 logger,日志写到 ``debug/custom/`` (独立于 MFAAvalonia)

这样双击 exe 启动时,Python 端日志跟 C# 日志分开,排查问题更清晰。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger as _loguru

# 日志目录: workdir/debug/custom/ (workdir=frontend/MFAAvalonia/)
DEBUG_DIR = Path("debug/custom")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


_agent_log = None


def setup_agent_logger() -> "_loguru":
    """配置 Agent 模式 logger,返回 loguru 根 logger (全局唯一配置)。

    调用方: ``agent/main.py`` 启动时调一次。
    """
    global _agent_log
    if _agent_log is not None:
        return _agent_log

    # 清掉所有现有 handler,避免重复输出
    _loguru.remove()

    # 1. stdout — INFO 级别,给 user 看
    _loguru.add(
        sys.stdout,
        level="INFO",
        format="[{time:HH:mm:ss.SSS}][{level}][{name}] {message}",
    )

    # 2. 文件 — DEBUG 级别,保留细节给开发看
    _loguru.add(
        str(DEBUG_DIR / "{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    _agent_log = _loguru
    return _loguru


def get_agent_logger() -> "_loguru":
    """获取已配置的 logger。

    如果 ``setup_agent_logger`` 没调过(在 main 之前 import agent.custom 等模块),
    返一个临时 fallback logger 写 stdout,不写文件。
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
