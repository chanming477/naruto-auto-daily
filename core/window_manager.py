"""core.window_manager — Win32 窗口查找 / 激活 / 几何信息。

设计要点：
- 仅 Windows 平台可用；平台检查延后到 ``__init__`` 与方法调用，
  让模块本身可以被 import 而不阻塞跨平台 IDE / 测试。
- 使用 pywin32 + ctypes；不依赖 pyautogui / pywinauto 等高层库，避免隐藏行为。
- 职责清晰：只负责「找到窗口」和「窗口的几何 / 状态」，不负责截图
  （截图由 ScreenshotManager 调用 PrintWindow 完成）。
- 进程级过滤通过 psutil 拉进程名；若 psutil 不存在则降级为「进程名 = ''」。

公开 API：
    WindowManager(profile: WindowProfile)
        .find_target() -> WindowInfo | None
        .list_visible() -> list[WindowInfo]
        .activate(hwnd) -> bool
        .close(hwnd) -> bool
        .get_rect(hwnd) -> Rect | None
        .wait_for_target(timeout_sec=10, poll_interval_sec=0.5) -> WindowInfo | None
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

# ------------------------------------------------------------
# 平台检查延后：模块 import 时不抛错，只在 __init__ / 方法调用时检查
# ------------------------------------------------------------
_PLATFORM_UNAVAILABLE: ImportError | None = None
if sys.platform != "win32":
    _PLATFORM_UNAVAILABLE = ImportError(
        "WindowManager is only available on Windows. "
        "Use a stub / alternative backend on other platforms."
    )
else:
    try:
        import ctypes
        from ctypes import wintypes

        import win32con  # type: ignore[import-not-found]
        import win32gui  # type: ignore[import-not-found]
        import win32process  # type: ignore[import-not-found]
    except ImportError as exc:
        _PLATFORM_UNAVAILABLE = exc

    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        psutil = None  # type: ignore[assignment]

from core.config_manager import WindowProfile

__all__ = ["WindowManager", "WindowInfo", "Rect"]


@dataclass(frozen=True)
class Rect:
    """窗口矩形（屏幕物理像素）。

    ``is_valid`` 提供明确的「失败信号」：当 ``GetWindowRect`` 异常或返回退化值
    时，使用 ``None`` 代替 Rect，并在 ``WindowInfo`` 列表里直接跳过该窗口，
    避免下游拿到一个 width=0 height=0 的「假成功」Rect。
    """

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def is_valid(self) -> bool:
        """真正的窗口矩形一定有正宽度和正高度。"""
        return self.right > self.left and self.bottom > self.top


@dataclass(frozen=True)
class WindowInfo:
    """一个目标窗口的快照信息。"""

    hwnd: int
    title: str
    class_name: str
    pid: int
    process_name: str
    is_visible: bool
    is_minimized: bool
    rect: Rect

    def __str__(self) -> str:  # pragma: no cover - human only
        return (
            f"WindowInfo(hwnd={self.hwnd} pid={self.pid} proc='{self.process_name}' "
            f"title='{self.title}' class='{self.class_name}' "
            f"rect={self.rect.width}x{self.rect.height} visible={self.is_visible} "
            f"minimized={self.is_minimized})"
        )


# ============================================================
# ctypes helpers
# ============================================================


def _require_windows() -> None:
    if _PLATFORM_UNAVAILABLE is not None:
        raise _PLATFORM_UNAVAILABLE


def _is_window_visible(hwnd: int) -> bool:
    return bool(win32gui.IsWindowVisible(hwnd))


def _is_window_minimized(hwnd: int) -> bool:
    return bool(win32gui.IsIconic(hwnd))


def _get_window_rect(hwnd: int) -> Rect | None:
    """失败返回 None；退化矩形（width/height <= 0）也返回 None。"""
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
    except win32gui.error:  # type: ignore[attr-defined]
        return None
    rect = Rect(int(l), int(t), int(r), int(b))
    return rect if rect.is_valid else None


def _get_window_text(hwnd: int) -> str:
    try:
        return win32gui.GetWindowText(hwnd)
    except win32gui.error:  # type: ignore[attr-defined]
        return ""


def _get_class_name(hwnd: int) -> str:
    try:
        return win32gui.GetClassName(hwnd)
    except win32gui.error:  # type: ignore[attr-defined]
        return ""


def _get_pid(hwnd: int) -> int:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid)
    except Exception:  # pragma: no cover - 极少见，进程句柄瞬间失效
        return 0


def _process_name_for_pid(pid: int) -> str:
    if pid <= 0 or psutil is None:
        return ""
    try:
        return psutil.Process(pid).name()
    except Exception:  # NoSuchProcess / AccessDenied / 任意底层异常
        return ""


# ============================================================
# Enumeration
# ============================================================


def _enum_top_level_windows() -> list[int]:
    """枚举所有顶层窗口的 hwnd 列表。"""
    result: list[int] = []

    def _cb(hwnd: int, _ctx: Any) -> bool:
        # 仅顶层窗口（无 owner）
        owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
        if owner == 0:
            result.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    return result


# ============================================================
# Manager
# ============================================================


class WindowManager:
    """基于当前 WindowProfile 的窗口管理。"""

    def __init__(self, profile: WindowProfile) -> None:
        _require_windows()
        self.profile = profile

    # ----- discovery ----------------------------------------------------

    def list_visible(self) -> list[WindowInfo]:
        """枚举所有顶层窗口，过滤掉不可见 / 已最小化 / 退化矩形的，转换为 WindowInfo 列表。"""
        out: list[WindowInfo] = []
        for hwnd in _enum_top_level_windows():
            info = self._snapshot(hwnd)
            if info is None:
                continue
            if self.profile.require_visible and not info.is_visible:
                continue
            if self.profile.require_not_minimized and info.is_minimized:
                continue
            out.append(info)
        return out

    def find_target(self) -> WindowInfo | None:
        """按当前 profile 匹配目标窗口。"""
        candidates = self.list_visible()
        if self.profile.match_mode == "any":
            return candidates[0] if candidates else None

        for info in candidates:
            if self._matches(info):
                return info

        # 兜底：放宽到「忽略最小化要求」再扫一次（用户切窗口经常触发最小化）
        if self.profile.require_not_minimized:
            for hwnd in _enum_top_level_windows():
                snap = self._snapshot(hwnd)
                if snap is None:
                    continue
                if not snap.is_visible:
                    continue
                if self._matches(snap):
                    return snap
        return None

    def wait_for_target(
        self,
        timeout_sec: float = 10.0,
        poll_interval_sec: float = 0.5,
    ) -> WindowInfo | None:
        """轮询直到匹配到目标窗口；超时返回 None。"""
        deadline = time.monotonic() + max(0.0, timeout_sec)
        while True:
            info = self.find_target()
            if info is not None:
                return info
            if time.monotonic() >= deadline:
                return None
            time.sleep(max(0.05, poll_interval_sec))

    # ----- actions ------------------------------------------------------

    def activate(self, hwnd: int) -> bool:
        """把窗口拉到前台。返回是否成功。

        Windows 前台窗口规则严格：只有前台进程能把自己拉到最前。
        用 AttachThreadInput 技巧可以提高成功率，失败时 fallback 到裸调用。
        任何路径下都会检查 SetForegroundWindow 返回值并记录。
        """
        _require_windows()
        if not win32gui.IsWindow(hwnd):
            return False
        try:
            # 若最小化则先恢复
            if _is_window_minimized(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            # Windows 对前台窗口有限制：前台进程才允许把自己拉到最前。
            # 借用 AttachThreadInput 技巧可以提高成功率（不强制，失败也无伤）。
            fg_hwnd = win32gui.GetForegroundWindow()
            fg_thread = win32process.GetWindowThreadProcessId(fg_hwnd)[0]
            target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
            cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            attached = False
            if fg_thread != cur_thread:
                ctypes.windll.user32.AttachThreadInput(fg_thread, cur_thread, True)
                attached = True
            if target_thread != cur_thread:
                ctypes.windll.user32.AttachThreadInput(target_thread, cur_thread, True)
                attached = True

            try:
                ok_fg = bool(win32gui.SetForegroundWindow(hwnd))
                if not ok_fg:
                    logger.warning(
                        "SetForegroundWindow returned False for hwnd={} (foreground steal rejected)",
                        hwnd,
                    )
            except Exception as exc:  # pragma: no cover
                logger.warning("SetForegroundWindow raised for hwnd={}: {}", hwnd, exc)
                ok_fg = False

            try:
                win32gui.SetFocus(hwnd)
            except Exception:  # pragma: no cover
                pass

            if attached:
                try:
                    ctypes.windll.user32.AttachThreadInput(fg_thread, cur_thread, False)
                    ctypes.windll.user32.AttachThreadInput(target_thread, cur_thread, False)
                except Exception:
                    pass

            # Fallback：若 AttachThreadInput 路径失败，再尝试一次裸调用。
            if not ok_fg:
                try:
                    fallback_ok = bool(win32gui.SetForegroundWindow(hwnd))
                    if fallback_ok:
                        ok_fg = True
                except Exception:
                    pass

            return ok_fg
        except Exception as exc:  # pragma: no cover - 极少见
            logger.warning("activate(hwnd={}) failed: {}", hwnd, exc)
            return False

    def close(self, hwnd: int) -> bool:
        """向窗口发送 WM_CLOSE。"""
        _require_windows()
        if not win32gui.IsWindow(hwnd):
            return False
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return True
        except Exception as exc:  # pragma: no cover
            logger.warning("close(hwnd={}) failed: {}", hwnd, exc)
            return False

    def get_rect(self, hwnd: int) -> Rect | None:
        """返回窗口矩形；hwnd 无效或 GetWindowRect 失败返回 None。"""
        _require_windows()
        return _get_window_rect(hwnd)

    # ----- internals ----------------------------------------------------

    def _snapshot(self, hwnd: int) -> WindowInfo | None:
        if not win32gui.IsWindow(hwnd):
            return None
        rect = _get_window_rect(hwnd)
        if rect is None:  # 退化或异常 → 跳过该窗口
            return None
        title = _get_window_text(hwnd)
        class_name = _get_class_name(hwnd)
        pid = _get_pid(hwnd)
        proc = _process_name_for_pid(pid)
        return WindowInfo(
            hwnd=int(hwnd),
            title=title,
            class_name=class_name,
            pid=pid,
            process_name=proc,
            is_visible=_is_window_visible(hwnd),
            is_minimized=_is_window_minimized(hwnd),
            rect=rect,
        )

    def _matches(self, info: WindowInfo) -> bool:
        # 进程黑名单
        if info.process_name and info.process_name in self.profile.process_blacklist:
            return False
        # 进程白名单（仅当配置了非空名单时生效）
        if self.profile.process_whitelist:
            if not info.process_name or info.process_name not in self.profile.process_whitelist:
                return False

        mode = self.profile.match_mode
        if mode == "title_contains":
            if not self.profile.match_keywords:
                return False
            return any(kw in info.title for kw in self.profile.match_keywords)
        if mode == "title_equals":
            return info.title in self.profile.match_keywords
        if mode == "class_name":
            return info.class_name in self.profile.match_keywords
        if mode == "pid":
            try:
                wanted = {int(k) for k in self.profile.match_keywords}
            except ValueError:
                return False
            return info.pid in wanted
        if mode == "any":
            return True
        return False


# 为避免 IDE 报 unused import；下面这一行是为了保留 wintypes 的引用
_ = wintypes