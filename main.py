"""main.py — naruto-auto-daily 的 CLI 入口 (V3 2026-07-19 OPT-1+OPT-2 大幅精简)。

V3 变更:
    - 删 4 个 core/ 死文件 (window_manager / screenshot_manager / base_task / state_machine)
    - 删 --capture-test / --run-task / --daily-all / --smoke-test / --list-windows / --activate-window
    - 删 build_context / cmd_capture_test / cmd_daily_all
    - 保留 --gui / --init-config / --list-tasks / --check / --debug / --quiet / --version
    - 无参数时默认启 MFAAvalonia 桌面 GUI

CLI 仅作调试/自检入口,业务跑批走 MFAAvalonia 桌面客户端(用户主要入口)。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 让 ``python main.py`` 和 ``python -m main`` 都能正常 import core.*
# 资源根:frozen 模式在 _MEIPASS(PyInstaller 解压目录),源码模式在 main.py 同级
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from core import __version__
from core.app_paths import get_resource_root, get_user_data_dir
from core.config_manager import ConfigManager
from core.logger import configure as configure_logger
from core.logger import shutdown as shutdown_logger

__all__ = [
    "main", "parse_args",
]


# ============================================================
# Parse args
# ============================================================


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="naruto-auto-daily",
        description="火影手游日常自动化工具 (MaaFramework + MFAAvalonia 桌面 GUI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python main.py                       # 默认启 MFAAvalonia 桌面 GUI\n"
               "  python main.py --list-tasks          # 打印 TASK_MAPPING 全部 task_id\n"
               "  python main.py --init-config         # 生成默认 config/ YAML\n"
               "  python main.py --check               # P1-7 自检 (config / templates / ADB)\n",
    )
    parser.add_argument("--init-config", action="store_true",
                        help="在 config/ 下生成默认 YAML 配置(已存在则跳过)")
    parser.add_argument("--gui", action="store_true",
                        help="启动 MFAAvalonia 桌面客户端(需要 .NET 10 Desktop Runtime)")
    parser.add_argument("--list-tasks", action="store_true",
                        help="打印所有可用 task_id <-> entry 映射表(从 TASK_MAPPING, 不连 ADB)")
    parser.add_argument("--debug", action="store_true",
                        help="把日志级别下调到 DEBUG")
    parser.add_argument("--quiet", action="store_true",
                        help="把日志级别上调到 WARNING")
    parser.add_argument("--version", action="store_true",
                        help="打印版本号")
    parser.add_argument("--check", action="store_true",
                        help="P1-7 自检: 配置 / 模板 / 任务注册表 / ADB")
    return parser.parse_args(argv)


# ============================================================
# Subcommands
# ============================================================


def cmd_init_config(project_root: Path) -> int:
    cfg = ConfigManager(get_user_data_dir(), auto_load=False)
    created = cfg.save_default_configs()
    if not created:
        print("[init-config] 所有配置文件已存在,未做任何修改。")
        print(f"[init-config] 配置目录: {cfg.config_dir}")
    else:
        print("[init-config] 已生成以下默认配置:")
        for p in created:
            print(f"  - {p}")
    return 0


def _launch_mfaavalonia_gui(project_root: Path) -> int:
    """启动 MFAAvalonia 桌面客户端。

    需要 .NET 10 Desktop Runtime,首次运行请先执行:
        DependencySetup_依赖库安装_win.bat
    """
    import subprocess

    exe = project_root / "MFAAvalonia.exe"
    if not exe.is_file():
        print("MFAAvalonia.exe 未找到,请先下载前端包。")
        print("  下载地址: https://github.com/MaaXYZ/MaaFramework/releases")
        print("  解压到项目根目录")
        return 1
    subprocess.Popen([str(exe)], cwd=str(project_root))
    print("MFAAvalonia 已启动。关闭此窗口不影响 GUI 运行。")
    return 0


def cmd_maafw_list(project_root: Path) -> int:  # noqa: ARG001
    """``--list-tasks`` 打印 task_id <-> entry 映射,不连 ADB。

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
    print("task_id ↔ pipeline entry 映射表")
    print("=" * 60)
    print()
    print("我们 task_id → pipeline entry:")
    for tid, entry in TASK_MAPPING.items():
        print(f"  {tid:<20s} → {entry}")
    print()
    print(f"支持的 task_id 共 {len(list_supported_tasks())} 个")
    print(f"用得到的 entry  共 {len(list_supported_entries())} 个")
    print()

    print("pipeline entry → 我们 task_id (反向):")
    for entry, tid in REVERSE_MAPPING.items():
        print(f"  {entry:<20s} → {tid}")
    print()

    resource_path = get_resource_root() / "resources" / "narutomobile"
    ok, msg = verify_resource_path(resource_path)
    if ok:
        print(f"[OK] resource path valid: {msg}")
        rc = 0
    else:
        print(f"[FAIL] resource path invalid: {msg}")
        rc = 1
    return rc


def cmd_check(project_root: Path, console_level: str | None = None) -> int:
    """``--check`` 命令: 自检配置 / 模板 / 任务注册表 / ADB。

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
    print("[1/4] 配置校验 (Pydantic)…")
    try:
        from core.config_manager import ConfigManager, ConfigurationError

        cfg = ConfigManager(get_user_data_dir(), auto_load=True)
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
    print("[2/4] 模板目录结构…")
    templates_root = get_resource_root() / "resources" / "narutomobile" / "image"
    if not templates_root.exists():
        print(f"   FAIL  模板根目录不存在: {templates_root}")
        issues.append("templates_root missing")
    else:
        subdirs = ["Group", "Activity", "Get_copper", "Give_energy", "Headhunt", "home", "shared"]
        present = [d for d in subdirs if (templates_root / d).is_dir()]
        missing = [d for d in subdirs if d not in present]
        print(f"   PASS  模板根目录: {templates_root} ({len(present)}/{len(subdirs)} 核心子目录)")
        if missing:
            print(f"   WARN  缺少核心子目录: {missing} (不影响运行)")

    # ---- 3. 任务注册表校验 ----
    print()
    print("[3/4] 任务注册表校验…")
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
                enabled = entry.get("enabled", False)
                order = entry.get("display_order", "?")
                category = entry.get("category", "?")
                has_class = bool(entry.get("task_class", ""))
                marker = "" if has_class else " (no task_class, pipeline-only)"
                print(f"      [OK] {tid:18s}  enabled={enabled} order={order} category={category}{marker}")
    except Exception as exc:  # noqa: BLE001
        print(f"   FAIL  任务注册表解析失败: {exc}")
        issues.append(f"registry: {exc}")

    # ---- 4. ADB 连通性 ----
    print()
    print("[4/4] ADB 连通性 (可选)…")
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

    # init-config 在 logger 初始化之前执行
    if args.init_config:
        return cmd_init_config(PROJECT_ROOT)

    # GUI 桌面客户端
    if args.gui:
        return _launch_mfaavalonia_gui(PROJECT_ROOT)

    # 打印任务映射表
    if args.list_tasks:
        return cmd_maafw_list(PROJECT_ROOT)

    # 无参数时默认启动 MFAAvalonia 桌面客户端
    return _launch_mfaavalonia_gui(PROJECT_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
