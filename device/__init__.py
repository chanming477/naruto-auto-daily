"""device package · 设备控制层 (V2 2026-07-18)。

仅留:
    types        — ActionResult 数据类 (next_state 改 Optional[str])

P2 删 (2026-07-18):
    - adb_client  (MaaFramework 自带 ADB 绑定, 唯一引用 capture_template.py 已删)
"""

__all__ = ["types"]
__version__ = "0.7.0"
