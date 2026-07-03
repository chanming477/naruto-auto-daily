# 桌面应用打包方案 v1.0

> **目标**: 把项目打包成单文件 exe，用户双击即可启动 GUI，无需安装 Python
> **日期**: 2026-07-02
> **当前环境**: Python 3.14.4 + PyInstaller 6.20 + PySide6 + maafw 5.10.4

---

## 一、当前状态分析

### 1.1 依赖体积拆解

| 组件 | 大小 | 备注 |
|------|------|------|
| Python 3.14 运行时 | ~30 MB | 打包时会包含一部分 |
| PySide6 | ~120 MB | Qt6 Core/Gui/Widgets + platforms |
| maafw C++ DLLs (16 个) | ~80 MB | DirectML/onnxruntime/opencv_world 是大头 |
| numpy + opencv-python-headless | ~45 MB | .pyd + .dll |
| narutomobile 资源 | 27 MB | 786 PNG + merged.json |
| Pillow + mss + psutil + pywin32 | ~10 MB | 小头 |
| 项目 Python 代码 | ~400 KB | 几十个 .py 文件 |

**预估**: 单文件 exe **~200-250 MB**，安装包 **~120 MB**（压缩后）

### 1.2 关键风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| Python 3.14 太新，PyInstaller 兼容性 | 中 | 已验证 PyInstaller 6.20 支持 3.14；如失败降级到 3.12 venv |
| maafw DLLs 无法自动收集 | 高 | 手动写 `binaries` 配置到 .spec |
| PySide6 Qt plugins 缺失 | 中 | `--collect-plugins PySide6` |
| 打包后 `__file__` 路径变化 | 中 | 用 `sys._MEIPASS` + 环境变量双层 fallback |
| 打包后 maafw ADB 自动发现失效 | 低 | maafw 调用 `Toolkit.find_adb_devices()` 不依赖项目路径 |

---

## 二、先决条件：路径计算改造

**问题**: 开发时 `Path(__file__).resolve().parent` 指向项目根目录；打包后指向 `_MEIPASS`（临时解压目录），但 `config/` 和 `logs/` 应该在 exe 旁边。

### 2.1 新增 `core/app_paths.py`

```python
"""应用路径工具——区分开发模式和打包模式。"""
import sys
from pathlib import Path


def get_app_root() -> Path:
    """返回应用根目录。

    开发模式: pyproject.toml 所在目录
    打包模式: 可执行文件所在目录（exe 旁边）
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后
        return Path(sys.executable).resolve().parent
    # 开发模式：向上查找到 pyproject.toml
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        if (candidate / "pyproject.toml").exists():
            return candidate
        candidate = candidate.parent
    # fallback: 当前工作目录
    return Path.cwd()


def get_resource_root() -> Path:
    """返回资源目录（模板 + pipeline JSON）。

    PyInstaller 把资源解压到 sys._MEIPASS，开发时就是项目根目录。
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return get_app_root()
```

### 2.2 修改 `main.py` 的 PROJECT_ROOT

```python
# 旧:
# PROJECT_ROOT = Path(__file__).resolve().parent

# 新:
from core.app_paths import get_app_root, get_resource_root
PROJECT_ROOT = get_app_root()
RESOURCE_ROOT = get_resource_root()
```

### 2.3 涉及的文件（大约 12 处）

所有用 `project_root` 参数的地方都改为从 `ConfigManager.project_root` 拿，ConfigManager 初始化时自动用 `get_app_root()`。

---

## 三、PyInstaller 打包方案

### 3.1 目录结构（打包后）

```
火影自动日常/
├── NarutoAutoDaily.exe           # 单文件入口
├── config/                       # ★ 外置，用户可编辑
│   ├── app_config.yaml
│   └── task_registry.yaml
├── logs/                         # ★ 外置，运行时生成
├── maafw_data/                   # maafw 缓存（外置，避免每次解压 80MB）
│   └── log/
└── 启动火影日常.lnk              # 快捷方式（可选，安装包提供）
```

`resources/narutomobile/` 和项目代码全部打包进 exe，运行时自动解压到临时目录（`_MEIPASS`）。

### 3.2 `.spec` 文件

