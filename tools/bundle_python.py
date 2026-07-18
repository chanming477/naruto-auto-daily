"""tools.bundle_python — 一键构建 Agent 模式 Python 捆绑。

**用法**:
    python tools/bundle_python.py

**做了什么**:
    1. 下载 python-build-standalone 的 embeddable Python (Windows x64, Python 3.12)
    2. 解压到 ``python/`` (frontend/MFAAvalonia/python/ 会被 MFAAvalonia.exe 通过
       ``interface.json`` 的 ``agent.child_exec = "python/python.exe"`` 引用)
    3. pip install 本项目依赖 (maafw / loguru / numpy / Pillow / onnxruntime)
    4. 复制 ``agent/`` 目录到 ``python/Lib/site-packages/agent/``

**预期结果**:
    - ``frontend/MFAAvalonia/python/`` 目录约 75 MB
    - MFAAvalonia.exe 启动时自动 spawn ``python/python.exe -u agent/main.py <socket_id>``

**注意**:
    - 需要联网 (下载 ~50 MB tarball)
    - **只在 Windows x64 测试过** (Python 3.12.9)
    - Linux/macOS 不需要 Python 捆绑 (直接用系统 Python)
    - 重复执行安全: 已存在 ``python/`` 时会跳过下载,只重新安装依赖
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

# ============================================================
# 配置 (2026-07-15 P1-7 修: 仓库已 transfer,Windows 架构是 x86_64,Windows variant 是 install_only)
# ============================================================
PYTHON_VERSION = "3.12.9"
RELEASE_DATE = "20250317"
# Windows 平台固定 x86_64 (platform.machine() 在 Windows 上是 'AMD64',asset 用 'x86_64' 命名)
ARCH = "x86_64"

# python-build-standalone release URL
# 仓库: indygreg 2025 年 transfer 到 astral-sh,旧 URL 404
# variant: Windows 平台只有 install_only (没有 shared-install_only)
# + 字符在 URL 里 percent-encode 为 %2B,避免 urllib 重定向丢失
URL = (
    f"https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{RELEASE_DATE}/cpython-{PYTHON_VERSION}%2B{RELEASE_DATE}-{ARCH}-pc-windows-msvc-install_only.tar.gz"
)

# 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET = PROJECT_ROOT / "frontend" / "MFAAvalonia" / "python"

# Agent 模式需要的依赖 (跟 requirements.txt 同步,只列必须的)
DEPS = [
    "maafw==5.10.4",
    "loguru>=0.7.3",
    "numpy>=2.0",
    "Pillow>=10.0",
    "onnxruntime>=1.18",
]


# ============================================================
# 工具函数
# ============================================================
def dir_size(path: Path) -> int:
    """目录总字节数。"""
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())


def download_and_extract(url: str, target: Path) -> None:
    """下载 tarball 并解压到 target/。

    python-build-standalone 的 install_only tarball 内部根目录是 ``python/``,
    解压到 ``target/`` 会变成 ``target/python/python.exe`` (嵌套)。本函数
    先解压到临时目录,再把内层 ``python/`` 扁平化到 ``target/`` 根。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"下载 {url} ...")
    tarball = target.parent / "_python_bundler_tmp.tar.gz"
    try:
        urllib.request.urlretrieve(url, str(tarball))
    except Exception as exc:
        print(f"下载失败: {exc}", file=sys.stderr)
        if tarball.exists():
            tarball.unlink()
        raise

    _extract_and_flatten(tarball, target)


def _extract_and_flatten(tarball: Path, target: Path) -> None:
    """解压 tarball 到临时目录,把内层 ``python/`` 扁平化到 target/。

    为什么: MFAAvalonia.exe 读 ``interface.json`` 的
    ``agent.child_exec = "python/python.exe"``,工作目录是
    ``frontend/MFAAvalonia/``,所以期望 ``frontend/MFAAvalonia/python/python.exe``
    在 TARGET 根 (而不是嵌套的 ``TARGET/python/python.exe``)。
    """
    import tempfile
    print(f"解压到 {target} (扁平化内层 python/ 目录) ...")
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(tmp)
        # tarball 根有 "python/" 子目录,内含 python.exe + Lib + DLLs 等
        inner = Path(tmp) / "python"
        if not inner.is_dir():
            raise RuntimeError(
                f"tarball 根目录没有 python/ 子目录,结构异常: {tarball}"
            )
        for f in inner.iterdir():
            dest = target / f.name
            if dest.exists():
                # TARGET 已有内容 (--force-redownload 触发),覆盖
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(f), str(dest))
    tarball.unlink()
    print(f"[OK] 捆绑完成: {target} ({dir_size(target) / 1024 / 1024:.0f} MB)")


