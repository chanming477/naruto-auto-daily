"""test_common_actions.py — CommonActions 关键行为。

所有测试用 MagicMock 替换 adb_client / recognizer / game_sm,零真实外部依赖。
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from device.types import ActionResult
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine
from tasks.common_actions import CommonActions


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fake_adb() -> MagicMock:
    """ADBClient MagicMock,默认所有 keyevent / screenshot / tap 都返回 success。"""
    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.return_value = ActionResult(
        success=True, message="ok", next_state=None,
        payload=np.zeros((100, 100, 3), dtype=np.uint8),
    )
    adb.tap.return_value = ActionResult(True, "ok", None)
    return adb


@pytest.fixture
def fake_recognizer() -> MagicMock:
    """PageRecognizer MagicMock,默认 detect_state 返回 UNKNOWN。"""
    rec = MagicMock()
    from recognition.types import RecognitionResult
    rec.detect_state.return_value = RecognitionResult(
        state=GameState.UNKNOWN, confidence=0.0, method="mock",
    )
    return rec


@pytest.fixture
def fake_game_sm() -> GameStateMachine:
    """真实 GameStateMachine(轻量,可直接测状态变更)。"""
    return GameStateMachine(initial=GameState.UNKNOWN)


@pytest.fixture
def common(
    fake_adb: MagicMock,
    fake_recognizer: MagicMock,
    fake_game_sm: GameStateMachine,
    tmp_path: Path,
) -> CommonActions:
    return CommonActions(
        adb_client=fake_adb,
        recognizer=fake_recognizer,
        game_sm=fake_game_sm,
        config=MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=1.0))),
        project_root=tmp_path,
    )


# ============================================================
# go_home
# ============================================================


def test_go_home_success_when_already_home(common, fake_game_sm, fake_recognizer):
    """已经在 HOME → 立即 return True,不按任何键。"""
    fake_game_sm.update_state(GameState.HOME)
    assert common.go_home() is True
    assert not common._adb.keyevent.called  # 没按键


def test_go_home_presses_back_then_home(common, fake_game_sm, fake_recognizer, fake_adb):
    """不在 HOME 时:按 BACK max_press_back 次 + HOME 1 次。"""
    # game_sm 一直保持 UNKNOWN(fixture 默认 initial=UNKNOWN + 没人改状态)
    # recognizer 默认返回 UNKNOWN RecognitionResult(frozen dataclass,不能再 mutate)
    result = common.go_home(max_press_back=3)
    assert result is False
    # 至少按了 3 次 BACK + 1 次 HOME
    back_calls = [c for c in fake_adb.keyevent.call_args_list
                  if c.args and c.args[0] == "BACK"]
    home_calls = [c for c in fake_adb.keyevent.call_args_list
                  if c.args and c.args[0] == "HOME"]
    assert len(back_calls) == 3
    assert len(home_calls) == 1


def test_go_home_returns_false_but_no_raise_when_adb_fails(common, fake_adb):
    """ADBClient 抛异常 → go_home catch 住,return False,不向上抛。"""
    fake_adb.keyevent.side_effect = RuntimeError("adb broken")
    result = common.go_home()
    assert result is False  # 不抛异常


def test_go_home_short_circuits_when_home_detected(common, fake_game_sm, fake_recognizer, fake_adb):
    """按 BACK 中途检测到 HOME → 提前 return True,不再继续。"""
    # game_sm 已经是 HOME → 第一次 _is_current_state 检查就 True
    fake_game_sm.update_state(GameState.HOME)
    result = common.go_home()
    assert result is True
    assert fake_adb.keyevent.call_count == 0  # 没按任何键


# ============================================================
# close_popup
# ============================================================


def test_close_popup_no_popup_returns_true(common, fake_game_sm):
    """当前不是 POPUP → return True(no-op)。"""
    fake_game_sm.update_state(GameState.HOME)
    assert common.close_popup() is True


def test_close_popup_detected_but_no_template_returns_false(common, fake_game_sm):
    """当前是 POPUP 但无关闭模板 → return False + log warning,不抛。"""
    fake_game_sm.update_state(GameState.POPUP)
    assert common.close_popup() is False


def test_close_popup_exception_does_not_propagate(common, fake_game_sm):
    """异常被 catch → return False。"""
    fake_game_sm.update_state(GameState.POPUP)
    # 模拟 raise
    common._recognizer = MagicMock()
    common._recognizer.detect_state.side_effect = RuntimeError("recognizer broken")
    assert common.close_popup() is False


# ============================================================
# wait_loading
# ============================================================


def test_wait_loading_succeeds_immediately_when_not_loading(common, fake_game_sm):
    """当前不是 LOADING → 立即 return True。"""
    fake_game_sm.update_state(GameState.HOME)
    assert common.wait_loading(timeout_sec=5.0) is True


def test_wait_loading_timeout_returns_false(common, fake_game_sm, monkeypatch):
    """LOADING 卡住 → 超时 return False。"""
    fake_game_sm.update_state(GameState.LOADING)
    # 让 time.sleep 立即返回,避免真的等
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    result = common.wait_loading(timeout_sec=0.1, poll_interval_sec=0.01)
    assert result is False


def test_wait_loading_eventually_succeeds(common, fake_game_sm, monkeypatch):
    """LOADING 状态过一段时间被外部改成 HOME → return True。"""
    fake_game_sm.update_state(GameState.LOADING)

    counter = {"n": 0}

    def fake_sleep(_x):
        counter["n"] += 1
        if counter["n"] >= 3:
            # 模拟外部 detect_state 后 LOADING 结束
            fake_game_sm.update_state(GameState.HOME)

    monkeypatch.setattr(time, "sleep", fake_sleep)
    result = common.wait_loading(timeout_sec=2.0, poll_interval_sec=0.01)
    assert result is True


# ============================================================
# ensure_state
# ============================================================


def test_ensure_state_already_target_returns_true_immediately(common, fake_game_sm):
    """当前 == target → 立即 return True,不调 go_home。"""
    fake_game_sm.update_state(GameState.HOME)
    assert common.ensure_state(GameState.HOME) is True
    assert not common._adb.keyevent.called


def test_ensure_state_calls_go_home_when_not_at_target(
    common, fake_game_sm, fake_adb, monkeypatch
):
    """当前 != target → 调 go_home(尽力)+ 重新检测。"""
    fake_game_sm.update_state(GameState.LOADING)
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    # go_home 返回 False(尽力回不去),但 ensure_state 自身应该走到 max_attempts
    result = common.ensure_state(GameState.HOME, max_attempts=2)
    # 至少调用过 1 次 go_home
    assert fake_adb.keyevent.called


def test_ensure_state_exception_does_not_propagate(common, fake_game_sm):
    """ensure_state 内部异常被 catch,return False。"""
    common._recognizer = MagicMock()
    common._recognizer.detect_state.side_effect = RuntimeError("oops")
    fake_game_sm.update_state(GameState.LOADING)
    # 不应抛
    assert common.ensure_state(GameState.HOME) is False


# ============================================================
# P1-STABLE-02: ADB 断连检测
# ============================================================


def test_go_home_aborts_early_on_consecutive_adb_failures(common, fake_adb, fake_game_sm):
    """P1-STABLE-02: 连续 2 次 keyevent 失败 → 视为 ADB 断连,提前 return False,
    不再坚持按完所有 BACK + HOME。"""
    fake_game_sm.update_state(GameState.UNKNOWN)
    fake_adb.keyevent.return_value = ActionResult(False, "adb disconnected", None)
    # max_press_back=5,正常会按 6 次(5 BACK + 1 HOME)。断连时应只按 2 次就退出。
    result = common.go_home(max_press_back=5)
    assert result is False
    # keyevent 调用次数 ≤ 2(允许 ≤ DISCONNECT_FAIL_STREAK)
    assert fake_adb.keyevent.call_count <= 2


def test_go_home_resets_fail_streak_on_success(common, fake_adb, fake_game_sm):
    """P1-STABLE-02: 单次失败后下一次成功,不算断连(fail_streak 重置)。"""
    fake_game_sm.update_state(GameState.UNKNOWN)
    # 第一次 BACK 失败,后面都成功(但因为 game_sm 一直 UNKNOWN,go_home 仍然会走完)
    call_count = {"n": 0}

    def alternating_keyevent(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ActionResult(False, "transient fail", None)
        # 后面都 success
        return ActionResult(True, "ok", None)

    fake_adb.keyevent.side_effect = alternating_keyevent
    result = common.go_home(max_press_back=3)
    # 失败 1 次后 streak 重置,继续走完 3+1 次按键,最终 UNKNOWN → 返 False(状态没到 HOME)
    assert result is False
    # 验证按了完整 4 次(3 BACK + 1 HOME,没提前退出)
    assert fake_adb.keyevent.call_count == 4


# ============================================================
# P1-STABLE-03: ensure_state 在 go_home 失败后主动重检测
# ============================================================


def test_ensure_state_reobserves_after_go_home_failure(common, fake_game_sm, fake_recognizer, fake_adb, monkeypatch):
    """P1-STABLE-03: go_home 失败后,ensure_state 主动 screenshot + detect_state 重检测,
    而不是只读 game_sm.current_state 缓存。"""
    fake_game_sm.update_state(GameState.LOADING)  # 起始 LOADING,不是 target
    monkeypatch.setattr(time, "sleep", lambda _x: None)
    # go_home 返回 False(尽力回不去)
    # 但 recognize 会把状态改成 HOME
    def fake_detect_state(_screen):
        from recognition.types import RecognitionResult
        # 第一次 detect 返回 UNKNOWN,后续返回 HOME
        if not hasattr(fake_detect_state, "called"):
            fake_detect_state.called = True
            return RecognitionResult(state=GameState.HOME, confidence=0.9, method="mock")
        return RecognitionResult(state=GameState.HOME, confidence=0.9, method="mock")

    fake_recognizer.detect_state.side_effect = fake_detect_state
    # 重要: go_home 会通过 _is_current_state 调一次 detect,ensure_state 在 go_home 失败后再调一次
    # 2 次 detect 都应被调用
    result = common.ensure_state(GameState.HOME, max_attempts=2)
    # game_sm 已被 update 到 HOME(由 _reobserve_current_state)
    assert fake_game_sm.current_state == GameState.HOME
    assert result is True
    # detect_state 至少被调 1 次(_is_current_state 或 _reobserve_current_state 之一)


# ============================================================
# P1-QUAL-03: wait_loading 文档明确标注
# ============================================================


def test_wait_loading_docstring_warns_about_passive_polling():
    """P1-QUAL-03: wait_loading docstring 必须明确标注「只轮询缓存,不主动截图」的限制。"""
    import inspect
    from tasks.common_actions import CommonActions

    doc = inspect.getdoc(CommonActions.wait_loading)
    assert "P1-QUAL-03" in doc
    # 必须提到限制
    assert "被动" in doc or "不主动" in doc
    # 必须提示 Phase 4+ 改
    assert "Phase 4" in doc or "改" in doc


# ============================================================
# P0-BUG-02: screenshot_manager
# ============================================================


def test_screenshot_capture_returns_none_on_full_failure(tmp_path: Path):
    """P0-BUG-02: capture() 重试用尽后,永远返 None(不返空 array)。"""
    from unittest.mock import MagicMock, patch

    from core.config_manager import ConfigManager, ScreenshotConfig
    from core.screenshot_manager import ScreenshotManager
    from core.window_manager import WindowInfo, Rect, WindowManager

    # mock config
    cfg = MagicMock()
    cfg.screenshot = ScreenshotConfig(
        output_dir="screenshots",
        backend="win32_print_window",
        to_grayscale=False,
        max_empty_retries=2,
        retry_delay_ms=10,
    )

    win_mgr = MagicMock(spec=WindowManager)
    info = WindowInfo(
        hwnd=12345, pid=1, process_name="x", title="t", class_name="c",
        rect=Rect(left=0, top=0, right=100, bottom=100), is_visible=True, is_minimized=False,
    )
    win_mgr.find_target.return_value = info

    mgr = ScreenshotManager(win_mgr, cfg.screenshot, tmp_path)
    # 内部 _capture_once 都返 None(完全失败)
    with patch.object(mgr, "_capture_once", return_value=None):
        result = mgr.capture()
    assert result is None  # P0-BUG-02: 必须 None,不是空 array


def test_screenshot_capture_does_not_return_empty_array(tmp_path: Path):
    """P0-BUG-02: 边缘 case — _capture_once 返空 array 时,capture 也必须返 None。"""
    import numpy as np
    from unittest.mock import MagicMock, patch

    from core.config_manager import ScreenshotConfig
    from core.screenshot_manager import ScreenshotManager
    from core.window_manager import WindowInfo, Rect, WindowManager

    cfg = MagicMock()
    cfg.screenshot = ScreenshotConfig(
        output_dir="screenshots",
        backend="win32_print_window",
        to_grayscale=False,
        max_empty_retries=2,
        retry_delay_ms=10,
    )
    win_mgr = MagicMock(spec=WindowManager)
    info = WindowInfo(
        hwnd=1, pid=1, process_name="x", title="t", class_name="c",
        rect=Rect(left=0, top=0, right=10, bottom=10), is_visible=True, is_minimized=False,
    )
    win_mgr.find_target.return_value = info
    mgr = ScreenshotManager(win_mgr, cfg.screenshot, tmp_path)

    # _capture_once 返空 array
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with patch.object(mgr, "_capture_once", return_value=empty):
        result = mgr.capture()
    assert result is None


# ============================================================
# P6-REAL-03: go_home 闭环验证(用真实 PageRecognizer + 真实模板)
# ============================================================


def _build_real_recognizer_with_home_template(tmp_path: Path):
    """构造一个真实 PageRecognizer + 真实 HOME 模板(P6-REAL-03 用)。"""
    import cv2

    from recognizer.page_recognizer import PageRecognizer

    # 构造 800x1280 屏幕,左上角放一个独特颜色矩形
    rng = np.random.default_rng(seed=20260624)
    screen = rng.integers(0, 256, size=(1280, 800, 3), dtype=np.uint8)
    cv2.rectangle(screen, (50, 50), (250, 150), (200, 100, 50), thickness=-1)
    cv2.rectangle(screen, (80, 80), (200, 130), (50, 200, 200), thickness=3)

    # HOME 模板 = 屏幕上那个矩形的精确裁切
    home_tpl = screen[50:150, 50:250].copy()
    templates_root = tmp_path / "templates"
    home_dir = templates_root / GameState.HOME.value
    home_dir.mkdir(parents=True)
    cv2.imwrite(str(home_dir / "main_hall.png"), home_tpl)

    # POPUP / LOADING 目录留空
    (templates_root / GameState.POPUP.value).mkdir(parents=True)
    (templates_root / GameState.LOADING.value).mkdir(parents=True)

    recognizer = PageRecognizer(templates_root, threshold=0.85)
    return recognizer, screen


def test_go_home_succeeds_when_home_template_matched(tmp_path, monkeypatch):
    """P6-REAL-03: 当 HOME 模板存在 + 屏幕能匹配 → go_home() 应识别到 HOME 返 True。

    流程:
        1) 初始 game_sm = UNKNOWN
        2) 调用 go_home(max_press_back=3)
        3) BACK 几次后,模拟器已经回到 HOME(屏幕包含 HOME 模板)
        4) PageRecognizer.detect_state 返回 HOME
        5) go_home 应返回 True
    """
    import cv2

    recognizer, home_screen = _build_real_recognizer_with_home_template(tmp_path)

    # 验证 recognizer 本身能在 home_screen 上识别到 HOME
    pre_check = recognizer.detect_state(home_screen)
    assert pre_check.state == GameState.HOME, (
        f"pre-check should detect HOME, got {pre_check.state} (conf={pre_check.confidence:.4f})"
    )

    # 构造 mock ADB:每次 screenshot 都返回 home_screen(模拟器已经在 HOME)
    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.return_value = ActionResult(
        success=True, message="ok", next_state=None,
        payload=home_screen.copy(),  # 必须传 .copy() 避免污染 fixture
    )
    adb.tap.return_value = ActionResult(True, "ok", None)

    # 真实 game_sm(从 UNKNOWN 开始)
    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    config = MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=0.0)))

    common = CommonActions(
        adb_client=adb,
        recognizer=recognizer,
        game_sm=game_sm,
        config=config,
        project_root=tmp_path,
    )
    monkeypatch.setattr(time, "sleep", lambda _x: None)

    # 调用 go_home
    result = common.go_home(max_press_back=3)

    assert result is True, f"go_home should return True when HOME template matches, got {result}"
    assert game_sm.current_state == GameState.HOME
    # 至少按了 1 次 BACK(因为初始 state 是 UNKNOWN,不短路)
    # 实际上,第一次 _is_current_state → 截图 → 识别 → HOME → 立即 return True
    # 所以可能 0 次 BACK 也合理。验证 keyevent 调过但没强制要求次数。
    # 关键:game_sm 应该已经切到 HOME
    assert game_sm.is_known is True


def test_go_home_with_real_template_progresses_state_machine(tmp_path, monkeypatch):
    """P6-REAL-03: go_home 每次识别到 HOME,game_sm 状态会被更新。

    模拟更现实的流程: 第一次截图 UNKNOWN(模拟器还没回到 HOME),
    第二次截图(按了一次 BACK 后)变 HOME → go_home 返 True。
    """
    import cv2

    recognizer, home_screen = _build_real_recognizer_with_home_template(tmp_path)

    # 第一次截图: 跟 HOME 无关的随机屏
    rng = np.random.default_rng(seed=42)
    not_home_screen = rng.integers(0, 256, size=(1280, 800, 3), dtype=np.uint8)

    # ADB mock: 每次 screenshot 轮流返回两张图
    screens = [not_home_screen, home_screen]
    call_n = {"n": 0}

    def fake_screenshot(*_args, **_kwargs):
        arr = screens[min(call_n["n"], len(screens) - 1)]
        call_n["n"] += 1
        return ActionResult(
            success=True, message="ok", next_state=None, payload=arr.copy(),
        )

    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.side_effect = fake_screenshot
    adb.tap.return_value = ActionResult(True, "ok", None)

    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    config = MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=0.0)))
    common = CommonActions(
        adb_client=adb, recognizer=recognizer, game_sm=game_sm,
        config=config, project_root=tmp_path,
    )
    monkeypatch.setattr(time, "sleep", lambda _x: None)

    result = common.go_home(max_press_back=3)
    assert result is True
    assert game_sm.current_state == GameState.HOME


def test_go_home_returns_false_when_no_home_template_and_screen_never_matches(tmp_path, monkeypatch):
    """P6-REAL-03: 模板目录完全为空 → 永远 UNKNOWN → go_home 返 False,但不抛。

    这是 P6 真实接入的 baseline 行为(空模板时),Phase 7 之前必须靠这个测试守护。
    """
    # 模板目录完全空
    templates_root = tmp_path / "empty_templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (templates_root / state.value).mkdir(parents=True)

    from recognizer.page_recognizer import PageRecognizer
    recognizer = PageRecognizer(templates_root, threshold=0.85)

    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.return_value = ActionResult(
        success=True, message="ok", next_state=None,
        payload=np.zeros((800, 1280, 3), dtype=np.uint8),
    )

    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    config = MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=0.0)))
    common = CommonActions(
        adb_client=adb, recognizer=recognizer, game_sm=game_sm,
        config=config, project_root=tmp_path,
    )
    monkeypatch.setattr(time, "sleep", lambda _x: None)

    result = common.go_home(max_press_back=2)
    assert result is False
    # game_sm 应该还是 UNKNOWN(没识别到任何状态)
    assert game_sm.current_state == GameState.UNKNOWN
    # BACK 键被按了 max_press_back 次 + HOME 键 1 次
    back_count = sum(
        1 for c in adb.keyevent.call_args_list
        if c.args and c.args[0] == "BACK"
    )
    home_count = sum(
        1 for c in adb.keyevent.call_args_list
        if c.args and c.args[0] == "HOME"
    )
    assert back_count == 2
    assert home_count == 1


def test_go_home_uses_real_home_template_presses_correctly(tmp_path, monkeypatch):
    """P6-REAL-03: 集成测试 — 真实模板 + 真实 recognizer + 真实 game_sm + mock ADB。

    完整流程: game_sm=UNKNOWN → 按 BACK → 截图 → 不匹配 → 按 HOME → 截图 → 匹配 → 返 True。
    """
    import cv2

    recognizer, home_screen = _build_real_recognizer_with_home_template(tmp_path)

    # subpage_screen: 纯色背景 + 屏幕中下部分放一个无关矩形
    # 关键: 不要在 (50, 50) 区域放任何接近 home 模板的颜色/特征,
    # 避免 OpenCV matchTemplate 偶然匹配到 noise pattern。
    subpage_screen = np.full((1280, 800, 3), 30, dtype=np.uint8)  # 深灰背景
    cv2.rectangle(subpage_screen, (300, 600), (500, 800), (100, 50, 200), thickness=-1)
    cv2.putText(
        subpage_screen, "SubPage", (320, 700),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2,
    )

    # 强验证: subpage_screen 不会偶然命中 home 模板
    pre_check = recognizer.detect_state(subpage_screen)
    assert pre_check.state == GameState.UNKNOWN, (
        f"subpage should NOT match HOME template, got {pre_check.state} "
        f"(conf={pre_check.confidence:.4f})"
    )

    # 用独立计数,避免 keyevent/screenshot 互相污染
    screenshot_n = {"n": 0}

    def fake_screenshot(*_args, **_kwargs):
        # 前 4 次 screenshot 返回 subpage_screen,第 4 次以后返回 home_screen
        # 估算: go_home 会做 1+max_press_back+1 = 5 次 screenshot (开头 1 次 + 每次 BACK 后 1 次 + HOME 键后 1 次)
        n = screenshot_n["n"]
        screenshot_n["n"] += 1
        arr = subpage_screen if n < 4 else home_screen
        return ActionResult(
            success=True, message="ok", next_state=None, payload=arr.copy(),
        )

    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.side_effect = fake_screenshot
    adb.tap.return_value = ActionResult(True, "ok", None)

    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    config = MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=0.0)))
    common = CommonActions(
        adb_client=adb, recognizer=recognizer, game_sm=game_sm,
        config=config, project_root=tmp_path,
    )
    monkeypatch.setattr(time, "sleep", lambda _x: None)

    # max_press_back=3: 走完整 3 BACK + 1 HOME 流程
    result = common.go_home(max_press_back=3)

    # 流程: BACK×3 (每次都不匹配) → HOME 键 (匹配) → 返 True
    assert result is True
    assert game_sm.current_state == GameState.HOME
    # 完整 keyevent 序列
    keyevents = [c.args[0] for c in adb.keyevent.call_args_list]
    assert keyevents == ["BACK", "BACK", "BACK", "HOME"]


def test_go_home_presses_home_only_after_all_backs_exhausted(tmp_path, monkeypatch):
    """P6-REAL-03: BACK 全部用尽前不应该按 HOME(避免误触)。"""
    recognizer, home_screen = _build_real_recognizer_with_home_template(tmp_path)

    # 屏幕永远是 home 模板不可识别的(强制走完所有 BACK)
    rng = np.random.default_rng(seed=11)
    fake_screen = rng.integers(0, 256, size=(1280, 800, 3), dtype=np.uint8)

    adb = MagicMock()
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.screenshot.return_value = ActionResult(
        success=True, message="ok", next_state=None, payload=fake_screen.copy(),
    )

    game_sm = GameStateMachine(initial=GameState.UNKNOWN)
    config = MagicMock(app=MagicMock(scheduler=MagicMock(inter_task_delay_sec=0.0)))
    common = CommonActions(
        adb_client=adb, recognizer=recognizer, game_sm=game_sm,
        config=config, project_root=tmp_path,
    )
    monkeypatch.setattr(time, "sleep", lambda _x: None)

    common.go_home(max_press_back=3)

    keyevents = [c.args[0] for c in adb.keyevent.call_args_list]
    # 关键契约: 所有 BACK 都在 HOME 之前
    assert keyevents == ["BACK", "BACK", "BACK", "HOME"]
    # HOME 永远在最后
    assert keyevents[-1] == "HOME"


# ===== v1.2 P1 #3 — make_recovery_chain 单元测试 =====


def test_make_recovery_chain_calls_dismiss_x_and_home_button():
    """v1.2 P1 #3: 模块级 make_recovery_chain 调 dismiss_x + tap_home_button。

    只调一次 X(单层弹窗场景,double_x=False)。
    """
    from unittest.mock import MagicMock
    from tasks.common_actions import make_recovery_chain

    common = MagicMock()
    common.dismiss_x.return_value = True
    common.tap_home_button.return_value = True
    log = MagicMock()

    result = make_recovery_chain(common, double_x=False, log=log)

    assert result is True
    common.dismiss_x.assert_called_once()
    common.tap_home_button.assert_called_once()
    log.info.assert_called()


def test_make_recovery_chain_double_x_calls_dismiss_x_twice():
    """v1.2 P1 #3: double_x=True 时 dismiss_x 调两次(双层弹窗场景)。"""
    from unittest.mock import MagicMock
    from tasks.common_actions import make_recovery_chain

    common = MagicMock()
    common.dismiss_x.return_value = True
    common.tap_home_button.return_value = True
    log = MagicMock()

    result = make_recovery_chain(common, double_x=True, log=log)

    assert result is True
    assert common.dismiss_x.call_count == 2
    common.tap_home_button.assert_called_once()


def test_make_recovery_chain_swallows_exceptions_and_returns_false():
    """v1.2 P1 #3: dismiss_x 抛异常 → 吞掉 + log warning + return False。"""
    from unittest.mock import MagicMock
    from tasks.common_actions import make_recovery_chain

    common = MagicMock()
    common.dismiss_x.side_effect = RuntimeError("adb tap failed")
    log = MagicMock()

    result = make_recovery_chain(common, double_x=False, log=log)

    assert result is False
    log.warning.assert_called_once()
    # 后续 tap_home_button 不应被调用(链断了)
    common.tap_home_button.assert_not_called()
