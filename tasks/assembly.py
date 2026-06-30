"""tasks.assembly — 共享运行时装配工厂函数(Phase 5 优化)。

提取 main.py 中 5 个函数各自重复的 ADBClient + Recognizer + GameSM + CommonActions
装配逻辑,统一为两个工厂函数。核心模块零变更。

用法:
    from tasks.assembly import assemble_lightweight, assemble_full

    # Phase 2/4 demo(不需要 ExecutionContext)
    cfg, adb, recognizer, game_sm, common = assemble_lightweight(project_root)

    # Phase 3/6 任务系统(需要 ExecutionContext + TaskEngine)
    cfg, ctx, common, engine, game_sm = assemble_full(project_root)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from core.config_manager import ConfigManager
from core.logger import configure as configure_logger
from device.adb_client import ADBClient, ADBError, ADBUnavailableError
from device.types import ActionResult
from recognition.template_matcher import TemplateMatcher
from recognizer.page_recognizer import PageRecognizer
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine
from tasks.common_actions import CommonActions

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from core.base_task import ExecutionContext
    from tasks.task_engine import TaskEngine

__all__ = [
    "assemble_lightweight",
    "assemble_full",
    "_install_mock_adb_defaults",
]


# ============================================================
# Internal helpers
# ============================================================


def _install_mock_adb_defaults(mock: "ADBClient | MagicMock") -> None:
    """给 MagicMock(spec=ADBClient) 装默认返回值,让 CommonActions 不抛错。

    移自 main.py — 统一 mock 默认值,main.py 里不再重复定义。
    """
    # 每次 mock 调用都返回新对象避免污染测试
    def _ok_screenshot(*_args, **_kwargs):
        return ActionResult(
            success=True, message="mock screenshot", next_state=None,
            payload=np.zeros((720, 1280, 3), dtype=np.uint8),
        )

    def _ok_action(*_args, **_kwargs):
        return ActionResult(success=True, message="mock action", next_state=None)

    mock.screenshot.side_effect = _ok_screenshot
    mock.tap.side_effect = _ok_action
    mock.swipe.side_effect = _ok_action
    mock.keyevent.side_effect = _ok_action
    mock.connect.return_value = ActionResult(True, "mock connect", None)


def _create_adb_client_or_mock(
    cfg: ConfigManager,
    *,
    use_real_adb: bool,
) -> "ADBClient | MagicMock":
    """尝试创建 + 连接 ADBClient;失败回退 MagicMock。

    Args:
        cfg: 已初始化的 ConfigManager。
        use_real_adb: True 时尝试真 ADB;失败(或 False)回退 MagicMock。

    Returns:
        ADBClient(已连接)或 MagicMock(spec=ADBClient)。
    """
    from unittest.mock import MagicMock

    if not use_real_adb:
        logger.info("use_real_adb=False; using MagicMock for ADBClient")
        mock = MagicMock(spec=ADBClient)
        _install_mock_adb_defaults(mock)
        return mock

    try:
        client = ADBClient(cfg)
        logger.info("ADBClient created: path={}, serial={}",
                    client.adb_path, client.serial or "<auto>")
        connect_result = client.connect()
        if not connect_result.success:
            logger.warning("ADB connect failed: {} — fallback to MagicMock",
                          connect_result.message)
            mock = MagicMock(spec=ADBClient)
            _install_mock_adb_defaults(mock)
            return mock
        return client
    except ADBUnavailableError as exc:
        logger.warning("ADB unavailable: {} — fallback to MagicMock", exc)
        mock = MagicMock(spec=ADBClient)
        _install_mock_adb_defaults(mock)
        return mock
    except ADBError as exc:
        logger.error("ADB error during init: {} — fallback to MagicMock", exc)
        mock = MagicMock(spec=ADBClient)
        _install_mock_adb_defaults(mock)
        return mock


def _create_recognizer_and_sm(
    cfg: ConfigManager,
    project_root: Path,
) -> tuple[PageRecognizer, GameStateMachine]:
    """创建 TemplateMatcher + PageRecognizer + GameStateMachine。

    Args:
        cfg: 已初始化的 ConfigManager。
        project_root: 项目根目录。

    Returns:
        (recognizer, game_sm) 二元组。
    """
    matcher = TemplateMatcher(cfg)
    templates_root = project_root / cfg.app.game_state.templates_dir
    recognizer = PageRecognizer(templates_root, matcher=matcher)
    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    return recognizer, game_sm


# ============================================================
# Public factory functions
# ============================================================


def assemble_lightweight(
    project_root: Path,
    *,
    use_real_adb: bool = False,
    console_level: str | None = None,
) -> tuple[ConfigManager, "ADBClient | MagicMock", PageRecognizer, GameStateMachine, CommonActions]:
    """轻量装配(Phase 2/4 demo 共用)。

    装配: ConfigManager + ADBClient(or MagicMock) + Recognizer + GameSM + CommonActions。
    调用方如需 RetryManager / RecoveryManager 需自行在返回后添加。

    Args:
        project_root: 项目根目录。
        use_real_adb: True 尝试真 ADB;失败 fallback MagicMock。
        console_level: 控制台日志级别;None 用配置文件默认。

    Returns:
        (cfg, adb_client, recognizer, game_sm, common_actions) 五元组。
    """
    cfg = ConfigManager(project_root, auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, project_root)
    logger.info("assemble_lightweight: logger initialized (level={})",
                cfg.app.logger.console_level)

    adb_client = _create_adb_client_or_mock(cfg, use_real_adb=use_real_adb)
    recognizer, game_sm = _create_recognizer_and_sm(cfg, project_root)
    common = CommonActions(
        adb_client=adb_client,
        recognizer=recognizer,
        game_sm=game_sm,
        config=cfg,
        project_root=project_root,
    )
    return cfg, adb_client, recognizer, game_sm, common


def assemble_full(
    project_root: Path,
    *,
    use_real_adb: bool = False,
    console_level: str | None = None,
) -> tuple[ConfigManager, "ExecutionContext", CommonActions, "TaskEngine", GameStateMachine]:
    """完整装配(Phase 3/6 任务系统共用)。

    装配: ConfigManager + ADBClient(or MagicMock) + Recognizer + GameSM +
          CommonActions + ExecutionContext + TaskEngine。

    Args:
        project_root: 项目根目录。
        use_real_adb: True 尝试真 ADB;失败 fallback MagicMock。
        console_level: 控制台日志级别;None 用配置文件默认。

    Returns:
        (cfg, ctx, common_actions, engine, game_sm) 五元组。
    """
    from unittest.mock import MagicMock

    from core.base_task import ExecutionContext
    from core.state_machine import build_default_state_machine
    from tasks.task_engine import TaskEngine

    cfg, adb_client, recognizer, game_sm, common = assemble_lightweight(
        project_root,
        use_real_adb=use_real_adb,
        console_level=console_level,
    )

    ctx = ExecutionContext(
        config=cfg,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=True),
    )

    engine = TaskEngine(ctx, common_actions=common)
    return cfg, ctx, common, engine, game_sm