创建 `d:\火影自动日常\NarutoAutoDaily.spec`：

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for NarutoAutoDaily — 火影自动日常桌面应用。"""

import sys
from pathlib import Path

# ---- 项目路径 ----
PROJECT = Path(__file__).resolve().parent  # d:/火影自动日常/
MAAF_DLL = Path(maa.__file__).resolve().parent / "bin"  # maafw DLLs
MAAFAGENT_DLL = Path(maaagentbinary.__file__).resolve().parent / "bin"  # MaaAgent DLLs

a = Analysis(
    # ---- 入口 ----
    ["main.py"],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[
        # 项目资源 — 打包进 exe
        ("resources/narutomobile", "resources/narutomobile"),
        ("resources/templates", "resources/templates"),
        ("schemes", "schemes"),
    ],
    hiddenimports=[
        # PySide6 — 关键：避免 GUI 启动报错
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        # maafw 子模块
        "maa.controller",
        "maa.resource",
        "maa.tasker",
        "maa.toolkit",
        "maa.context",
        "maa.custom_action",
        "maa.custom_recognition",
        "maa.event_sink",
        "maa.pipeline",
        "maa.job",
        "maa.library",
        "maa.buffer",
        "maa.define",
        # maafw_bridge
        "maafw_bridge",
        "maafw_bridge.tasker",
        "maafw_bridge.event_sink",
        "maafw_bridge.resource",
        "maafw_bridge.task_mapping",
        "maafw_bridge.custom_actions",
        "maafw_bridge.pipeline_overrides",
        # 项目模块（PyInstaller 有时找不到动态 import 的模块）
        "core.config_manager",
        "core.base_task",
        "core.scheduler",
        "core.logger",
        "core.state_machine",
        "core.screenshot_manager",
        "core.window_manager",
        "device.adb_client",
        "device.types",
        "recovery.recovery_manager",
        "recovery.retry_manager",
        "state.game_state",
        "state_machine.game_state_machine",
        "tasks.assembly",
        "tasks.common_actions",
        "tasks.task_engine",
        "tasks.task_engine_maafw",
        "tasks.mail_task",
        "tasks.daily_signin_task",
        "tasks.liveness_task",
        "tasks.group_signin_task",
        "tasks.weekly_signin_task",
        "tasks.monthly_signin_task",
        "tasks.recruit_task",
        "tasks.activity_task",
        "tasks.navigator",
        "tasks.pipeline_runner",
        "recognition.template_matcher",
        "recognizer.page_recognizer",
        "logging_ext",
        "logging_ext.run_context",
        # UI
        "ui.main_window",
        "ui.run_worker",
        "ui.run_worker_maafw",
        "ui.control_panel",
        "ui.status_panel",
        "ui.task_panel",
        "ui.log_panel",
        "ui.qt_log_handler",
        "ui.config_dialog",
        "ui.scheme_manager",
        "ui.resource_status_panel",
        # 常见遗漏
        "cv2",
        "numpy",
        "PIL",
        "yaml",
        "loguru",
        "pydantic",
        "mss",
        "psutil",
        "win32api",
        "win32con",
        "win32gui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不需要的 Qt 模块
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtBluetooth",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtXml",
        "PySide6.QtHelp",
        "PySide6.QtDesigner",
        "PySide6.QtUiTools",
        # 不需要的 Python 标准库模块
        "tkinter",
        "tcl",
        "tcl8",
        "tcl8.6",
        "curses",
        "email",
        "http",
        "xmlrpc",
        "pydoc",
        "distutils",
        "lib2to3",
    ],
    ignore_warnings=False,
)

# ---- 手动收集 maafw DLLs ----
for dll in sorted(MAAF_DLL.glob("*.dll")):
    a.binaries += [(dll.name, str(dll), "BINARY")]

# MaaAgentBinary DLLs（如果有）
if MAAFAGENT_DLL.exists():
    for dll in sorted(MAAFAGENT_DLL.glob("*.dll")):
        a.binaries += [(dll.name, str(dll), "BINARY")]

# ---- Qt5/Qt6 platform plugins ----
# PyInstaller 通常能自动收集，但显式指定更安全
a.datas += [
    # maafw 不需要打包进 _MEIPASS 的资源（它会自己从 maafw_data 目录读）
    # 但 merged.json 在 resources/narutomobile/pipeline/ 里已包含
]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NarutoAutoDaily",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # UPX 压缩（进一步减小体积）
    upx_exclude=[
        "*.dll",                  # 不压缩 DLL（可能破坏数字签名）
        "python*.dll",
    ],
    runtime_tmpdir=None,
    console=True,                 # 开发版保留控制台（看日志），发布版改 False
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="resources/icons/app.ico" if (PROJECT / "resources/icons/app.ico").exists() else None,
)
```

### 3.3 打包命令

```bash
# 第一步：生成 .spec（如果还没写）
# pyi-makespec --windowed --name NarutoAutoDaily main.py

# 第二步：用自定义 .spec 打包
cd d:/火影自动日常
pyinstaller --clean NarutoAutoDaily.spec

# 输出:
# dist/NarutoAutoDaily.exe  (~200-250 MB)

# 第三步：测试
dist/NarutoAutoDaily.exe --gui
```

### 3.4 体积优化技巧

```bash
# 1. 用 UPX 压缩（.spec 里 upx=True），可减小 20-30%
# 2. 去掉无用的 Qt 模块（excludes 里已列），省 ~40 MB
# 3. 去掉 tkinter/curses/email 等标准库，省 ~15 MB
# 4. exclude 掉 maafw 不需要的 DLL（按需调整）:
#    - DirectML.dll (如不用 GPU 推理可删除，省 ~10MB)
#    - onnxruntime_maa.dll (如不用 PaddleOCR 可删除，省 ~15MB)
#    - opencv_world4_maa.dll (maafw 核心依赖，不能删)

# 优化后预估: 180-200 MB
```

---

## 四、Nuitka 进阶方案（后续优化）

PyInstaller 工作稳定后再切换到 Nuitka：

### 4.1 命令

```bash
pip install nuitka

cd d:/火影自动日常
python -m nuitka --standalone --windows-console-mode=disable \
    --enable-plugin=pyside6 \
    --include-data-dir=resources=resources \
    --include-data-dir=schemes=schemes \
    --include-package=maafw_bridge \
    --include-package=core \
    --include-package=tasks \
    --include-package=ui \
    --include-package=device \
    --include-package=recovery \
    --include-package=state \
    --include-package=state_machine \
    --include-package=recognition \
    --include-package=recognizer \
    --output-dir=nuitka_build \
    --assume-yes-for-downloads \
    main.py
```

### 4.2 Nuitka vs PyInstaller

| 维度 | PyInstaller | Nuitka |
|------|------------|--------|
| 打包速度 | 1-3 分钟 | 10-30 分钟（首次编译） |
| exe 大小 | 200-250 MB | 150-200 MB |
| 启动速度 | 3-8 秒（解压） | 1-3 秒 |
| 反编译难度 | 容易（.pyc） | 困难（C 编译） |
| 兼容性 | 广泛 | 部分包不兼容 |

**推荐**: 开发阶段用 PyInstaller（快速迭代），正式发布切 Nuitka。

---

## 五、安装包制作

### 5.1 NSIS 方案（推荐）

安装 [NSIS](https://nsis.sourceforge.io/)，创建 `installer/setup.nsi`：

```nsis
!define PRODUCT_NAME "火影自动日常"
!define PRODUCT_VERSION "0.7.0"
!define PRODUCT_PUBLISHER "naruto-auto-daily contributors"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "火影自动日常_Setup_${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES\NarutoAutoDaily"
RequestExecutionLevel admin

Section "Install"
    SetOutPath "$INSTDIR"

    # 主程序
    File "dist\NarutoAutoDaily.exe"

    # 配置文件（空的默认配置，首次运行自动生成）
    CreateDirectory "$INSTDIR\config"
    File /r "config\*.yaml"

    # 日志目录
    CreateDirectory "$INSTDIR\logs"

    # maafw 数据目录
    CreateDirectory "$INSTDIR\maafw_data"

    # 快捷方式
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\NarutoAutoDaily.exe" "--gui"
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\NarutoAutoDaily.exe" "--gui"
SectionEnd
```

### 5.2 安装后的目录结构

```
C:\Program Files\NarutoAutoDaily\
├── NarutoAutoDaily.exe
├── config/
│   ├── app_config.yaml           # 用户编辑配置
│   └── task_registry.yaml
├── logs/                         # 运行时日志
├── maafw_data/                   # maafw 缓存
└── uninstall.exe
```

---

## 六、自动构建（GitHub Actions）

```yaml
# .github/workflows/build.yml
name: Build Windows EXE

on:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"     # 用 3.12，兼容性最好

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build EXE
        run: |
          python -c "import maa; import maaagentbinary"  # 确保 maafw 已装
          pyinstaller --clean NarutoAutoDaily.spec

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: NarutoAutoDaily-${{ github.ref_name }}
          path: dist/NarutoAutoDaily.exe
```

---

## 七、实施步骤

| 步骤 | 内容 | 预估时间 |
|------|------|---------|
| **Step 1** | 新增 `core/app_paths.py`，修改 `main.py` PROJECT_ROOT 计算 | 30 分钟 |
| **Step 2** | 验证所有模块的 import 在打包环境可用（`--check` 增强） | 15 分钟 |
| **Step 3** | 写 `NarutoAutoDaily.spec`，第一次打包尝试 | 30 分钟 |
| **Step 4** | 解决 PyInstaller 报错（缺失 DLL/hidden import/数据文件） | 1-2 小时 |
| **Step 5** | 打包成功的 exe 在真机上验证：启动、连 ADB、跑任务 | 30 分钟 |
| **Step 6** | volume 优化（excludes + UPX） | 30 分钟 |
| **Step 7** | 创建应用图标（`.ico`），写 NSIS 安装脚本 | 1 小时 |
| **Step 8** | GitHub Actions 自动构建 | 30 分钟 |

**总计**: 3-5 小时可出第一个可用安装包。

---

## 八、关键注意事项

### 8.1 maafw 的 Toolkit.init_option

```python
# 当前代码:
Toolkit.init_option("./maafw_data", {"logging": True})

# 打包后必须用绝对路径:
from core.app_paths import get_app_root
maafw_data = get_app_root() / "maafw_data"
maafw_data.mkdir(parents=True, exist_ok=True)
Toolkit.init_option(str(maafw_data), {"logging": True})
```

### 8.2 配置外置

打包后 `config/app_config.yaml` 不应该在 `_MEIPASS` 里（只读），而应该从 exe 旁边读取。首次运行如果 exe 旁边没有 config/，自动复制默认配置过去。

### 8.3 ADB 不打包

ADB 不打包进 exe，而是：
- 优先读取用户 `app_config.yaml` 中配置的 `adb_path`
- 如果没配，自动搜索常见路径：
  - MuMu 模拟器自带的 `adb.exe`
  - `C:\Program Files (x86)\MuMu Player\*`
  - `D:\LenovoSoftstore\软件\MuMuPlayer-12.0\nx_main\adb.exe`

### 8.4 控制台窗口

```python
# .spec 中:
console=True    # 开发版：显示控制台（方便看日志）
console=False   # 发布版：无控制台，纯 GUI
```

如果用 `console=False`，需要把所有 `print()` 改为 `logger.info()`，否则用户看不到输出。

---

## 九、验收标准

- [ ] 双击 `NarutoAutoDaily.exe` → GUI 正常弹出
- [ ] 日志面板有输出，不白屏/不崩溃
- [ ] 连接 ADB 成功（MuMu 模拟器运行中）
- [ ] 跑 `mail` 任务成功
- [ ] config/app_config.yaml 编辑后重启生效
- [ ] 安装包能在新电脑上安装并运行（不装 Python）

---

## 十、风险和缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| Python 3.14 + PyInstaller 不兼容 | 中 | 降级到 3.12 venv 打包 |
| PySide6 打包缺 Qt plugins | 高 | `--collect-plugins PySide6` + 手动验 |
| maafw DLLs 缺失 | 高 | .spec 中 `binaries` 手动枚举所有 DLL |
| onnxruntime/DirectML 太大 | 中 | 可选 exclude（不用 OCR 可删 onnxruntime）|
| 打包后路径错误 | 中 | `app_paths.py` 统一处理 |
| exe 太大用户不接受 | 低 | UPX 压缩 + exclude 无用模块 → ~180 MB |
