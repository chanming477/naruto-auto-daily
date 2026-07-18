"""core.screenshot_manager — 窗口截图 → numpy.ndarray。

设计要点：
- 两个后端：
    1. ``win32_print_window`` —— 通过 Win32 PrintWindow + PW_RENDERFULLCONTENT，
       对 GPU 加速窗口（Qt / Electron / DirectX 渲染）兼容性好。
    2. ``mss_full_screen``  —— 截整个桌面，按窗口 Rect 裁剪，作为 PrintWindow
       在某些奇葩窗口上失败的兜底方案。
- 输出统一为 ``numpy.ndarray``，shape=(H, W, 3)，dtype=uint8，BGR 顺序（与 OpenCV 一致）。
- 支持 to_grayscale 与 ROI 裁剪；
- 截图为空 / PrintWindow 返回 0 时按 max_empty_retries 重试，每次间隔 retry_delay_ms；
  重试用尽仍失败返回 None，调用方据此判断「真失败」而不是「拿到一张黑屏」。
- GDI 资源（DC / Bitmap）严格在 try / finally 中释放，避免异常路径泄漏。
- 平台检查延后到 __init__，让模块本身可以被 import 而不阻塞跨平台 IDE / 测试。

公开 API：
    ScreenshotManager(window_manager: WindowManager, config: ScreenshotConfig,
                      project_root: Path)
        .capture(target: WindowInfo | None = None) -> np.ndarray | None
        .capture_gray(target=None) -> np.ndarray | None
        .capture_stable(target=None, *, n=2, interval_ms=200, threshold=0.98) -> np.ndarray | None
        .capture_and_save(name, target=None, save_dir=None) -> ScreenshotResult | None
        .crop(image, x, y, w, h) -> np.ndarray | None
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

# ------------------------------------------------------------
# 平台检查延后：模块 import 时不抛错，只标记不可用。
# 这让 main.py 在非 Windows 平台也能 from core.screenshot_manager import ...
# ------------------------------------------------------------
_PLATFORM_UNAVAILABLE: ImportError | None = None
if sys.platform != "win32":
    _PLATFORM_UNAVAILABLE = ImportError(
        "ScreenshotManager is only available on Windows."
    )
else:
    try:
        import ctypes
        from ctypes import wintypes  # noqa: F401  (公开符号位置)

        import win32con  # type: ignore[import-not-found]
        import win32gui  # type: ignore[import-not-found]
        import win32ui  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
        import mss  # type: ignore[import-not-found]
    except ImportError as exc:  # pywin32 / Pillow / mss 缺失
        _PLATFORM_UNAVAILABLE = exc

from core.config_manager import ScreenshotConfig
from core.window_manager import WindowInfo, WindowManager

__all__ = ["ScreenshotManager", "ScreenshotResult"]

# PrintWindow flags
_PW_CLIENTONLY = 0x00000001
_PW_RENDERFULLCONTENT = 0x00000002


@dataclass(frozen=True)
class ScreenshotResult:
    """截图产物（一张图 + 一条元信息）。"""

    image: np.ndarray  # shape=(H, W, 3) BGR uint8 or (H, W) gray uint8
    width: int
    height: int
    backend: str
    hwnd: int
    saved_path: Path | None = None

    @property
    def is_empty(self) -> bool:
        return self.image is None or self.image.size == 0


# ============================================================
# Backend: win32 PrintWindow
# ============================================================


def _capture_print_window(hwnd: int) -> np.ndarray | None:
    """通过 PrintWindow 抓取指定窗口的位图（BGR numpy）。

    失败返回 ``None``，包括：
        - hwnd 无效 / 窗口尺寸不合法
        - GetWindowDC / CreateCompatibleBitmap 失败
        - 两次 PrintWindow（含 PW_RENDERFULLCONTENT fallback）都返回 0
        - 任何中间异常
    GDI 资源始终在 finally 中释放。
    """
    if _PLATFORM_UNAVAILABLE is not None:
        return None
    if not win32gui.IsWindow(hwnd):
        return None

    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except win32gui.error:  # type: ignore[attr-defined]
        return None
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    hwnd_dc = 0
    src_dc: Any = None
    mem_dc: Any = None
    bmp: Any = None
    bmp_handle = 0
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None
        src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        mem_dc = src_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(src_dc, width, height)
        mem_dc.SelectObject(bmp)

        # 关键兼容性：PW_RENDERFULLCONTENT 让硬件加速窗口也能被截到。
        # 第一次失败再用 flag=0 退化一次。
        result = ctypes.windll.user32.PrintWindow(
            hwnd, mem_dc.GetSafeHdc(), _PW_RENDERFULLCONTENT)
        if result == 0:
            result = ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 0)

        if result == 0:
            # P0-BUG-02: 两次 PrintWindow 都返回 0,记录为 WARNING(原 debug 静默),
            # 明确告诉调用方这次截不到图(dwm blocked / 窗口 GPU 不可读)。
            # 注意:flag=0 退化版的成功返回也可能是「不完整」(对 GPU 加速窗口),
            # 调用方应使用 capture_stable 做稳定性校验。
            logger.warning(
                "PrintWindow both attempts failed for hwnd={} ({}); "
                "returning None (image would be unreliable, see P0-BUG-02)",
                hwnd, "DWM may block GPU-rendered content",
            )
            return None

        bmpinfo = bmp.GetInfo()
        bmpstr = bmp.GetBitmapBits(True)
        # PIL 解码确保颜色通道顺序正确（top-down vs bottom-up）
        img_rgba = Image.frombuffer(
            "RGBA",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRA",
            0,
            1,
        )
        img = np.asarray(img_rgba)[:, :, :3]  # drop alpha -> BGR
        return np.ascontiguousarray(img)
    except Exception as exc:
        logger.warning("PrintWindow exception for hwnd={}: {}", hwnd, exc)
        return None
    finally:
        # GDI 清理（无论成功失败）
        if bmp is not None:
            try:
                bmp_handle = bmp.GetHandle()
            except Exception:
                bmp_handle = 0
        if bmp_handle:
            try:
                win32gui.DeleteObject(bmp_handle)
            except Exception:
                pass
        if mem_dc is not None:
            try:
                mem_dc.DeleteDC()
            except Exception:
                pass
        if src_dc is not None:
            try:
                src_dc.DeleteDC()
            except Exception:
                pass
        if hwnd_dc:
            try:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                pass


# ============================================================
# Backend: mss full screen + crop
# ============================================================


def _capture_mss_full_screen(rect: tuple[int, int, int, int]) -> np.ndarray | None:
    """截整个屏幕并按窗口 rect 裁剪，返回 BGR numpy。失败返回 None。"""
    if _PLATFORM_UNAVAILABLE is not None:
        return None
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None

    try:
        with mss.mss() as sct:
            monitor = {"left": int(left), "top": int(top),
                       "width": int(width), "height": int(height)}
            raw = sct.grab(monitor)
            arr = np.asarray(raw)[:, :, :3]  # drop alpha -> BGR
            return np.ascontiguousarray(arr)
    except Exception as exc:
        logger.warning("mss capture exception: {}", exc)
        return None


# ============================================================
# Manager
# ============================================================


class ScreenshotManager:
    """封装两种截图后端的统一入口。"""

    def __init__(
        self,
        window_manager: WindowManager,
        config: ScreenshotConfig,
        project_root: Path,
    ) -> None:
        if _PLATFORM_UNAVAILABLE is not None:
            raise _PLATFORM_UNAVAILABLE

        self.window_manager = window_manager
        self.config = config
        self.project_root = project_root.resolve()
        self.output_dir = self.project_root / config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ----- public capture ----------------------------------------------

    def capture(self, target: WindowInfo | None = None) -> np.ndarray | None:
        """截一张图。重试由内部完成；最终失败返回 None。"""
        if target is None:
            target = self.window_manager.find_target()
        if target is None:
            logger.debug("capture skipped: no target window")
            return None
        if not target.rect.is_valid:
            logger.debug("capture skipped: target rect invalid (hwnd={})", target.hwnd)
            return None

        retries = max(1, self.config.max_empty_retries)
        delay_s = self.config.retry_delay_ms / 1000.0
        last: np.ndarray | None = None
        for attempt in range(1, retries + 1):
            arr = self._capture_once(target)
            if arr is not None and arr.size > 0 and arr.shape[0] > 0 and arr.shape[1] > 0:
                if self.config.to_grayscale:
                    arr = self._to_grayscale(arr)
                return arr
            last = arr
            logger.debug("capture attempt {}/{} empty for hwnd={}",
                         attempt, retries, target.hwnd)
            if attempt < retries:
                time.sleep(delay_s)

        # P0-BUG-02: 即便 last 不为 None(退化版的 PNG 也算「拿到了图」),
        # 只要重试用尽就明确返 None,不要把不可靠图像传出去。
        # 调用方(capture_and_save / 业务层)据此判断「真失败」而不是「拿到一张黑屏」。
        logger.warning("capture failed after {} retries for hwnd={}",
                       retries, target.hwnd)
        return None  # 统一语义: 失败 = None

    def capture_gray(self, target: WindowInfo | None = None) -> np.ndarray | None:
        img = self.capture(target)
        if img is None:
            return None
        if img.ndim == 2:
            return img
        return self._to_grayscale(img)

    def capture_stable(
        self,
        target: WindowInfo | None = None,
        *,
        n: int = 2,
        interval_ms: int = 200,
        threshold: float = 0.98,
        pixel_tolerance: int = 8,
    ) -> np.ndarray | None:
        """画面稳定性检查：连续截 n 张，相邻帧的「像素差 ≤ tolerance」比例 ≥ threshold 才算稳定。

        用法（Phase 2+）：执行动作后调用 ``capture_stable``，若返回 None 表示动画/转场
        仍在进行，任务应该继续等待或重试。Phase 1 仅暴露接口，暂无具体任务调用。

        Returns:
            稳定时返回最后一帧；不稳定或全部失败返回 None。
        """
        n = max(2, int(n))
        threshold = max(0.0, min(1.0, float(threshold)))

        prev = self.capture(target)
        if prev is None:
            return None
        for i in range(n - 1):
            time.sleep(max(0.0, interval_ms) / 1000.0)
            cur = self.capture(target)
            if cur is None:
                return None
            if not self._is_similar(prev, cur, threshold, pixel_tolerance):
                logger.debug("capture_stable: frame {}/{} not stable", i + 1, n - 1)
                return None
            prev = cur
        return prev

    def capture_and_save(
        self,
        name: str,
        target: WindowInfo | None = None,
        save_dir: Path | None = None,
    ) -> ScreenshotResult | None:
        """截图并保存到磁盘（同时返回结果对象）。"""
        if target is None:
            target = self.window_manager.find_target()
        if target is None:
            return None

        arr = self.capture(target)
        if arr is None:
            return None

        out_dir = save_dir if save_dir is not None else self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        path = out_dir / f"{safe}_{ts}.png"

        try:
            # arr 是 BGR uint8 (H,W,3)，PIL 需要 RGB → 翻转通道即可；
            # PIL 在 fromarray 阶段会自己做内存布局调整，无需 .copy()。
            rgb = arr[..., ::-1]
            Image.fromarray(rgb).save(path, format="PNG")
        except Exception as exc:  # pragma: no cover - 磁盘满 / 权限问题
            logger.error("failed to save screenshot {}: {}", path, exc)
            return ScreenshotResult(
                image=arr,
                width=int(arr.shape[1]),
                height=int(arr.shape[0]),
                backend=self.config.backend,
                hwnd=target.hwnd,
                saved_path=None,
            )

        logger.debug("screenshot saved: {} ({}x{})", path, arr.shape[1], arr.shape[0])
        return ScreenshotResult(
            image=arr,
            width=int(arr.shape[1]),
            height=int(arr.shape[0]),
            backend=self.config.backend,
            hwnd=target.hwnd,
            saved_path=path,
        )

    # ----- Phase 4 增量: 稳定性归档(failure / transitions / recovery) -------

    def save_failure(
        self,
        image: np.ndarray,
        context: str | None = None,
    ) -> Path | None:
        """归档一张失败现场截图到 ``screenshots/failure/``。

        Phase 4:任务失败时调用,把失败时刻的截图留底,便于事后排查。

        Args:
            image: BGR uint8 ndarray(shape=(H, W, 3))。None 或形状非法返 None 不抛。
            context: 可选上下文描述(任务名 / 异常类型等),会写进文件名。

        Returns:
            保存的 ``Path``;失败时 None。
        """
        return self._save_to_subdir(
            image, subdir="failure", name_prefix="failure", context=context,
        )

    def save_state_transition(
        self,
        image: np.ndarray,
        from_state: object,
        to_state: object,
    ) -> Path | None:
        """归档一次状态切换的截图到 ``screenshots/transitions/``。

        由调用方在状态切换时调用,记录切换瞬间的视觉证据。
        P2-2 (2026-07-18): 原 GameStateMachine 模块已删,改为通用接口。

        Args:
            image: BGR uint8 ndarray。
            from_state: 切换前状态(可 ``str()`` 即可)。
            to_state: 切换后状态。

        Returns:
            保存的 ``Path``;失败时 None。
        """
        ctx = f"{from_state}->{to_state}"
        return self._save_to_subdir(
            image, subdir="transitions", name_prefix="transition", context=ctx,
        )

    def save_recovery(
        self,
        image: np.ndarray,
        recovery_type: str,
        state_after: object | None = None,
    ) -> Path | None:
        """归档一次恢复成功的截图到 ``screenshots/recovery/``。

        Phase 4: ``RecoveryManager`` 4 个恢复方法成功时调用,留底恢复后的现场。

        Args:
            image: BGR uint8 ndarray。
            recovery_type: 恢复类型,如 ``"unknown"`` / ``"popup"`` / ``"loading"`` /
                ``"adb_error"`` / ``"unknown:go_home"``。
            state_after: 恢复后的状态(可 ``str()`` 即可),可选。

        Returns:
            保存的 ``Path``;失败时 None。
        """
        ctx = recovery_type if state_after is None else f"{recovery_type}:{state_after}"
        return self._save_to_subdir(
            image, subdir="recovery", name_prefix="recovery", context=ctx,
        )

    # ----- internals ---------------------------------------------------

    def _save_to_subdir(
        self,
        image: np.ndarray,
        *,
        subdir: str,
        name_prefix: str,
        context: str | None = None,
    ) -> Path | None:
        """把 ``image`` 保存到 ``output_dir/<subdir>/<name_prefix>_<ts>[_<context>].png``。

        内部统一处理:None / 空数组 / 非法 dtype 全部返 None 不抛;IO 失败返 None。
        """
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            logger.debug(
                "_save_to_subdir: invalid image (type={}, size={}), skip",
                type(image).__name__,
                getattr(image, "size", 0),
            )
            return None
        try:
            target_dir = self.output_dir / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            safe_ctx = ""
            if context:
                safe_ctx = "_" + "".join(
                    c if c.isalnum() or c in "-_." else "_" for c in str(context)
                )[:80]
            path = target_dir / f"{name_prefix}_{ts}{safe_ctx}.png"
            rgb = image[..., ::-1]  # BGR -> RGB
            Image.fromarray(rgb).save(path, format="PNG")
            logger.debug(
                "screenshot archived: {} ({}x{}, subdir={})",
                path, image.shape[1], image.shape[0], subdir,
            )
            return path
        except Exception as exc:  # pragma: no cover - 磁盘满 / 权限
            logger.warning(
                "_save_to_subdir failed (subdir={}, context={}): {}",
                subdir, context, exc,
            )
            return None

    # ----- helpers ------------------------------------------------------

    def crop(self, image: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        """对图像按 ROI 裁剪。坐标越界或 ROI 退化时返回 None。"""
        if image is None or image.size == 0:
            return None
        H, W = image.shape[:2]
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(W, x0 + max(0, int(w)))
        y1 = min(H, y0 + max(0, int(h)))
        if x1 <= x0 or y1 <= y0:
            return None
        return image[y0:y1, x0:x1].copy()

    # ----- internals ----------------------------------------------------

    def _capture_once(self, target: WindowInfo) -> np.ndarray | None:
        backend = self.config.backend
        try:
            if backend == "win32_print_window":
                return _capture_print_window(target.hwnd)
            elif backend == "mss_full_screen":
                rect = (
                    target.rect.left,
                    target.rect.top,
                    target.rect.right,
                    target.rect.bottom,
                )
                return _capture_mss_full_screen(rect)
            else:
                logger.error("unknown screenshot backend '{}'", backend)
                return None
        except Exception as exc:  # pragma: no cover - 防御
            logger.warning("screenshot exception (backend={}, hwnd={}): {}",
                           backend, target.hwnd, exc)
            return None

    @staticmethod
    def _to_grayscale(image: np.ndarray) -> np.ndarray:
        # 0.299 R + 0.587 G + 0.114 B（输入是 BGR）
        b = image[:, :, 0].astype(np.float32)
        g = image[:, :, 1].astype(np.float32)
        r = image[:, :, 2].astype(np.float32)
        gray = 0.114 * b + 0.587 * g + 0.299 * r
        return np.clip(gray, 0, 255).astype(np.uint8)

    @staticmethod
    def _is_similar(
        a: np.ndarray,
        b: np.ndarray,
        similar_ratio_threshold: float,
        pixel_tolerance: int,
    ) -> bool:
        """比较两帧是否近似。形状不一致直接返回 False。"""
        if a.shape != b.shape:
            return False
        if a.ndim == 3:
            diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
        else:
            diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
        similar = float((diff <= pixel_tolerance).sum()) / float(diff.size)
        return similar >= similar_ratio_threshold