def install_deps(pip: Path) -> None:
    """pip install 依赖到捆绑的 Python。

    **注意**: 2026-07-15 P1-7 修 — 去掉 ``--no-deps`` 标志。
    之前用 --no-deps 是为了"严格控制依赖",但实际漏装了:
        - ``maa.define`` 依赖 ``strenum`` (PyPI 包,不是 stdlib 的 enum.StrEnum)
        - ``loguru`` 依赖 ``win32_setctime`` (Windows 专属)
    漏装这些导致脚本 import 失败。让 pip 自动处理依赖更安全。
    """
    print(f"安装依赖 ({len(DEPS)} 个,含 transitive 依赖) ...")
    # 一次性装全部,让 pip 解析依赖关系
    subprocess.run(
        [str(pip), "-m", "pip", "install", *DEPS, "--quiet"],
        check=True,
    )
    print("[OK] 依赖安装完成")


def copy_agent_source(project_root: Path, target: Path) -> None:
    """复制 ``agent/`` 目录到 workdir 相对路径 (跟 MaaAutoNaruto / MFAAvalonia 一致)。

    2026-07-15 P1-7 review C1 修: ``interface.json`` 的 ``agent.child_args``
    是 ``["-u", "agent/main.py"]`` (文件路径,不是 ``-m`` module 形式),
    所以 ``agent/`` 必须直接放在 workdir 下 (即 ``frontend/MFAAvalonia/agent/``),
    而不是嵌套在 ``python/Lib/site-packages/agent/``。

    Args:
        project_root: 项目根 (含 agent/ 源)
        target: python/ 捆绑目录 (``frontend/MFAAvalonia/python/``)
    """
    src = project_root / "agent"
    # 关键: agent/ 跟 python/ 同级,在 MFAAvalonia workdir 下
    # target = frontend/MFAAvalonia/python/, target.parent = frontend/MFAAvalonia/
    dest = target.parent / "agent"
    print(f"复制 {src} → {dest}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"[OK] agent/ 已复制 ({dir_size(dest) / 1024:.0f} KB)")


# ============================================================
# Main
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="构建 Agent 模式 Python 捆绑 (frontend/MFAAvalonia/python/)")
    parser.add_argument(
        "--force-redownload",
        action="store_true",
        help="删除现有 python/ 目录重新下载",
    )
    parser.add_argument(
        "--local-tarball",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "用本地 tarball 文件而不是从 GitHub 下载。"
            "例如: --local-tarball D:\\downloads\\cpython-3.12.9+20250317-x86_64-pc-windows-msvc-install_only.tar.gz"
        ),
    )
    args = parser.parse_args()

    # 平台检查
    if sys.platform != "win32":
        print(f"[WARN] 本脚本只在 Windows 测试过 (当前: {sys.platform})", file=sys.stderr)

    # 平台检查:ARCH 已 hardcode 成 x86_64,Windows-only 脚本不动态检测。
    # 如果以后要支持 macOS / Linux,改成 platform.machine() 动态检测 + 警告。

    # 1. 下载 + 解压
    if args.force_redownload and TARGET.exists():
        print(f"删除现有 {TARGET}")
        shutil.rmtree(TARGET)

    # 本地 tarball 模式: 跳过 URL 下载
    if args.local_tarball:
        tarball = args.local_tarball
        if not tarball.exists():
            print(f"[FAIL] 本地 tarball 不存在: {tarball}", file=sys.stderr)
            return 1
        print(f"使用本地 tarball: {tarball} ({tarball.stat().st_size / 1024 / 1024:.1f} MB)")
        _extract_and_flatten(tarball, TARGET)
    elif not (TARGET / "python.exe").exists():
        download_and_extract(URL, TARGET)
    else:
        print(f"已存在 {TARGET} ({dir_size(TARGET) / 1024 / 1024:.0f} MB),跳过下载")

    # 2. pip install
    pip = TARGET / "python.exe"
    install_deps(pip)

    # 3. 复制 agent/ 源
    copy_agent_source(PROJECT_ROOT, TARGET)

    # 4. 验证
    print()
    print("=== 验证 ===")
    # 注意: maafw PyPI 包 import 名是 maa (不是 maafw)
    verify_script = (
        "import maa; import loguru; import numpy; import PIL; import onnxruntime; "
        "import agent.main; print('all imports OK')"
    )
    rc = subprocess.run(
        [str(pip), "-c", verify_script],
        cwd=str(TARGET),
    ).returncode
    if rc == 0:
        print("[OK] Python 捆绑验证通过 (maafw + agent 全部 import 成功)")
    else:
        print(f"[FAIL] Python 捆绑验证失败 (rc={rc})", file=sys.stderr)
        return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
