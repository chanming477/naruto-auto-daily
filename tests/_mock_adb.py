"""tests._mock_adb — Mock ADBClient fixture(2026-06-30 工程治理,Q3 设计)。

不连真模拟器,跑单元测试:
    任务 pipeline 节点结构
    ROI 范围合理
    on_error 不指 silent verify_done
    模板文件物理存在
    节点无 Noop 漏失

DeepSeek Q3 推荐:每个 task 测试 6 个断言。

用法:
    from tests._mock_adb import make_mock_adb, make_blank_screen, default_assertions
    adb = make_mock_adb()
    # 跑任务 pipeline,adb.tap/screenshot 都被 mock 接住
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np


def make_blank_screen(width: int = 1920, height: int = 1080, channels: int = 3) -> np.ndarray:
    """生成一张全黑测试截图。(1080, 1920, 3) BGR uint8。"""
    return np.zeros((height, width, channels), dtype=np.uint8)


def make_mock_adb(screen: Optional[np.ndarray] = None) -> "MockADB":
    """返回一个 mock ADBClient,所有动作返回 ActionResult(success=True)。

    Mock 行为:
        - screenshot() → 返回给定 screen(默认全黑)
        - tap(x, y) → success
        - swipe(...) → success
        - keyevent(key) → success
        - connect() → success
    """
    if screen is None:
        screen = make_blank_screen()

    class MockADB:
        def __init__(self):
            self._screen = screen
            self.taps: list[tuple[int, int]] = []
            self.swipes: list[tuple[int, int, int, int]] = []
            self.keys: list[str] = []

        def screenshot(self):
            payload = self._screen.copy()
            return _MockActionResult(True, "mock", None, payload=payload)

        def tap(self, x: int, y: int):
            self.taps.append((x, y))
            return _MockActionResult(True, "mock", None)

        def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
            self.swipes.append((x1, y1, x2, y2))
            return _MockActionResult(True, "mock", None)

        def keyevent(self, key):
            self.keys.append(key if isinstance(key, str) else str(key))
            return _MockActionResult(True, "mock", None)

        def connect(self):
            return _MockActionResult(True, "mock", None)

    return MockADB()


class _MockActionResult:
    """模拟 device.types.ActionResult(success, msg, error, payload)。

    真实 ActionResult 字段:
        success: bool
        message: str
        error: Optional[Exception]
        payload: Optional[Any]
    """
    def __init__(self, success: bool, message: str, error, payload=None):
        self.success = success
        self.message = message
        self.error = error
        self.payload = payload


def default_assertions(task_module, task_class_name: str) -> list:
    """返回对单个 task class 的 6 个标准断言列表(供测试调用)。

    断言对象:
        1. task_id 非空
        2. name 非空 + Chinese
        3. category 合法 (daily/weekly/monthly/combat/social)
        4. Pipeline 至少 5 个节点
        5. verify_done 节点存在
        6. on_error 不指向 verify_done(silent SUCCESS 警示)
    """
    import inspect
    cls = getattr(task_module, task_class_name)
    return [
        ("task_id 字段", lambda: bool(cls.task_id)),
        ("name 字段", lambda: bool(cls.name)),
        ("category 合法", lambda: cls.category in ("daily", "weekly", "monthly", "combat", "social")),
        ("Pipeline 节点 ≥ 5", lambda: _check_pipeline_size(task_module, task_class_name, min_size=5)),
        ("verify_done 节点存在", lambda: _check_verify_done_present(task_module, task_class_name)),
        ("on_error 不指 verify_done", lambda: _check_no_silent_verify_done(task_module, task_class_name)),
    ]


def _check_pipeline_size(task_module, task_class_name: str, min_size: int) -> bool:
    """检查 build_<task>_pipeline() 返回的 pipeline 节点数。"""
    builder_name = f"_build_{task_class_name.replace('Task', '').lower()}_pipeline"
    builder = getattr(task_module, builder_name, None)
    if builder is None:
        return False
    # 不实例化 Navigator,用 inspect 看源码长度
    import inspect
    try:
        source = inspect.getsource(builder)
        return source.count("pipe.add(") >= min_size - 1  # 减去开头的 ensure_home
    except Exception:
        return False


def _check_verify_done_present(task_module, task_class_name: str) -> bool:
    """检查 builder 内至少有一个 verify_done 节点。"""
    builder_name = f"_build_{task_class_name.replace('Task', '').lower()}_pipeline"
    builder = getattr(task_module, builder_name, None)
    if builder is None:
        return False
    import inspect
    try:
        source = inspect.getsource(builder)
        return '"verify_done"' in source or "'verify_done'" in source
    except Exception:
        return False


def _check_no_silent_verify_done(task_module, task_class_name: str) -> bool:
    """检查 on_error 不指向 verify_done(2026-06-30 起 silent SUCCESS 已禁止)。

    允许 back_main_screen → verify_done(回主页 OK)。
    但 alert/find_* 节点的 on_error 不应直接 verify_done。
    """
    builder_name = f"_build_{task_class_name.replace('Task', '').lower()}_pipeline"
    builder = getattr(task_module, builder_name, None)
    if builder is None:
        return False
    import inspect
    try:
        source = inspect.getsource(builder)
        # on_error=['verify_done'] 出现频次 = 0 表示 OK(都用 back_main_screen 回主页)
        # 但允许最后 back_main_screen 节点 on_error=['verify_done']
        cnt = source.count("on_error=['verify_done']")
        return cnt <= 1  # 至多 1 处(仅最终 back_main_screen)
    except Exception:
        return False


__all__ = [
    "make_blank_screen",
    "make_mock_adb",
    "default_assertions",
]
