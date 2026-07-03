"""core.app_paths — App paths resolver.

区分两种运行模式:

- **源码模式**(``python main.py``)``:`` 两个根都解析到项目根。
- **PyInstaller frozen 模式**(``main.exe``)``:``

  * ``get_resource_root()`` → ``sys._MEIPASS``(只读,资源解压目录)
  * ``get_user_data_dir()`` → ``sys.executable`` 所在目录(可写,exe 旁边)

调用方按用途选函数,不要混用:
- 模板、scheme 等**只读**资源 → ``get_resource_root()``
- config、screenshots、logs 等**可写**数据 → ``get_user_data_dir()``
"""
from __future__ import annotations

import sys
from pathlib import Path

# core/app_paths.py 的上一级是 core/ 目录,再上一级才是项目根。
_SRC_ROOT: Path = Path(__file__).resolve().parent.parent


def get_resource_root() -> Path:
    """只读资源根目录(schemes/、resources/templates/、pyz 内嵌资源)。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 解压出来的临时目录
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return _SRC_ROOT


def get_user_data_dir() -> Path:
    """可写数据根目录(config/、screenshots/、logs/)。

    frozen 模式下放到 exe 旁边,方便用户备份/迁移;
    exe 目录在 Windows 上通常需要管理员权限的 Program Files 之外。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _SRC_ROOT
