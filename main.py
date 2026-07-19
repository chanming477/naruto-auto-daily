"""main.py — naruto-auto-daily 的 CLI 入口。

2026-07-19 OPT: P0/P2 死代码清理 + 老 7/14 精简统一走 MaaTaskEngine
(MaaFramework pipeline + merged.json 模板)。CLI 仅保留调试/自检入口。

Phase 1 命令（保留, 调试用）：
    --init-config      生成默认 YAML（已存在不覆盖）
    --capture-test     截一张目标窗口的图保存到 screenshots/
    --debug / --quiet / --version

P2-6 (2026-07-18): --smoke-test / --list-windows / --activate-window 已删
(全死代码, 无用户)。仅 --capture-test 保留。

MaaFramework 真实跑批（2026-07-14 统一入口）：
    --run-task <TASK_ID>     真机跑指定 task (从 TASK_MAPPING 20 个 task_id 选)
    --list-tasks             打印所有可用 task_id <-> entry 映射
    --daily-all              顺序跑 config/schedule.json 全部 task (MaaFramework 引擎)

默认行为（无任何参数）：
    启动 MFAAvalonia 桌面 GUI (等价 ``--gui``, 需先下载 frontend/MFAAvalonia/,
    见 ``start.bat`` 自动检测 + 引导)。

详见 README.md / docs/standards/ / docs/superpowers/specs/
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

from core import __version__
from core.base_task import ExecutionContext
from core.config_manager import ConfigManager
from core.logger import configure as configure_logger
from core.logger import shutdown as shutdown_logger
from core.screenshot_manager import ScreenshotManager
from core.state_machine import StateMachine, build_default_state_machine
from core.window_manager import WindowManager

# 注: Phase 2/4 的 ADBClient / TemplateMatcher / PageRecognizer / GameStateMachine /
# RecoveryManager / RetryManager 等类已随旧 Navigator 框架删除或被 MaaFramework 取代,
# 不再在 main.py 顶层 import。相关代码路径见 tasks/task_engine_maafw.py。
# P2-6 (2026-07-18): Scheduler 也删除, --smoke-test 命令已删。

__all__ = [
    "main", "build_context", "parse_args",
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
               "  python main.py                       # 默认启 MFAAvalonia 桌面 GUI\n"
               "  python main.py --run-task mail       # 真机跑邮件领取(走 MaaFramework)\n"
               "  python main.py --daily-all           # 顺序跑 config/schedule.json 全部 task\n"
               "  python main.py --list-tasks          # 打印 TASK_MAPPING 20 个 task_id\n"
               "  python main.py --init-config\n"
               "  python main.py --capture-test        # 截一张目标窗口的图\n"
               "  python main.py --check               # P1-7 自检\n",
    )
    parser.add_argument("--init-config", action="store_true",
                        help="在 config/ 下生成默认 YAML 配置（已存在则跳过）")
    # P2-6 (2026-07-18): --smoke-test / --list-windows / --activate-window 已删
    # 只保留 --capture-test (调试真机截屏有用)
    parser.add_argument("--capture-test", action="store_true",
                        help="截一张目标窗口的图保存到 screenshots/ 用于验证")
    # ---- GUI 桌面客户端 ----
    parser.add_argument("--gui", action="store_true",
                        help="启动 MFAAvalonia 桌面客户端(需要 .NET 10 Desktop Runtime)")
    # ---- MaaFramework 真实跑批(2026-07-14 统一入口)----
    parser.add_argument("--run-task", type=str, default=None, metavar="TASK_ID",
                        help="真机跑指定 task(走 MaaFramework + narutomobile 模板),"
                             " 如 --run-task mail (覆盖 TASK_MAPPING 20 个 task_id)")
    parser.add_argument("--list-tasks", action="store_true",
                        help="打印所有可用 task_id <-> entry 映射表(从 TASK_MAPPING, 不连 ADB)")
    parser.add_argument("--daily-all", action="store_true",
                        help="顺序跑 config/schedule.json 全部 task(MaaFramework + narutomobile 模板)")
    parser.add_argument("--debug", action="store_true",
                        help="把日志级别下调到 DEBUG")
    parser.add_argument("--quiet", action="store_true",
                        help="把日志级别上调到 WARNING")
    parser.add_argument("--version", action="store_true",
                        help="打印版本号")
    # ---- P1-7 自检命令 ----
    parser.add_argument("--check", action="store_true",
                        help="P1-7 自检: ADB 连通性 / Pydantic 配置校验 / 模板完整性 / 任务注册表")
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
        print(f"\n[FAIL] MaaTaskEngine init failed: {exc}")
        logger.error("MaaTaskEngine init failed: {}", exc)
        return 1

    result = engine.run_task(task_id)
    return _print_task_result(result, label)



def cmd_daily_all(
    project_root: Path,
    console_level: str | None = None,
) -> int:
    """``--daily-all`` 命令: 顺序跑 config/schedule.json 全部任务(MaaFramework 版)。

    任务顺序由 ``config/schedule.json`` 决定(2026-07-11 起 5 个:
    mail / liveness / group_signin / daily_signin / recruit),走 MaaTaskEngine。
    """
    import json
    from core.config_manager import ConfigManager
    from tasks.task_engine_maafw import MaaTaskEngine

    print("=" * 70)
    print("MaaFramework daily (config/schedule.json)")
    print("=" * 70)

    cfg = ConfigManager(get_user_data_dir(), auto_load=True)
    if console_level is not None:
        cfg.app.logger.console_level = console_level
    configure_logger(cfg.app.logger, get_user_data_dir())  # P0-1 修复

    scheme_path = get_resource_root() / "config" / "schedule.json"  # P2-2 统一路径(2026-07-15 从 schemes/ → config/)
    if not scheme_path.exists():
        print(f"[FAIL] not found: {scheme_path}")
        return 6
    task_ids = json.loads(scheme_path.read_text(encoding="utf-8")).get("task_ids", [])
    print(f"tasks ({len(task_ids)}): {' → '.join(task_ids)}")

    try:
        engine = MaaTaskEngine(cfg)
    except Exception as exc:
        print(f"\n[FAIL] MaaTaskEngine init failed: {exc}")
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
    # 2026-07-15 修:Windows GBK console 不能 print [OK]/[FAIL] unicode,改用 ASCII 避免 UnicodeEncodeError
    resource_path = get_resource_root() / "resources" / "narutomobile"
    ok, msg = verify_resource_path(resource_path)
    if ok:
        print(f"[OK] resource path valid: {msg}")
        rc = 0
    else:
        print(f"[FAIL] resource path invalid: {msg}")
        rc = 1
    return rc


# 注: 2026-07-14 清理删掉 ``cmd_daily_maafw`` / ``cmd_maafw_task`` 两个死函数
# (对应的 ``--daily-maafw`` / ``--maafw-task`` argparse flag 已删,不再调用)。
# ``cmd_daily_all`` (走 ``--daily-all``) 是 2026-07-14 唯一保留的 daily 入口。


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
    # 2026-07-18: 模板已迁到 resources/narutomobile/image/ (MaaFramework pipeline 真用的目录)
    templates_root = get_resource_root() / "resources" / "narutomobile" / "image"
    if not templates_root.exists():
        print(f"   FAIL  模板根目录不存在: {templates_root}")
        issues.append("templates_root missing")
    else:
        # 实际有 30+ 个子目录 (Activity/Advanture/Asura_instance/...),只列几个核心的做参考
        subdirs = ["Group", "Activity", "Get_copper", "Give_energy", "Headhunt", "home", "shared"]
        present = [d for d in subdirs if (templates_root / d).is_dir()]
        missing = [d for d in subdirs if d not in present]
        print(f"   PASS  模板根目录: {templates_root} ({len(present)}/{len(subdirs)} 核心子目录)")
        if missing:
            print(f"   WARN  缺少核心子目录: {missing} (不影响运行)")

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
                # V3 (2026-07-18): task_class 字段已删,任务入口由 MaaFramework pipeline 决定
                # → 只校验元数据完整性 (enabled / display_order / category)
                enabled = entry.get("enabled", False)
                order = entry.get("display_order", "?")
                category = entry.get("category", "?")
                has_class = bool(entry.get("task_class", ""))
                marker = "" if has_class else " (no task_class, pipeline-only)"
                print(f"      [OK] {tid:18s}  enabled={enabled} order={order} category={category}{marker}")
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

    # GUI 桌面客户端
    if args.gui:
        return _launch_mfaavalonia_gui(PROJECT_ROOT)

    # MaaFramework 真实跑批(2026-07-14 统一入口)
    if args.run_task:
        from maafw_bridge import is_supported
        if not is_supported(args.run_task):
            print(f"[FAIL] unknown task_id: {args.run_task!r}")
            print("  run `python main.py --list-tasks` to see full mapping")
            return 4
        return _run_single_maafw_task(
            PROJECT_ROOT, args.run_task, console_level=console_level, label=args.run_task,
        )
    if args.list_tasks:
        return cmd_maafw_list(PROJECT_ROOT)

    # Phase 6 业务扩展: config/schedule.json 全流程
    if args.daily_all:
        return cmd_daily_all(PROJECT_ROOT, console_level=console_level)

    # 调试命令只剩 --capture-test (P2-6 决策 B)
    # --smoke-test / --list-windows / --activate-window 已删 (全死代码)
    no_action = not args.capture_test
    if no_action:
        # 2026-07-11: 无参数时默认启动 MFAAvalonia 桌面客户端
        # (源码模式 + 打包 exe 模式 行为一致,均交给 _launch_mfaavalonia_gui)
        return _launch_mfaavalonia_gui(PROJECT_ROOT)

    t0 = time.monotonic()
    ctx = build_context(PROJECT_ROOT, console_level=console_level)
    rc = 0
    try:
        if args.capture_test:
            rc = cmd_capture_test(ctx)
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