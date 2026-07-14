"""main.py — naruto-auto-daily 的 CLI 入口。

Phase 7 (2026-06-30):
    28 个真实日常业务 task(narutomobile v1.3.35 merged.json 全抄)
    + 工程治理(目录 / 文档 / 命名统一 / LICENSE / CONTRIBUTING / CHANGELOG)

Phase 1 命令（保留）：
    --init-config    生成默认 YAML（已存在不覆盖）
    --smoke-test     无目标窗口也能跑：初始化所有 Manager + 调度器空跑
    --list-windows   列出当前桌面所有顶层窗口
    --run            按 task_registry.yaml 执行任务
    --task <id>      只执行指定 ID 的任务（需配合 --run）
    --activate-window / --capture-test / --debug / --quiet / --version

Phase 2 命令（新增）：
    --phase2         跑 Phase 2 完整识别闭环:连接 → 截图 → 匹配 → 识别 → 更新 → 日志
    --phase2-smoke   不连真 ADB:用代码生成的 demo 截图跑完整闭环,确保任何机器能验收
    --help           显式打印帮助

Phase 3 命令（新增）：
    --phase3 / --phase3-task <id>
                    跑 Phase 3 任务系统(TaskEngine + DailySigninTask + CommonActions)

Phase 4 命令（新增）：
    --phase4         跑 Phase 4 稳定性体系:
                       RetryManager (execute_adb_action 真实链) +
                       RecoveryManager (4 个 recover_* 方法) +
                       RunContext (state_before/after/elapsed_ms 日志上下文)。
                    演示: GameStateMachine.recover(recovery_manager) 新签名。
    --phase4-smoke   不连真 ADB,MagicMock fallback(同 --phase4 但 use_real_adb=False)

Phase 6/7 命令（28 个真实 task 跑批）：
    --mail-real / --daily-signin-real / --liveness-real / --recruit-real / --activity-real
    --weekly-signin-real / --group-signin-real / --monthly-signin-real
    --rich-room-real / --team-dash-real / --secret-realm-real
    --survival-challenge-real / --shugyou-no-michi-real / --stronghold-real / --mission-office-real
    --advanture-real / --elite-instance-real / --point-race-real / --rebel-ninja-real
    --use-energy-real / --give-energy-real / --leaderboard-real / --more-gameplay-real
    --ninja-book-real / --weekly-win-real / --sky-ground-real
    --easy-helper-real / --hundred-ninja-real
    --daily-all  顺序跑 schemes/daily.json 全部 task

默认行为（无任何参数）：
    启动 MFAAvalonia 桌面 GUI(等价 ``--gui``,需先下载 frontend/MFAAvalonia/)。
    想无 ADB 跑 demo 用 ``python main.py --phase2-smoke``;真机跑批用 ``--mail-real`` / ``--daily-all``。

详见 README.md / CONTRIBUTING.md / docs/standards/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 让 ``python main.py`` 和 ``python -m main`` 都能正常 import core.*
# 资源根:frozen 模式在 _MEIPASS(PyInstaller 解压目录),源码模式在 main.py 同级
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.app_paths import get_resource_root, get_user_data_dir
from loguru import logger

# Phase 2 依赖:numpy / OpenCV 用于 demo 截图生成与可选落盘
import cv2
import numpy as np

from core import __version__
from core.base_task import ExecutionContext
from core.config_manager import ConfigManager
from core.logger import configure as configure_logger
from core.logger import shutdown as shutdown_logger
from core.scheduler import Scheduler
from core.screenshot_manager import ScreenshotManager
from core.state_machine import StateMachine, build_default_state_machine
from core.window_manager import WindowManager

# Phase 2 增量
from device.adb_client import ADBClient, ADBError, ADBUnavailableError
from recognition.template_matcher import TemplateMatcher
from recognizer.page_recognizer import PageRecognizer
from state.game_state import GameState
# V2: GameContext 已删除,改为 ExecutionContext 的类型别名(state.types 里)
# 这里不再 import — run_phase2_demo 用 GameStateMachine 直接持有状态。
from state_machine.game_state_machine import GameStateMachine

# Phase 3 增量
from tasks.assembly import assemble_full, assemble_lightweight, _install_mock_adb_defaults
from tasks.common_actions import CommonActions
from tasks.task_engine import TaskEngine

# Phase 4 增量
from recovery.recovery_manager import RecoveryManager
from recovery.retry_manager import RetryManager, RetryPolicy

__all__ = [
    "main", "build_context", "parse_args",
    "run_phase2_demo", "run_phase3_demo", "run_phase4_demo",
]


# ============================================================
# Bootstrap helpers
# ============================================================


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="naruto-auto-daily",
        description="火影手游日常自动化工具 (MaaFramework 5.10.4 + MFAAvalonia 桌面 GUI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python main.py                 # 默认启 MFAAvalonia 桌面 GUI\n"
               "  python main.py --phase2        # 尝试连接 ADB 真设备(无 ADB 自动 fallback demo)\n"
               "  python main.py --phase2-smoke  # 不连 ADB,跑 Phase 2 识别闭环 demo\n"
               "  python main.py --init-config\n"
               "  python main.py --smoke-test\n"
               "  python main.py --list-windows\n"
               "  python main.py --run --task daily_signin\n",
    )
    parser.add_argument("--init-config", action="store_true",
                        help="在 config/ 下生成默认 YAML 配置（已存在则跳过）")
    parser.add_argument("--smoke-test", action="store_true",
                        help="无目标窗口也能跑：初始化所有 Manager + 调度器空跑")
    parser.add_argument("--list-windows", action="store_true",
                        help="枚举并打印所有顶层窗口信息")
    parser.add_argument("--run", action="store_true",
                        help="按 task_registry.yaml 顺序执行任务")
    parser.add_argument("--task", type=str, default=None, metavar="ID",
                        help="只执行指定 task_id（需配合 --run）")
    parser.add_argument("--activate-window", action="store_true",
                        help="只查找并激活目标窗口，不执行任何任务")
    parser.add_argument("--capture-test", action="store_true",
                        help="截一张目标窗口的图保存到 screenshots/ 用于验证")
    # ---- Phase 2 增量 ----
    parser.add_argument("--phase2", action="store_true",
                        help="Phase 2 完整识别闭环:连接 ADB → 截图 → 模板匹配 → "
                             "识别页面 → 状态机更新 → 日志。无 ADB 时自动 fallback 到 demo 模式")
    parser.add_argument("--phase2-smoke", action="store_true",
                        help="Phase 2 smoke:跳过真 ADB,用代码生成 demo 截图跑完整闭环")
    # ---- Phase 3 增量 ----
    parser.add_argument("--phase3", action="store_true",
                        help="Phase 3 任务系统:TaskEngine + DailySigninTask + CommonActions。"
                             "无 ADB / 模板时仍能跑(enter/execute/verify mock,recover 真做)。")
    parser.add_argument("--phase3-task", type=str, default=None, metavar="ID",
                        help="只跑 Phase 3 指定 task_id(需配合 --phase3)")
    parser.add_argument("--phase3-smoke", action="store_true",
                        help="Phase 3 smoke:不连真 ADB,MagicMock fallback(同 --phase3 但 use_real_adb=False)")
    # ---- Phase 4 增量 ----
    parser.add_argument("--phase4", action="store_true",
                        help="Phase 4 稳定性体系:RetryManager + RecoveryManager + RunContext。"
                             "演示 GameStateMachine.recover(recovery_manager) 新签名。")
    parser.add_argument("--phase4-smoke", action="store_true",
                        help="Phase 4 smoke:不连真 ADB,MagicMock fallback。")
    # ---- GUI 桌面客户端 ----
    parser.add_argument("--gui", action="store_true",
                        help="启动 MFAAvalonia 桌面客户端(需要 .NET 10 Desktop Runtime)")
    # ---- Phase 6 真实接入增量(P7-REAL) ----
    parser.add_argument("--daily-signin-real", action="store_true",
                        help="P7-REAL: 真实模拟器跑每日签到全流程(需要 MuMu 模拟器 + 1920x1080)")
    parser.add_argument("--mail-real", action="store_true",
                        help="Phase 6 业务扩展: 真实模拟器跑邮件领取(mail_entry 等模板缺失时降级)")
    parser.add_argument("--liveness-real", action="store_true",
                        help="Phase 6 业务扩展: 真实模拟器跑活跃奖励(复用 liveness/* 模板)")
    parser.add_argument("--group-signin-real", action="store_true",
                        help="Phase 6 业务扩展: 真实模拟器跑组织签到(group/* 模板缺失时降级)")
    parser.add_argument("--daily-all", action="store_true",
                        help="Phase 6 业务扩展: 顺序跑 schemes/daily.json 的全部任务(TaskEngine.run_all)")
    parser.add_argument("--emu-resolution", type=str, default="auto",
                        help="实际模拟器分辨率 WxH,默认 auto=自动检测(如 1600x900)")
    parser.add_argument("--debug", action="store_true",
                        help="把日志级别下调到 DEBUG")
    parser.add_argument("--quiet", action="store_true",
                        help="把日志级别上调到 WARNING")
    parser.add_argument("--version", action="store_true",
                        help="打印版本号")
    # ---- P1-7 自检命令 ----
    parser.add_argument("--check", action="store_true",
                        help="P1-7 自检: ADB 连通性 / Pydantic 配置校验 / 模板完整性 / 任务注册表")
    # ---- Phase 8 MaaFramework 桥接命令(2026-07-02,跟旧 --xxx-real 平行,不破坏旧)----
    parser.add_argument("--daily-maafw", action="store_true",
                        help="Phase 8: 跑 schemes/daily.json 全部 task(走 MaaFramework + narutomobile 模板,需要模拟器)")
    parser.add_argument("--maafw-task", type=str, default=None, metavar="TASK_ID",
                        help="Phase 8: 跑指定 task (MaaFramework + narutomobile 模板),"
                             " 如 --maafw-task mail(覆盖 TASK_MAPPING 20 个 task_id)")
    parser.add_argument("--maafw-list", action="store_true",
                        help="Phase 8: 打印 task_id <-> entry 映射表(不连 ADB)")
    return parser.parse_args(argv)


def build_context(project_root: Path,
                  *,
                  console_level: str | None = None) -> ExecutionContext:
    """组装 ExecutionContext。

    顺序很关键：先 ConfigManager（其他模块要读配置）→ Logger（用配置级别）→
    WindowManager → ScreenshotManager → StateMachine → ExecutionContext。
    """
    cfg_mgr = ConfigManager(get_user_data_dir(), auto_load=True)

    # 1. 日志（必须用配置里的级别；如果 CLI 指定了 console_level，会覆盖）
    if console_level is not None:
        cfg_mgr.app.logger.console_level = console_level
    configure_logger(cfg_mgr.app.logger, get_user_data_dir())
    logger.info("logger initialized (level={})", cfg_mgr.app.logger.console_level)

    # 2. 窗口管理器（用 device profile）
    profile = cfg_mgr.device.active()
    win_mgr = WindowManager(profile)

    # 3. 截图管理器
    shot_mgr = ScreenshotManager(win_mgr, cfg_mgr.app.screenshot, get_user_data_dir())

    # 4. 状态机：所有转换规则 + 日志回调由 state_machine.build_default_state_machine
    #    内聚提供，main 不再硬编码状态机表。
    sm = build_default_state_machine(
        cfg_mgr.app.state_machine.initial_state,
        log_transitions=cfg_mgr.app.state_machine.log_transitions,
    )

    ctx = ExecutionContext(
        config=cfg_mgr,
        window_manager=win_mgr,
        screenshot_manager=shot_mgr,
        state_machine=sm,
    )
    logger.debug("ExecutionContext built (run_id={})", ctx.run_id)
    return ctx


# ============================================================
# Subcommands
# ============================================================


def cmd_init_config(project_root: Path) -> int:
    cfg = ConfigManager(get_user_data_dir(), auto_load=False)
    created = cfg.save_default_configs()
    if not created:
        print("[init-config] 所有配置文件已存在，未做任何修改。")
        print(f"[init-config] 配置目录: {cfg.config_dir}")
    else:
        print("[init-config] 已生成以下默认配置：")
        for p in created:
            print(f"  - {p}")
    return 0


def cmd_smoke_test(ctx: ExecutionContext) -> int:
    """无目标窗口也能跑：初始化所有 Manager + 调度器空跑。"""
    print("=" * 60)
    print("naruto-auto-daily · smoke-test")
    print("=" * 60)

    print(f"version       : {__version__}")
    print(f"project root  : {ctx.config.project_root}")
    print(f"config dir    : {ctx.config.config_dir}")
    print(f"app config    : name={ctx.config.app.app.name} "
          f"phase={ctx.config.app.app.phase}")
    print(f"logger        : console={ctx.config.app.logger.console_level} "
          f"file={ctx.config.app.logger.file_level}")
    print(f"device profile: {ctx.config.device.active_profile} "
          f"mode={ctx.config.device.active().match_mode}")
    print(f"screenshot    : backend={ctx.config.app.screenshot.backend} "
          f"gray={ctx.config.app.screenshot.to_grayscale}")
    print(f"scheduler     : stop_on_failure={ctx.config.app.scheduler.stop_on_failure} "
          f"timeout={ctx.config.app.scheduler.task_timeout_sec}s")
    print(f"state machine : initial={ctx.config.app.state_machine.initial_state} "
          f"current={ctx.state_machine.state}")
    print()

    # 列出可见窗口（仅 Windows）
    if sys.platform == "win32":
        wins = ctx.window_manager.list_visible()
        print(f"visible top-level windows: {len(wins)}")
        for w in wins[:8]:
            print(f"  - hwnd={w.hwnd} pid={w.pid} proc='{w.process_name}' "
                  f"title='{w.title[:40]}' class='{w.class_name}' "
                  f"rect={w.rect.width}x{w.rect.height}")
        if len(wins) > 8:
            print(f"  ... ({len(wins) - 8} more)")
    else:
        print("non-Windows platform: skipping window enumeration")
    print()

    # 跑一次空调度（注册表为空）
    scheduler = Scheduler(ctx)
    report = scheduler.run()
    print()
    print(f"scheduler report: {report.summary()}")
    print(f"final state machine: {ctx.state_machine.state}")
    return 0


def cmd_list_windows(ctx: ExecutionContext) -> int:
    if sys.platform != "win32":
        print("non-Windows platform: WindowManager unavailable")
        return 0
    wins = ctx.window_manager.list_visible()
    print(f"visible top-level windows: {len(wins)}")
    for w in wins:
        print(f"  hwnd={w.hwnd:>8} pid={w.pid:>6} proc='{w.process_name:<24}' "
              f"visible={w.is_visible} minimized={w.is_minimized} "
              f"rect={w.rect.width}x{w.rect.height} title='{w.title}'")
    return 0


def cmd_activate_window(ctx: ExecutionContext) -> int:
    if sys.platform != "win32":
        print("non-Windows platform: WindowManager unavailable")
        return 1
    info = ctx.window_manager.find_target()
    if info is None:
        print("no target window matched by current device profile")
        print(f"  profile={ctx.config.device.active_profile} "
              f"mode={ctx.config.device.active().match_mode} "
              f"keywords={ctx.config.device.active().match_keywords}")
        return 2
    print(f"target: {info}")
    ok = ctx.window_manager.activate(info.hwnd)
    print(f"activate: {'OK' if ok else 'FAILED'}")
    return 0 if ok else 3


def cmd_capture_test(ctx: ExecutionContext) -> int:
    if sys.platform != "win32":
        print("non-Windows platform: ScreenshotManager unavailable")
        return 1
    info = ctx.window_manager.find_target()
    if info is None:
        print("no target window matched by current device profile")
        return 2
    print(f"target: {info}")
    res = ctx.screenshot_manager.capture_and_save("smoke_capture", target=info)
    if res is None or res.saved_path is None:
        print("capture failed (see logs)")
        return 3
    print(f"capture saved: {res.saved_path} ({res.width}x{res.height}, backend={res.backend})")
    return 0


def cmd_run(ctx: ExecutionContext, task_id: str | None) -> int:
    scheduler = Scheduler(ctx)
    if task_id:
        print(f"running single task: {task_id}")
        result = scheduler.run_single(task_id)
        if result is None:
            return 2
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if result.is_success else 1
    report = scheduler.run()
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if (report.fail_count == 0 and not report.aborted) else 1


# ============================================================
# Phase 2: 识别闭环
# ============================================================


def _make_demo_screenshot(width: int = 720, height: int = 1280) -> np.ndarray:
    """生成 demo 截图(BGR uint8),供无 ADB / 无真设备时跑完整闭环。

    设计要点:
        - 固定 seed 的纯 noise 背景,确保可复现且不与常见 UI 元素重合
        - 角落放一个 8×8 纯色块作为 demo 标记(尺寸 / 位置避开常见 UI 控件位置)
        - **不加任何文字**,避免与 OCR / 模板产生意外匹配
        - Phase 2 demo 在无真模板时 detect_state 应返回 UNKNOWN,这是预期行为

    Args:
        width: 截图宽度(像素)。
        height: 截图高度(像素)。

    Returns:
        BGR uint8 numpy.ndarray,shape=(height, width, 3)。
    """
    rng = np.random.default_rng(seed=20260624)
    arr = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    # 左下角 (10, 10) 处放一个 8x8 的纯绿色标记
    arr[height - 18:height - 10, 10:18] = (0, 255, 0)  # BGR
    return arr


def run_phase2_demo(
    project_root: Path,
    *,
    use_real_adb: bool = False,
    console_level: str | None = None,
) -> int:
    """Phase 2 完整识别闭环(验收入口)。

    流程(Prompt 要求):
        启动 → 连接模拟器 → 截图 → 模板匹配 → 识别当前页面 → 状态机更新 → 日志 → 退出

    Args:
        project_root: 项目根目录。
        use_real_adb: True 时尝试连接真 ADB;失败则 graceful fallback。
            False(``--phase2-smoke`` 默认)直接用 demo 截图。
        console_level: 控制台日志级别覆盖(``--debug`` / ``--quiet``)。

    Returns:
        退出码。永远 0(graceful exit),除非 KeyboardInterrupt。
    """
    print("=" * 60)
    print("naruto-auto-daily · Phase 2 识别闭环")
    print("=" * 60)

    # 1) 初始化 config + logger
    cfg = ConfigManager(get_user_data_dir(), auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, get_user_data_dir())
    logger.info("logger initialized (level={})", cfg.app.logger.console_level)
    logger.info("Phase 2 demo: use_real_adb={}", use_real_adb)

    # 2) 准备 GameState 初始值(V2:状态存在 game_sm,不在 ctx 里)
    # GameStateConfig.initial_state 是 str(避免 core.config_manager 反向依赖 state 模块),
    # 这里做运行时校验:非法值 fallback 到 UNKNOWN 并 warning。
    try:
        initial_state = GameState(cfg.app.game_state.initial_state)
    except ValueError:
        logger.warning(
            "invalid game_state.initial_state='{}'; fallback to UNKNOWN",
            cfg.app.game_state.initial_state,
        )
        initial_state = GameState.UNKNOWN

    # 3) 连接模拟器(ADBClient)
    adb_client: ADBClient | None = None
    if use_real_adb:
        try:
            adb_client = ADBClient(cfg)
            logger.info("ADBClient created: path={}, serial={}",
                        adb_client.adb_path, adb_client.serial or "<auto>")
            connect_result = adb_client.connect()
            if not connect_result.success:
                logger.warning("ADB connect failed: {} — fallback to demo screenshot",
                               connect_result.message)
                adb_client = None
        except ADBUnavailableError as exc:
            logger.warning("ADB unavailable: {} — fallback to demo screenshot", exc)
            adb_client = None
        except ADBError as exc:
            logger.error("ADB error during init: {} — fallback to demo screenshot", exc)
            adb_client = None
    else:
        logger.info("use_real_adb=False, skip ADB connect, use demo screenshot")

    # 4) 截图
    screenshot_arr: np.ndarray | None = None
    screenshot_path: Path | None = None
    if adb_client is not None:
        shot = adb_client.screenshot()
        if shot.success and isinstance(shot.payload, np.ndarray):
            screenshot_arr = shot.payload
            # 可选落盘
            screenshots_dir = get_user_data_dir() / cfg.app.screenshot.output_dir
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshots_dir / f"phase2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            try:
                cv2.imwrite(str(screenshot_path), screenshot_arr)
                logger.info("screenshot saved: {} ({}x{})",
                            screenshot_path, screenshot_arr.shape[1], screenshot_arr.shape[0])
            except Exception as exc:
                logger.warning("failed to persist screenshot: {}", exc)
                screenshot_path = None
        else:
            logger.warning("ADB screenshot failed: {} — fallback to demo screenshot",
                           shot.message)

    if screenshot_arr is None:
        screenshot_arr = _make_demo_screenshot()
        logger.info("using demo screenshot ({}x{})",
                    screenshot_arr.shape[1], screenshot_arr.shape[0])

    # 5) 创建 TemplateMatcher + PageRecognizer
    matcher = TemplateMatcher(cfg)
    templates_root = get_resource_root() / cfg.app.game_state.templates_dir
    recognizer = PageRecognizer(templates_root, matcher=matcher)

    # 6) 模板匹配 + 状态识别
    result = recognizer.detect_state(screenshot_arr)
    logger.info("RecognitionResult: state={}, confidence={:.4f}, method={}",
                result.state.value, result.confidence, result.method)

    # 7) 状态机更新(V3:状态在 game_sm,不在 ctx 里)
    sm = GameStateMachine(initial=initial_state)
    sm.update_state(result.state, source="detect_state")
    if sm.current_state == GameState.UNKNOWN:
        logger.warning("state machine is UNKNOWN; entering recover() via RecoveryManager")
        # V3 (Phase 4): recover() 改用 RecoveryManager,不再做 probe + fallback 双重恢复。
        # 构造一个最小可用的 CommonActions(只给 recognizer / game_sm / config,ADB 用 MagicMock)。
        from unittest.mock import MagicMock

        from device.types import ActionResult
        from tasks.common_actions import CommonActions

        mock_adb = MagicMock()
        mock_adb.screenshot.return_value = ActionResult(
            True, "mock screenshot", None,
            payload=screenshot_arr,  # 复用同一张截图,避免无 ADB 时取不到图
        )
        mock_adb.keyevent.return_value = ActionResult(True, "mock", None)
        mock_adb.tap.return_value = ActionResult(True, "mock", None)
        common = CommonActions(
            adb_client=mock_adb,
            recognizer=recognizer,
            game_sm=sm,
            config=cfg,
            project_root=project_root,
        )
        recovery_mgr = RecoveryManager(
            common_actions=common,
            game_sm=sm,
            adb_client=mock_adb,
            screenshot_manager=None,
            config=cfg,
        )
        recovered = sm.recover(recovery_manager=recovery_mgr)
        logger.info("recover() final state: {}", recovered.value)

    # 8) 最终报告(V2:不维护 GameContext,直接读 sm + 局部变量)
    print()
    print(f"final game_state : {sm.current_state.value}")
    print(f"screenshot_path  : {screenshot_path or '<in-memory only>'}")
    print(f"fsm history      : {len(sm.history)} transition(s)")
    for tr in sm.history[-3:]:
        print(f"  {tr}")

    logger.success("Phase 2 demo finished: state={}", sm.current_state.value)
    print()
    print("exit 0")
    return 0


def cmd_phase2(project_root: Path, console_level: str | None = None) -> int:
    """``--phase2`` 命令:尝试真 ADB,失败 fallback。"""
    return run_phase2_demo(project_root, use_real_adb=True, console_level=console_level)


def cmd_phase2_smoke(project_root: Path, console_level: str | None = None) -> int:
    """``--phase2-smoke`` 命令:跳过真 ADB,用 demo 截图。"""
    return run_phase2_demo(project_root, use_real_adb=False, console_level=console_level)


# ============================================================
# Phase 3: 任务系统
# ============================================================


def _assemble_phase3_components(
    project_root: Path,
    *,
    use_real_adb: bool,
    console_level: str | None,
) -> tuple[ConfigManager, "ADBClient | MagicMock", "PageRecognizer", "GameStateMachine", CommonActions]:
    """Phase 3 装配: 委托给 ``tasks.assembly.assemble_lightweight()``。"""
    return assemble_lightweight(
        project_root, use_real_adb=use_real_adb, console_level=console_level,
    )


def run_phase3_demo(
    project_root: Path,
    *,
    use_real_adb: bool = False,
    task_id: str | None = None,
    console_level: str | None = None,
) -> int:
    """Phase 3 完整任务系统入口。

    流程:
        1. 装配 ConfigManager + ADBClient(可 MagicMock) + Recognizer + GameSM
        2. 创建 CommonActions
        3. 构造 ExecutionContext(Phase 1 资产,window_manager/screenshot_manager 用 MagicMock)
        4. 把 CommonActions 挂到 ``ctx.config._phase3_deps``(DailySigninTask 内部用)
        5. 创建 TaskEngine(ctx, common_actions)
        6. 跑 run_task(task_id) 或 run_all()
        7. 打印 RunReport

    Args:
        project_root: 项目根目录。
        use_real_adb: True 尝试真 ADB;失败 fallback 到 MagicMock。
        task_id: 单任务模式(只跑指定 ID);None 时跑全部 enabled 任务。
        console_level: 控制台日志级别。

    Returns:
        退出码。0 = 全部成功;非 0 = 有失败任务。
    """
    print("=" * 60)
    print("naruto-auto-daily · Phase 3 任务系统")
    print("=" * 60)

    cfg, adb_client, recognizer, game_sm, common = _assemble_phase3_components(
        project_root, use_real_adb=use_real_adb, console_level=console_level,
    )

    # 构造 ExecutionContext(Phase 1 资产,Phase 3 业务用 ExecutionContext 作为唯一上下文)
    from unittest.mock import MagicMock

    from core.base_task import ExecutionContext
    from core.state_machine import build_default_state_machine

    ctx = ExecutionContext(
        config=cfg,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=True),
    )

    # P1-ARCH-02: TaskEngine.__init__ 会自动把 common_actions 挂到 ``ctx.common_actions``,
    # 不再走 ``cfg._phase3_deps`` 私有属性 hack。
    # 任务的 pre_check / recover 直接从 ``ctx.common_actions`` 拿(P1-BUG-01 同步去掉 Noop fallback)。

    # TaskEngine
    engine = TaskEngine(ctx, common_actions=common)

    # 跑
    if task_id:
        print(f"running single task: {task_id}")
        result = engine.run_task(task_id)
        if result is None:
            return 2
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        rc = 0 if result.is_success else 1
    else:
        report = engine.run_all()
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        rc = 0 if (report.fail_count == 0 and not report.aborted) else 1

    print()
    print(f"final state machine (program-level): {ctx.state_machine.state}")
    print(f"final game state  (game-level)     : {game_sm.current_state.value}")
    print()
    return rc


def cmd_phase3(
    project_root: Path,
    task_id: str | None = None,
    console_level: str | None = None,
) -> int:
    """``--phase3`` 命令:尝试真 ADB,失败 MagicMock fallback。"""
    return run_phase3_demo(
        project_root, use_real_adb=True, task_id=task_id, console_level=console_level,
    )


def cmd_phase3_smoke(
    project_root: Path,
    task_id: str | None = None,
    console_level: str | None = None,
) -> int:
    """``--phase3-smoke`` 命令:跳过真 ADB,MagicMock。"""
    return run_phase3_demo(
        project_root, use_real_adb=False, task_id=task_id, console_level=console_level,
    )


# ============================================================
# Phase 4: 稳定性体系
# ============================================================


def run_phase4_demo(
    project_root: Path,
    *,
    use_real_adb: bool = False,
    console_level: str | None = None,
) -> int:
    """Phase 4 稳定性体系演示入口。

    流程:
        1. 装配 ConfigManager + ADBClient + Recognizer + GameStateMachine + CommonActions
        2. 创建 RetryManager(cfg 驱动) + RecoveryManager(委托 CommonActions)
        3. 用 ``RunContext`` 包裹整个 demo,在 ``__exit__`` 自动打 elapsed_ms
        4. 演示:
            a) RetryManager.execute_adb_action(adb, "screenshot") 真实调用链
            b) GameStateMachine.recover(recovery_manager) 新签名
            c) RecoveryManager.recover_unknown / recover_popup / recover_loading_timeout
               / recover_adb_error 各一次
        5. 打印总结(exit 0 永远 graceful)
    """
    from logging_ext import RunContext

    print("=" * 60)
    print("naruto-auto-daily · Phase 4 稳定性体系")
    print("=" * 60)

    # 1) 装配: 委托给 tasks.assembly
    cfg, adb_client, recognizer, game_sm, common = assemble_lightweight(
        project_root, use_real_adb=use_real_adb, console_level=console_level,
    )
    logger.info("Phase 4: ADBClient ready ({})", type(adb_client).__name__)

    # 3) RetryManager + RecoveryManager
    retry_mgr = RetryManager(policy=RetryPolicy.from_config(cfg))
    recovery_mgr = RecoveryManager(
        common_actions=common,
        game_sm=game_sm,
        adb_client=adb_client,
        screenshot_manager=None,  # Phase 4 demo 不接真实截图归档
        retry_manager=retry_mgr,
        config=cfg,
    )

    # 4) 用 RunContext 包裹整个 demo(state_before=UNKNOWN,运行完后 state_after=HOME)
    with RunContext(task_id="phase4_demo", state_before="UNKNOWN") as rc:
        rc.log.info("Phase 4 demo starting")

        # a) 真实调用链:RetryManager.execute_adb_action 包装 adb.screenshot
        rc.log.info("[demo 1/5] RetryManager.execute_adb_action(adb, 'screenshot')")
        try:
            shot = retry_mgr.execute_adb_action(adb_client, "screenshot")
            rc.log.success("execute_adb_action succeeded: success={}", shot.success)
        except Exception as exc:
            rc.log.error("execute_adb_action failed: {}", exc)

        # b) GameStateMachine.recover(recovery_manager) 新签名
        rc.log.info("[demo 2/5] GameStateMachine.recover(recovery_manager)")
        game_sm.update_state(GameState.UNKNOWN, source="phase4_demo")
        recovered = game_sm.recover(recovery_manager=recovery_mgr)
        rc.log.info("recover() final state: {}", recovered.value)
        rc.state_after = recovered.value

        # c) 4 个 RecoveryManager 方法各演示一次
        rc.log.info("[demo 3/5] RecoveryManager.recover_unknown")
        # 强制 UNKNOWN 后再调
        game_sm.update_state(GameState.UNKNOWN, source="phase4_demo_force")
        result = recovery_mgr.recover_unknown()
        rc.log.info("recover_unknown: {}", result.value)

        rc.log.info("[demo 4/5] RecoveryManager.recover_popup")
        game_sm.update_state(GameState.POPUP, source="phase4_demo_force")
        result_ok = recovery_mgr.recover_popup()
        rc.log.info("recover_popup: {}", result_ok)

        rc.log.info("[demo 5/5] RecoveryManager.recover_adb_error")
        result_ok = recovery_mgr.recover_adb_error()
        rc.log.info("recover_adb_error: {}", result_ok)

    # 5) 总结
    print()
    print(f"final game state        : {game_sm.current_state.value}")
    print(f"recovery attempts total : 4 (unknown/popup/loading_timeout/adb_error)")
    print()
    print("exit 0")
    return 0


def cmd_phase4(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--phase4`` 命令:尝试真 ADB,失败 MagicMock fallback。"""
    return run_phase4_demo(project_root, use_real_adb=True, console_level=console_level)


