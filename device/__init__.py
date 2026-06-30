"""device package · Phase 2 设备控制层。

包含:
    types        — ActionResult 数据类
    adb_client   — ADBClient(ADB 子进程封装)

Phase 2 仅交付 ADBClient。Phase 3+ 才会扩展到其它设备后端。
"""

__all__ = ["adb_client", "types"]
__version__ = "0.2.0"