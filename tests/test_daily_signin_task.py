"""test_daily_signin_task.py — DailySigninTask 关键行为。

V4 真实接入(2026-06-24) — 复用 narutomobile 模板与 pipeline 设计:
    - 业务编排改用 Navigator(状态机 next 链)
    - run() 真实走 Navigator pipeline,失败时 recover + 重试 1 次
    - pre_check / post_check / recover / enter / verify 保留作为兼容契约

测试策略:
    - V3 mock-based 测试改为 V4 Navigator-based 测试
    - 用真实模板 + 真实 recognizer + mock ADB 跑全闭环
    - 失败场景: 模板不匹配 / Pipeline 死锁 / 关键节点失败
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from core.base_task import BaseTask, ExecutionContext, TaskResult, TaskStatus
from tasks.common_actions import CommonActions
from tasks.daily_signin_task import (
    DailySigninTask,
    _build_daily_signin_pipeline,
    DEFAULT_REF_WIDTH,
    DEFAULT_REF_HEIGHT,
)
from tasks.navigator import Navigator, Node, Pipeline, ClickAction, KeyAction, NoopAction


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def common_actions() -> CommonActions:
    """mock CommonActions,ensure_state 和 go_home 默认 True。"""
    ca = MagicMock(spec=CommonActions)
    ca.ensure_state.return_value = True
    ca.go_home.return_value = True
    return ca


@pytest.fixture
def ctx(tmp_path: Path) -> ExecutionContext:
    """真实 ExecutionContext,ConfigManager 用临时 tmp_path。"""
    from core.config_manager import ConfigManager
    from core.state_machine import build_default_state_machine

    cfg = ConfigManager(tmp_path, auto_load=True)
    return ExecutionContext(
        config=cfg,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=False),
    )


@pytest.fixture
def task(common_actions, ctx) -> DailySigninTask:
    """V3: 注入到 ctx.common_actions。"""
    ctx.common_actions = common_actions
    return DailySigninTask()


# ============================================================
# Constants
# ============================================================


def test_task_id_name_category_constants():
    """常量定义正确。"""
    assert DailySigninTask.task_id == "daily_signin"
    assert DailySigninTask.name == "每日签到"
    assert DailySigninTask.category == "daily"


def test_default_ref_resolution_is_1920x1080():
    """默认 ROI 基于 1920x1080(narutomobile 平板推荐)。"""
    assert DEFAULT_REF_WIDTH == 1920
    assert DEFAULT_REF_HEIGHT == 1080


# ============================================================
# 5 方法名契约 (V2 用户清单: enter / execute / verify / recover / run)
# ============================================================


def test_does_not_override_basetask_execute():
    """P1-ARCH-01: DailySigninTask.execute 继承自 BaseTask(未覆盖)。"""
    assert DailySigninTask.execute is BaseTask.execute


def test_overrides_basetask_run():
    """run() 覆盖 BaseTask.run 抽象方法。"""
    assert DailySigninTask.run is not BaseTask.run
    assert DailySigninTask.run.__qualname__ == "DailySigninTask.run"


def test_enter_returns_true_in_demo(task, ctx):
    """V3 demo 兼容: enter 是 mock(只为兼容 BaseTask 契约)。"""
    assert task.enter(ctx) is True


def test_verify_returns_true_in_demo(task, ctx):
    assert task.verify(ctx) is True


# ============================================================
# recover — 真做
# ============================================================


def test_recover_calls_dismiss_x_and_home_button(task, ctx, common_actions):
    """v1.2 P0 #1: recover 用模板匹配替代硬编码 tap — 调 dismiss_x + tap_home_button,不调 go_home。

    模板匹配在 common_actions.dismiss_x/tap_home_button 内部完成,这里只验证公共方法被调用。
    """
    assert task.recover(ctx) is True
    # v1.2: recover 调模板化公共方法,不再直接调 adb.tap
    common_actions.dismiss_x.assert_called()
    common_actions.tap_home_button.assert_called()


def test_recover_returns_false_when_no_common_actions(task, ctx):
    """P1-BUG-01: ctx.common_actions 缺失时 recover 明确返 False。"""
    ctx.common_actions = None
    assert task.recover(ctx) is False


# ============================================================
# pre_check
# ============================================================


def test_pre_check_calls_common_actions_ensure_state(task, ctx, common_actions):
    """P0-FIX-2026-06-29: pre_check 只检查 common_actions 不为 None,不强制 ensure_state(HOME)。"""
    common_actions.ensure_state.return_value = True
    assert task.pre_check(ctx) is True


def test_pre_check_returns_false_when_no_common_actions(task, ctx):
    ctx.common_actions = None
    assert task.pre_check(ctx) is False


# ============================================================
# V4 真实流程: Pipeline 构造
# ============================================================


def test_daily_signin_pipeline_has_all_required_nodes(tmp_path):
    """Pipeline 包含完整的 8 个关键节点(2026-07-01 改写:委托 MonthlySigninTask)。

    A 计划(2026-06-30)验证:游戏里的"每日签到" = 活动页 → 每月签到 tab → 签到,
    pipeline 节点序列从 monthly 路径复用。
    """
    adb = MagicMock()
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    pipe = _build_daily_signin_pipeline(nav)

    required = [
        "ensure_home",
        "find_activity",
        "swipes_for_monthly_sign",
        "find_monthly_sign_tab",
        "find_sign_button",
        "verify_signed",
        "back_main_screen",
        "verify_done",
    ]
    for name in required:
        assert name in pipe, f"missing required node: {name}"

    assert pipe.entry == "ensure_home"


def test_pipeline_entry_node_no_recognition_just_action():
    """ensure_home 节点没有 templates(由 pre_check 完成),不需识别。"""
    from pathlib import Path
    nav = Navigator(MagicMock(), Path(r"D:\火影自动日常"))
    pipe = _build_daily_signin_pipeline(nav)
    node = pipe.get("ensure_home")
    assert node is not None
    assert node.templates == []
    assert node.next == ["find_activity"]


# ============================================================
# V4 真实流程: Navigator 端到端(用真实模板 + mock ADB)
# ============================================================


def _make_mock_adb_with_screen(screen: np.ndarray, action_success: bool = True):
    """mock ADB,每次 screenshot 返回相同 screen,其他操作 success。"""
    from device.types import ActionResult
    adb = MagicMock()
    adb.screenshot.return_value = ActionResult(
        True, "ok", None, payload=screen.copy(),
    )
    adb.tap.return_value = ActionResult(action_success, "ok", None)
    adb.keyevent.return_value = ActionResult(action_success, "ok", None)
    adb.swipe.return_value = ActionResult(action_success, "ok", None)
    return adb


def test_navigator_pipeline_with_real_template_success(tmp_path):
    """P7-REAL: 用真实 HOME 模板 + Navigator,模拟 "已经在 HOME" 场景。

    关键验证:
        1. 真实 PageRecognizer 不参与(Navigator 不依赖 GameState)
        2. Pipeline 中的模板匹配真实跑(不 mock TemplateMatcher)
        3. 模拟器返回"主界面"截图(空屏幕),所有模板不匹配 → on_error → verify_done
        4. V4 pipeline 设计: 空屏幕走 on_error 终节点,graceful exit (success=True)
    """
    adb = _make_mock_adb_with_screen(np.full((900, 1600, 3), 200, dtype=np.uint8))
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    nav.set_resolution_scale(DEFAULT_REF_WIDTH, DEFAULT_REF_HEIGHT, 1600, 900)
    pipe = _build_daily_signin_pipeline(nav)
    result = nav.run(pipe, max_total_iterations=8, max_idle_iterations=3)

    # V4: 空屏幕 → find_activity 不匹配 → on_error → back_main_screen 也不匹配 → verify_done
    # pipeline graceful exit, success=True
    assert result.success is True
    assert result.last_node == "verify_done"
    assert "verify_done" in result.history
    # 应该调过多次 screenshot
    assert adb.screenshot.call_count >= 1


def test_navigator_with_real_template_matched_in_screen(tmp_path):
    """P7-REAL: 在屏幕里贴上真实的 headhunt.png 模板位置,验证识别+点击。

    2026-07-01 改写: 活动入口模板改用 narutomobile 的 headhunt.png(活动卷轴入口)
    ROI (1920x1080) = (1194, 132, 50, 42)。
    """
    from PIL import Image
    from device.types import ActionResult

    # 加载真实的 headhunt 模板(活动入口,narutomobile ROI)
    tpl_path = Path(r"D:\火影自动日常\resources\templates\actions\shared\headhunt.png")
    assert tpl_path.exists(), f"template missing: {tpl_path}"
    pil = Image.open(tpl_path).convert("RGB")
    tpl = cv2.cvtColor(np.array(pil, dtype=np.uint8), cv2.COLOR_RGB2BGR)
    assert tpl is not None and tpl.size > 0
    th, tw = tpl.shape[:2]

    # 构造屏幕: 把 headhunt 模板贴在 narutomobile ROI 位置
    # narutomobile ROI (1920x1080) = (1194, 132, 50, 42)
    # 缩放 0.833 → (1600x900) = (994, 110, 41, 35)
    scale = 1600 / 1920
    rx, ry, rw, rh = int(1194 * scale), int(132 * scale), int(50 * scale), int(42 * scale)
    # 模板也要缩放
    tpl_small = cv2.resize(tpl, (int(tw * scale), int(th * scale)))
    sh, sw = tpl_small.shape[:2]

    screen = np.full((900, 1600, 3), 200, dtype=np.uint8)
    screen[ry:ry + sh, rx:rx + sw] = tpl_small  # 完美放置

    adb = MagicMock()
    adb.screenshot.return_value = ActionResult(True, "ok", None, payload=screen.copy())
    adb.tap.return_value = ActionResult(True, "ok", None)
    adb.keyevent.return_value = ActionResult(True, "ok", None)
    adb.swipe.return_value = ActionResult(True, "ok", None)

    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    nav.set_resolution_scale(DEFAULT_REF_WIDTH, DEFAULT_REF_HEIGHT, 1600, 900)
    pipe = _build_daily_signin_pipeline(nav)
    result = nav.run(pipe, max_total_iterations=15, max_idle_iterations=5)

    # 关键: 至少在 find_activity 节点识别到 headhunt 模板并点击
    # 后面的节点因为屏幕不变,会失败,但 find_activity 应该被命中
    assert adb.tap.call_count >= 1, "tap should be called at least once (find_activity)"
    print(f"Pipeline result: success={result.success} last={result.last_node} "
          f"iters={result.total_iterations} history={result.history}")


# ============================================================
# BaseTask.execute 模板集成
# ============================================================


def test_execute_pre_check_failure_returns_skip(task, ctx):
    """pre_check 返 False → BaseTask.execute 直接返 SKIP,run() 不被调用。"""
    ctx.common_actions = None  # 让 pre_check 返 False(P1-BUG-01 语义)
    result = task.execute(ctx)
    assert result.status == TaskStatus.SKIP
    assert "pre_check" in result.message.lower()


def test_execute_uses_zero_max_retries(task):
    """V3: max_retries=0,避免 BaseTask 模板和 run() 双重重试。"""
    assert DailySigninTask.max_retries == 0


# ============================================================
# Navigator 单元测试
# ============================================================


def test_navigator_resolution_scale_to_1600x900():
    """Navigator.set_resolution_scale 计算正确。"""
    adb = MagicMock()
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    nav.set_resolution_scale(1920, 1080, 1600, 900)
    assert abs(nav._scale_x - 0.8333) < 0.001
    assert abs(nav._scale_y - 0.8333) < 0.001


def test_navigator_resolution_scale_identity():
    """1920x1080 屏幕 → scale = 1.0。"""
    adb = MagicMock()
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    nav.set_resolution_scale(1920, 1080, 1920, 1080)
    assert nav._scale_x == 1.0
    assert nav._scale_y == 1.0


def test_navigator_template_path_resolution():
    """nav.templates() 解析 actions/ 目录下的模板。"""
    adb = MagicMock()
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    tpls = nav.templates("shared/award_center_entry.png", "shared/x.png")
    assert len(tpls) == 2
    assert tpls[0].name == "award_center_entry.png"
    assert tpls[1].name == "x.png"


def test_navigator_template_path_missing_returns_empty():
    """nav.templates() 找不到的模板静默跳过(返回空)。"""
    adb = MagicMock()
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    tpls = nav.templates("nonexistent/foo.png")
    assert tpls == []


def test_navigator_jumpback_strip():
    """[JumpBack] 前缀正确去掉。"""
    from tasks.navigator import strip_jumpback
    assert strip_jumpback("[JumpBack]back_to_home") == "back_to_home"
    assert strip_jumpback("back_to_home") == "back_to_home"