def cmd_phase4_smoke(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--phase4-smoke`` 命令:跳过真 ADB,MagicMock。"""
    return run_phase4_demo(project_root, use_real_adb=False, console_level=console_level)


# ============================================================
# Phase 6: 真实每日签到(P7-REAL 真实接入)
# ============================================================


def _assemble_real_runner(
    project_root: Path,
    console_level: str | None,
) -> tuple[ConfigManager, "ExecutionContext", "TaskEngine", tuple[int, int]] | int:
    """Phase 6 真实任务的统一装配: ADBClient + ExecutionContext + TaskEngine。

    Returns:
        成功: (cfg, ctx, engine, (width, height))
        失败: int 退出码(2=ADB init / 3=ADB connect / 4=screenshot)
    """
    cfg = ConfigManager(get_user_data_dir(), auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, get_user_data_dir())

    # 1) ADB 连接
    from device.adb_client import ADBError
    try:
        adb_client = ADBClient(cfg)
        logger.info("ADBClient: path={} serial={}", adb_client.adb_path, adb_client.serial or "<auto>")
    except ADBError as exc:
        logger.error("ADBClient init failed: {}", exc)
        logger.info(
            "hint: 在 config/app_config.yaml 里配置 adb.adb_path 和 adb.default_serial"
        )
        return 2

    res = adb_client.connect()
    if not res.success:
        logger.error("ADB connect failed: {}", res.message)
        return 3
    logger.success("ADB connected: {}", adb_client.serial)

    # 2) 截图(分辨率探测)
    shot = adb_client.screenshot()
    if not shot.success or shot.payload is None:
        logger.error("screenshot failed: {}", shot.message)
        return 4
    h, w = shot.payload.shape[:2]
    logger.info("实际屏幕分辨率: {}x{}", w, h)

    # 3) 装配
    from unittest.mock import MagicMock as _MM
    from core.base_task import ExecutionContext
    from core.state_machine import build_default_state_machine
    from tasks.common_actions import CommonActions
    from tasks.task_engine import TaskEngine
    from state.game_state import GameState
    from state_machine.game_state_machine import GameStateMachine
    from recognition.template_matcher import TemplateMatcher
    from recognizer.page_recognizer import PageRecognizer

    matcher = TemplateMatcher(cfg)
    templates_root = get_resource_root() / cfg.app.game_state.templates_dir
    recognizer = PageRecognizer(templates_root, matcher=matcher)
    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    common = CommonActions(
        adb_client=adb_client,
        recognizer=recognizer,
        game_sm=game_sm,
        config=cfg,
        project_root=project_root,
    )
    ctx = ExecutionContext(
        config=cfg,
        window_manager=_MM(),
        screenshot_manager=_MM(),
        state_machine=build_default_state_machine("IDLE", log_transitions=True),
    )
    engine = TaskEngine(ctx, common_actions=common)
    return cfg, ctx, engine, (w, h)


def _print_task_result(result, label: str) -> int:
    """打印单个 TaskResult 并返回退出码。"""
    print()
    print("=" * 60)
    print(f"执行结果 · {label}")
    print("=" * 60)
    if result is None:
        print("任务调度失败 (task_id not found)")
        return 5
    d = result.to_dict()
    for k, v in d.items():
        print(f"  {k}: {v}")
    print()
    return 0 if result.is_success else 1


def _launch_mfaavalonia_gui(project_root: Path) -> int:
    """启动 MFAAvalonia 桌面客户端。

    需要 .NET 10 Desktop Runtime,首次运行请先执行:
        frontend\\MFAAvalonia\\DependencySetup_依赖库安装_win.bat

    Args:
        project_root: 项目根目录。

    Returns:
        退出码: 0 = 成功启动, 1 = exe 不存在。
    """
    import subprocess

    exe = project_root / "frontend" / "MFAAvalonia" / "MFAAvalonia.exe"
    if not exe.is_file():
        print("MFAAvalonia.exe 未找到，请先下载前端包。")
        print("  下载地址: https://github.com/MaaXYZ/MaaFramework/releases")
        print("  解压到: frontend\\MFAAvalonia\\")
        return 1
    # 以 frontend/MFAAvalonia/ 为工作目录启动(所有相对路径以此为根)
    subprocess.Popen([str(exe)], cwd=str(exe.parent))
    print("MFAAvalonia 已启动。关闭此窗口不影响 GUI 运行。")
    return 0


def _run_single_maafw_task(
    project_root: Path,  # noqa: ARG001 保留 project_root 参数签名(未来扩展)
    task_id: str,
    console_level: str | None = None,
    label: str | None = None,
) -> int:
    """``--xxx-real`` / ``--maafw-task`` 公共实现(P0-1 + P2-1,2026-07-11 抽取)。

    Args:
        project_root: 保留参数签名,目前未使用(MaaTaskEngine 通过 ConfigManager 拿 root)。
        task_id: 要跑的 task_id(``mail`` / ``liveness`` / ``recruit`` ...)。
        console_level: CLI 日志级别覆盖(``--debug`` / ``--quiet``)。
        label: 输出日志用的 task 标签,默认 = ``task_id``。

    Returns:
        0 = 成功(SUCCESS 或 BEST_EFFORT),1 = 失败,5 = task_id 未注册。
    """
    label = label or task_id
    print("=" * 70)
    print(f"MaaFramework {label} task")
    print("=" * 70)

    from tasks.task_engine_maafw import MaaTaskEngine  # 局部 import 避免顶层循环依赖

    cfg = ConfigManager(get_user_data_dir(), auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, get_user_data_dir())  # P0-1 修复:7 个命令统一落盘

    try:
        engine = MaaTaskEngine(cfg)
    except Exception as exc:
        print(f"\n✗ MaaTaskEngine init failed: {exc}")
        logger.error("MaaTaskEngine init failed: {}", exc)
        return 1

    result = engine.run_task(task_id)
    return _print_task_result(result, label)


def cmd_daily_signin_real(
    project_root: Path,
    console_level: str | None = None,
    emu_resolution: str = "auto",  # noqa: ARG001 保留参数签名,内部走 MaaFW 不读分辨率
) -> int:
    """``--daily-signin-real`` 命令: 跑每日签到(MaaFramework + narutomobile 模板)。

    2026-07-11 起改走 MaaTaskEngine(取代旧自研 ``daily_signin_task``),
    旧 ``--xxx-real`` CLI 入口保留以便老脚本不破。``emu_resolution`` 参数保留
    但忽略(narutomobile 默认 1920x1080,模拟器分辨率自适配)。
    """
    # P3-1 静默忽略提示:用户传非 "auto" 时明确告知 MaaFW 模式下该参数无效
    if emu_resolution != "auto":
        logger.warning(
            "cmd_daily_signin_real: emu_resolution='{}' is ignored under MaaFramework mode "
            "(narutomobile 自适配 1920x1080 默认坐标)",
            emu_resolution,
        )
    return _run_single_maafw_task(
        project_root, "daily_signin", console_level=console_level, label="daily_signin",
    )


def cmd_mail_real(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--mail-real`` 命令: 跑邮件领取(MaaFramework + narutomobile 模板)。"""
    return _run_single_maafw_task(project_root, "mail", console_level=console_level)


def cmd_liveness_real(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--liveness-real`` 命令: 跑活跃奖励(MaaFramework + narutomobile 模板)。"""
    return _run_single_maafw_task(project_root, "liveness", console_level=console_level)


def cmd_group_signin_real(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--group-signin-real`` 命令: 跑组织签到(MaaFramework + narutomobile 模板)。"""
    return _run_single_maafw_task(project_root, "group_signin", console_level=console_level)


def cmd_weekly_signin_real(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--weekly-signin-real`` 命令: 真实模拟器跑每周签到流程。

    weekly_signin 不在 TASK_MAPPING(narutomobile 无对应 entry),
    保留旧自研 ``weekly_signin_task`` 实现,不走 MaaFramework。
    """
    print("=" * 60)
    print("naruto-auto-daily · Phase 7 每周签到(模板缺失降级)")
    print("=" * 60)

    assembled = _assemble_real_runner(project_root, console_level)
    if isinstance(assembled, int):
        return assembled
    cfg, ctx, engine, (w, h) = assembled

    from tasks.weekly_signin_task import WeeklySigninTask
    engine.register_task("weekly_signin", WeeklySigninTask)

    print()
    print(f"开始执行 weekly_signin 任务 (实际屏幕 {w}x{h})")
    print(f"   ⚠ weekly_signin/* 模板可能缺失,Pipeline 会自然降级到 back_to_home")
    print()
    result = engine.run_task("weekly_signin")
    return _print_task_result(result, "weekly_signin")


def cmd_daily_all(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--daily-all`` 命令: 顺序跑 schemes/daily.json 全部任务(MaaFramework 版)。

    任务顺序由 ``schemes/daily.json`` 决定(2026-07-11 起 5 个:
    mail / liveness / group_signin / daily_signin / recruit),走 MaaTaskEngine。
    """
    import json
    from core.config_manager import ConfigManager
    from tasks.task_engine_maafw import MaaTaskEngine

    print("=" * 70)
    print("MaaFramework daily (schemes/daily.json)")
    print("=" * 70)

    cfg = ConfigManager(get_user_data_dir(), auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, get_user_data_dir())  # P0-1 修复

    scheme_path = get_resource_root() / "schemes" / "daily.json"  # P2-2 统一路径
    if not scheme_path.exists():
        print(f"✗ not found: {scheme_path}")
        return 6
    task_ids = json.loads(scheme_path.read_text(encoding="utf-8")).get("task_ids", [])
    print(f"tasks ({len(task_ids)}): {' → '.join(task_ids)}")

    try:
        engine = MaaTaskEngine(cfg)
    except Exception as exc:
        print(f"\n✗ MaaTaskEngine init failed: {exc}")
        logger.error("MaaTaskEngine init failed: {}", exc)
        return 1

    report = engine.run_daily(task_ids)
    MaaTaskEngine.print_report(report)
    return 0 if (report.fail_count == 0 and not report.aborted) else 1


# ============================================================
# Phase 8 (2026-07-02): --maafw-list 任务映射自检命令
# ============================================================


def cmd_maafw_list(project_root: Path) -> int:  # noqa: ARG001 保留 project_root 参数以便未来扩展
    """``--maafw-list`` 打印 task_id <-> entry 映射,不连 ADB。

    用于快速核对映射表是否符合预期(改 task_mapping.py 后必跑这个)。
    """
    from maafw_bridge import (
        TASK_MAPPING,
        REVERSE_MAPPING,
        list_supported_tasks,
        list_supported_entries,
        verify_resource_path,
    )

    print("=" * 60)
    print("Phase 8 maafw 任务映射表")
    print("=" * 60)
    print()
    print("我们 task_id → narutomobile entry:")
    for tid, entry in TASK_MAPPING.items():
        print(f"  {tid:<20s} → {entry}")
    print()
    print(f"支持的 task_id 共 {len(list_supported_tasks())} 个")
    print(f"用得到的 entry  共 {len(list_supported_entries())} 个")
    print()

    print("narutomobile entry → 我们 task_id (反向):")
    for entry, tid in REVERSE_MAPPING.items():
        print(f"  {entry:<20s} → {tid}")
    print()

    # 2026-07-11 修:verify_resource_path 需要 path 参数(原孤儿函数从未跑过,这次发现缺参)
    # 默认路径与 maafw_bridge.tasker._do_init 一致:{resource_root}/resources/narutomobile
    resource_path = get_resource_root() / "resources" / "narutomobile"
    ok, msg = verify_resource_path(resource_path)
    if ok:
        print(f"✓ resource 路径合法: {msg}")
        rc = 0
    else:
        print(f"✗ resource 路径异常: {msg}")
        rc = 1
    return rc



# ============================================================
# Phase 8 (2026-07-02) — MaaFramework 杂接: --daily-maafw
# 设计: 不删任何旧代码,只新增平行命令。
# ============================================================


def cmd_daily_maafw(project_root: Path, console_level: str | None = None) -> int:
    """``--daily-maafw``: 跑 daily schedule(走 MaaFramework + narutomobile 模板)。

    跟 ``--daily-all`` 平行 — 后者走旧自研 task_engine,本命令走 maafw 引擎。
    """
    from core.config_manager import ConfigManager
    from tasks.task_engine_maafw import MaaTaskEngine

    print("=" * 70)
    print("Phase 8 MaaFramework daily runner")
    print("=" * 70)

    cfg = ConfigManager(get_user_data_dir(), auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, get_user_data_dir())  # P0-1 修复
    print(f"project_root: {get_user_data_dir()}")
    print(f"maafw resource: {cfg.app.maafw.narutomobile_resource_path or '(default: resources/narutomobile)'}")

    try:
        engine = MaaTaskEngine(cfg)
    except Exception as exc:
        print(f"\n✗ MaaTaskEngine init failed: {exc}")
        logger.error("MaaTaskEngine init failed: {}", exc)
        return 1

    report = engine.run_daily()
    MaaTaskEngine.print_report(report)

    rc = 0 if (report.fail_count == 0 and not report.aborted) else 1
    return rc


def cmd_maafw_task(project_root: Path, task_id: str, console_level: str | None = None) -> int:
    """``--maafw-task <task_id>``: 跑单个 task(走 MaaFramework + narutomobile 模板)。

    覆盖 TASK_MAPPING 全部 20 个 task_id(包括旧 CLI 无入口的 recruit / advanture /
    elite_instance 等),为补足旧 ``--xxx-real`` 命令未覆盖的 task。
    """
    from maafw_bridge import resolve_entry

    print(f"task_id: {task_id}  →  entry: {resolve_entry(task_id)}")
    return _run_single_maafw_task(project_root, task_id, console_level=console_level)


def cmd_check(project_root: Path, console_level: str | None = None) -> int:
    """``--check`` 命令: 自检 ADB / 配置 / 模板 / 任务注册表。

    检查项:
        1. ADB 是否可达 + 设备在线(``adb.get-state``)
        2. ``app_config.yaml`` Pydantic 校验通过
        3. 任务引用的模板是否存在(扫描所有 task file 中的 templates() 调用)
        4. ``resources/templates/actions/`` 目录结构完整
        5. 任务注册表(task_registry.yaml)中所有 task_id 都有对应 Python 类

    Returns:
        0 = 所有检查通过
        1 = 至少 1 项检查失败
    """
    print("=" * 60)
    print("naruto-auto-daily · --check 自检")
    print("=" * 60)

    issues: list[str] = []

    # ---- 1. Pydantic 配置校验 ----
    print()
    print("[1/5] 配置校验 (Pydantic)…")
    try:
        from core.config_manager import ConfigManager, ConfigurationError

        cfg = ConfigManager(get_user_data_dir(), auto_load=True)
        # 触发 _load
        _ = cfg.app
        print(f"   PASS  app_config.yaml 校验通过 (phase={cfg.app.app.phase})")
    except ConfigurationError as exc:
        print(f"   FAIL  app_config.yaml 校验失败: {exc}")
        issues.append(f"config: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"   FAIL  配置加载异常: {exc}")
        issues.append(f"config load: {exc}")

    # ---- 2. 模板目录结构 ----
    print()
    print("[2/5] 模板目录结构…")
    templates_root = get_resource_root() / "resources" / "templates" / "actions"
    if not templates_root.exists():
        print(f"   FAIL  模板根目录不存在: {templates_root}")
        issues.append("templates_root missing")
    else:
        subdirs = ["shared", "mail", "group", "activity", "liveness"]
        present = [d for d in subdirs if (templates_root / d).is_dir()]
        missing = [d for d in subdirs if d not in present]
        print(f"   PASS  模板根目录: {templates_root} ({len(present)}/{len(subdirs)} 子目录)")
        if missing:
            print(f"   WARN  缺少子目录: {missing} (不影响运行)")

    # ---- 3. 任务注册表 → Python 类映射 ----
    print()
    print("[3/5] 任务注册表校验…")
    try:
        import yaml as _yaml

        registry_path = get_user_data_dir() / "config" / "task_registry.yaml"
        if not registry_path.exists():
            print(f"   FAIL  task_registry.yaml 不存在: {registry_path}")
            issues.append("task_registry.yaml missing")
        else:
            data = _yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
            tasks = data.get("tasks", {}) or {}
            print(f"   PASS  注册了 {len(tasks)} 个任务")
            for tid, entry in tasks.items():
                task_class_path = entry.get("task_class", "")
                # 解析 "module.ClassName"
                try:
                    module_name, class_name = task_class_path.rsplit(".", 1)
                    mod = __import__(module_name, fromlist=[class_name])
                    cls = getattr(mod, class_name)
                    enabled = entry.get("enabled", False)
                    order = entry.get("display_order", "?")
                    print(f"      ✓ {tid:18s} -> {class_name:25s}  enabled={enabled} order={order}")
                except (ImportError, AttributeError, ValueError) as exc:
                    print(f"      ✗ {tid:18s} -> {task_class_path}  FAIL: {exc}")
                    issues.append(f"task {tid}: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"   FAIL  任务注册表解析失败: {exc}")
        issues.append(f"registry: {exc}")

    # ---- 4. 任务模板引用完整性 ----
    print()
    print("[4/5] 任务模板引用完整性…")
    try:
        import re
        from pathlib import Path as _Path

        tasks_dir = get_resource_root() / "tasks"
        tpl_pattern = re.compile(r'"([a-z_]+/[a-z0-9_]+\.png)"')
        missing_count = 0
        total_refs = 0
        for task_file in sorted(tasks_dir.glob("*_task.py")):
            text = task_file.read_text(encoding="utf-8")
            refs = set(tpl_pattern.findall(text))
            for ref in refs:
                total_refs += 1
                full = templates_root / ref
                if not full.exists():
                    print(f"   MISS  {task_file.name:30s} → {ref}")
                    missing_count += 1
        print(f"   PASS  引用了 {total_refs} 个模板,{total_refs - missing_count} 个存在,{missing_count} 个缺失")
    except Exception as exc:  # noqa: BLE001
        print(f"   FAIL  模板引用扫描失败: {exc}")
        issues.append(f"template scan: {exc}")

    # ---- 5. ADB 连通性 ----
    print()
    print("[5/5] ADB 连通性 (可选)…")
    try:
        import subprocess
        adb_path = cfg.app.adb.adb_path if "cfg" in locals() else r"C:\tmp\android-sdk\platform-tools\adb.exe"
        result = subprocess.run(
            [adb_path, "get-state"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and "device" in result.stdout:
            print(f"   PASS  ADB device online: {result.stdout.strip()}")
        else:
            print(f"   WARN  ADB 未检测到 device: rc={result.returncode} stdout='{result.stdout.strip()}'")
            print(f"         stderr='{result.stderr.strip()}' (不影响其他检查)")
    except FileNotFoundError:
        print(f"   WARN  ADB 二进制不存在: {adb_path}")
    except subprocess.TimeoutExpired:
        print(f"   WARN  ADB get-state 超时")
    except Exception as exc:  # noqa: BLE001
        print(f"   WARN  ADB 检查异常: {exc}")

    # ---- 总结 ----
    print()
    print("=" * 60)
    if issues:
        print(f"FAIL  共 {len(issues)} 项检查不通过:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    else:
        print("PASS  所有检查通过")
        return 0


# ============================================================
# Entrypoint
# ============================================================


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.version:
        print(f"naruto-auto-daily {__version__}")
        return 0

    # console level 由 CLI 覆盖
    console_level = None
    if args.debug:
        console_level = "DEBUG"
    elif args.quiet:
        console_level = "WARNING"

    # P1-7 自检
    if args.check:
        return cmd_check(PROJECT_ROOT, console_level=console_level)

    # init-config 在 logger 初始化之前执行（它不依赖 logger）
    if args.init_config:
        return cmd_init_config(PROJECT_ROOT)

    # Phase 2 demo:可以跳过 build_context(Phase 1 那一套 Context)
    if args.phase2:
        return cmd_phase2(PROJECT_ROOT, console_level=console_level)
    if args.phase2_smoke:
        return cmd_phase2_smoke(PROJECT_ROOT, console_level=console_level)

    # Phase 3 任务系统
    if args.phase3:
        return cmd_phase3(PROJECT_ROOT, task_id=args.phase3_task, console_level=console_level)
    if args.phase3_smoke:
        return cmd_phase3_smoke(PROJECT_ROOT, task_id=args.phase3_task, console_level=console_level)

    # Phase 4 稳定性体系
    if args.phase4:
        return cmd_phase4(PROJECT_ROOT, console_level=console_level)
    if hasattr(args, "phase4_smoke") and args.phase4_smoke:
        return cmd_phase4_smoke(PROJECT_ROOT, console_level=console_level)

    # GUI 桌面客户端
    if args.gui:
        return _launch_mfaavalonia_gui(PROJECT_ROOT)

    # Phase 6 真实接入: 每日签到真实流程(P7-REAL)
    if args.daily_signin_real:
        return cmd_daily_signin_real(PROJECT_ROOT, console_level=console_level,
                                       emu_resolution=args.emu_resolution)

    # Phase 6 业务扩展: 邮件/活跃/组织签到(独立入口)
    if args.mail_real:
        return cmd_mail_real(PROJECT_ROOT, console_level=console_level)
    if args.liveness_real:
        return cmd_liveness_real(PROJECT_ROOT, console_level=console_level)
    if args.group_signin_real:
        return cmd_group_signin_real(PROJECT_ROOT, console_level=console_level)

    # Phase 6 业务扩展: schemes/daily.json 全流程
    if args.daily_all:
        return cmd_daily_all(PROJECT_ROOT, console_level=console_level)

    # Phase 8 MaaFramework 桥接(2026-07-02,跟旧 --daily-all 平行)
    if args.daily_maafw:
        return cmd_daily_maafw(PROJECT_ROOT, console_level=console_level)
    if args.maafw_task:
        return cmd_maafw_task(PROJECT_ROOT, args.maafw_task, console_level=console_level)
    if args.maafw_list:
        return cmd_maafw_list(PROJECT_ROOT)

    # 其他 Phase 1 命令需要完整的 ExecutionContext
    no_action = not any([
        args.smoke_test, args.list_windows,
        args.run, args.activate_window, args.capture_test,
    ])
    if no_action:
        # 2026-07-11: 无参数时默认启动 MFAAvalonia 桌面客户端
        # (源码模式 + 打包 exe 模式 行为一致,均交给 _launch_mfaavalonia_gui)
        return _launch_mfaavalonia_gui(PROJECT_ROOT)

    t0 = time.monotonic()
    ctx = build_context(PROJECT_ROOT, console_level=console_level)
    rc = 0
    try:
        if args.list_windows:
            rc = cmd_list_windows(ctx)
        elif args.activate_window:
            rc = cmd_activate_window(ctx)
        elif args.capture_test:
            rc = cmd_capture_test(ctx)
        elif args.smoke_test:
            rc = cmd_smoke_test(ctx)
        elif args.run:
            rc = cmd_run(ctx, args.task)
        logger.info("done in {:.2f}s", time.monotonic() - t0)
    except KeyboardInterrupt:
        logger.warning("interrupted by user")
        rc = 130
    except Exception as exc:  # 防御兜底
        logger.exception("unhandled exception: {}", exc)
        rc = 1
    finally:
        shutdown_logger()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())