# -*- mode: python ; coding: utf-8 -*-
"""naruto-auto-daily · PyInstaller spec (v0 — minimal)

Phase 1: Step 2 first-pass。spec 只列**已知必须**的:
  - 只读资源(resources/templates、resources/narutomobile、schemes)打进 frozen
  - hiddenimports 先放项目内自定义 package(maafw 走 pip 自动发现)

边打边补:打失败/运行时缺啥再加,不要预设。
"""
import sys
from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).resolve()

# 只读资源 — frozen 后会在 _MEIPASS 下,get_resource_root() 解析到
datas = [
    (str(PROJECT_ROOT / "resources" / "templates"),   "resources/templates"),
    (str(PROJECT_ROOT / "resources" / "narutomobile"), "resources/narutomobile"),
    (str(PROJECT_ROOT / "schemes"),                    "schemes"),
]

# 必装子模块(项目内自定义 package + maafw_bridge)
hiddenimports = [
    # 项目自研 package
    "core",
    "core.app_paths",
    "core.config_manager",
    "core.scheduler",
    "core.state_machine",
    "core.screenshot_manager",
    "core.window_manager",
    "core.base_task",
    "core.logger",
    "tasks",
    "tasks.assembly",
    "tasks.common_actions",
    "tasks.pipeline_runner",
    "tasks.navigator",
    "tasks.task_engine",
    "tasks.task_engine_maafw",
    "state",
    "state.game_state",
    "state_machine",
    "state_machine.game_state_machine",
    "device",
    "device.adb_client",
    "recognizer",
    "recognizer.page_recognizer",
    "recognition",
    "recognition.template_matcher",
    "recovery",
    "recovery.recovery_manager",
    "recovery.retry_manager",
    "logging_ext",
    "maafw_bridge",
    "ui",
    # maafw(走 pip,PyInstaller 通常能自动发现,显式列只是保险)
    "maafw",
    # stdlib 子模块(防止 PyInstaller 误判)
    "unittest.mock",
]

# requirements.txt 没装的(防止 PyInstaller 拉一堆用不上的)
# 注意:不要排除 unittest!unittest.mock 是 stdlib 子模块,显式 import 需要
excludes = [
    "tkinter",
    "matplotlib",
    "scipy",
    "pandas",
    "test",
    "tests",
    "pydoc",
]


a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="naruto-auto-daily",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,                # 去符号,缩 ~5-10MB
    upx=True,                  # 压缩 bootloader(只省 ~150KB,但聊胜于无)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,             # 桌面应用模式,双击直接弹 GUI 不弹控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
