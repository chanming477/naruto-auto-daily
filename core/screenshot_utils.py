"""core.screenshot_utils — 跨平台截图落盘工具(PIL 优先,规避 cv2.imwrite iCCP bug)。

背景:
    narutomobile 风格的 ``cv2.imwrite`` 在某些 iCCP chunks 不规范的 PNG 上会
    **静默返回 False**(不抛异常),导致 dry-run / 调试时截图"看起来保存了"
    实际磁盘上没文件。

    这个模块只放"落盘"工具函数,不改变现有 ScreenshotManager / ADBClient 接口。
    调用方在拿到 ndarray 后调 ``save_image_pil(img, path)`` 即可。

公开 API:
    save_image_pil(img: np.ndarray, path: Path | str) -> bool
        BGR ndarray → 落盘为 PNG/JPG(根据 path 后缀)。
        优先 PIL(最稳),失败回退 cv2.imwrite。
    safe_makedirs(path: Path | str) -> None
        mkdir -p 等价。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

__all__ = ["save_image_pil", "safe_makedirs"]


def safe_makedirs(path: Path | str) -> None:
    """``mkdir -p`` 等价,父目录不存在则创建。"""
    p = Path(path)
    if p.is_dir() or (p.suffix == ""):
        # 是目录路径或无后缀: 当目录创建
        target_dir = p if p.is_dir() or p.suffix == "" else p.parent
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        # 是文件路径: 创建父目录
        p.parent.mkdir(parents=True, exist_ok=True)


def save_image_pil(img: np.ndarray, path: Path | str) -> bool:
    """把 BGR ndarray 落盘为图片文件。

    优先用 PIL(支持 iCCP/PNG/JPG 等),失败回退 cv2.imwrite。

    Args:
        img: BGR uint8 ndarray, shape=(H, W, 3)。
        path: 目标文件路径。后缀决定格式(.png / .jpg / .jpeg)。

    Returns:
        True 表示成功落盘;False 表示全部失败。
    """
    if img is None or not isinstance(img, np.ndarray) or img.size == 0:
        return False
    p = Path(path)
    safe_makedirs(p.parent if p.suffix else p)
    suffix = p.suffix.lower()

    # 1) PIL 优先(BGR → RGB)
    try:
        from PIL import Image

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img.ndim == 3 and img.shape[2] == 3 else img
        pil_img = Image.fromarray(rgb)
        # 缺省 png;若 .jpg/.jpeg 走 JPEG
        if suffix in {".jpg", ".jpeg"}:
            pil_img.save(str(p), format="JPEG", quality=90)
        else:
            pil_img.save(str(p), format="PNG")
        if p.exists() and p.stat().st_size > 0:
            return True
    except Exception:
        pass

    # 2) cv2.imwrite 兜底
    try:
        ok = cv2.imwrite(str(p), img)
        if ok and p.exists() and p.stat().st_size > 0:
            return True
    except Exception:
        pass

    return False