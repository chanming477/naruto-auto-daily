"""test_custom_actions.py — GoIntoEntryByGuide / NonlinearSwipe 自定义 action 行为。

Maafw 自定义 action 继承自 maa.custom_action.CustomAction(C++ 类)。
测试用 MagicMock 替换 context.tasker.controller + context.run_recognition_direct,验证:
- 参数缺失 → False
- 截屏失败 → False
- OCR 命中 → 点击 + True(post_delay 跳过)
- OCR 不命中 → False
- 多 alias 命中 → 用第一个命中
- box 中心计算正确

方案 A (2026-07-15) 改动:
    核心逻辑移到 ``maafw_bridge._actions_core``,本测试只改 monkeypatch target
    从 ``maafw_bridge.custom_actions.time.sleep`` → ``maafw_bridge._actions_core.time.sleep``
    (time.sleep 实际在 _actions_core 里调用,不在 custom_actions 里)。
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def fake_context() -> MagicMock:
    """Maafw context MagicMock — tasker.controller + run_recognition_direct。"""
    ctx = MagicMock()
    # 截屏拿 numpy image
    fake_image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    screencap_job = MagicMock()
    screencap_job.wait.return_value.get.return_value = fake_image
    ctx.tasker.controller.post_screencap.return_value = screencap_job
    # post_click
    click_job = MagicMock()
    click_job.wait.return_value = None
    ctx.tasker.controller.post_click.return_value = click_job
    return ctx


@pytest.fixture
def fake_reco_detail():
    """一个假的 RecognitionDetail(带 box + hit)。"""
    from maa.define import Rect
    reco = MagicMock()
    reco.hit = True
    reco.box = Rect(x=80, y=300, w=120, h=50)
    return reco


@pytest.fixture
def fake_reco_miss():
    """一个假的 RecognitionDetail(不命中)。"""
    reco = MagicMock()
    reco.hit = False
    reco.box = None
    return reco


@pytest.fixture
def action():
    from maafw_bridge.custom_actions import GoIntoEntryByGuideAction
    return GoIntoEntryByGuideAction()


# ============================================================
# 参数校验
# ============================================================


def test_missing_entry_name_returns_false(action, fake_context):
    """argv.custom_action_param 没 entry_name → False,不调 OCR。"""
    argv = MagicMock()
    argv.custom_action_param = {}
    assert action.run(fake_context, argv) is False
    fake_context.run_recognition_direct.assert_not_called()


def test_empty_entry_name_returns_false(action, fake_context):
    """entry_name="" → False。"""
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": ""}
    assert action.run(fake_context, argv) is False


def test_none_custom_action_param_returns_false(action, fake_context):
    """argv.custom_action_param = None → False。"""
    argv = MagicMock()
    argv.custom_action_param = None
    assert action.run(fake_context, argv) is False


# ============================================================
# 截屏失败
# ============================================================


def test_screencap_returns_none_returns_false(action, fake_context):
    """截屏 job 拿不到 image → False。"""
    job = MagicMock()
    job.wait.return_value.get.return_value = None
    fake_context.tasker.controller.post_screencap.return_value = job
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}
    assert action.run(fake_context, argv) is False
    fake_context.run_recognition_direct.assert_not_called()


def test_screencap_raises_returns_false(action, fake_context):
    """截屏抛异常 → False。"""
    fake_context.tasker.controller.post_screencap.side_effect = RuntimeError("adb down")
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}
    assert action.run(fake_context, argv) is False


# ============================================================
# OCR 命中 → 点击
# ============================================================


def test_ocr_hit_clicks_center(action, fake_context, fake_reco_detail, monkeypatch):
    """新算法 (2026-07-15 完整版) 5 步 OCR 全命中 → 3 次 post_click,全部命中 box 中心 (140, 325)。

    老版本 (单步) 1 次 post_click,新版本 3 次:
        1. 忍界指引 (returning player 分支)
        2. entry tab 中心
        3. 前往按钮 中心
    box=(80,300,120,50) 中心 (140, 325),计算逻辑没变,只是调用次数变了。
    """
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is True
    # 3 次 post_click,每次都是 box 中心
    assert fake_context.tasker.controller.post_click.call_count == 3
    for call in fake_context.tasker.controller.post_click.call_args_list:
        assert call.args == (140, 325)


def test_ocr_miss_returns_false(action, fake_context, fake_reco_miss, monkeypatch):
    """OCR 不命中 → False,不点击。"""
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_miss
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is False
    fake_context.tasker.controller.post_click.assert_not_called()


def test_ocr_returns_none_returns_false(action, fake_context, monkeypatch):
    """run_recognition_direct 返 None → False(没启动识别流程)。"""
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = None
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is False


# ============================================================
# 多 alias
# ============================================================


def test_multi_alias_first_hit_wins(action, fake_context, monkeypatch):
    """多 alias:第一个命中即用,不再试后续。

    新算法 5 步 OCR:
        1. 回流 check (miss → normal path,不点 忍界指引)
        2. (skip) 忍界指引
        3. 天赋 (hit → top reached)
        4. entry_name 搜索:alias 1 miss → alias 2 hit
        5. 前往 (hit)
    2 次 post_click:entry tab (110, 420) + 前往 (中心由 前往 box 决定)。
    """
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    from maa.define import Rect
    miss = MagicMock(hit=False, box=None)
    tianfu = MagicMock(hit=True, box=Rect(x=0, y=66, w=219, h=627))
    alias1_miss = MagicMock(hit=False, box=None)
    alias2_hit = MagicMock(hit=True, box=Rect(x=60, y=400, w=100, h=40))
    qian_hit = MagicMock(hit=True, box=Rect(x=834, y=539, w=287, h=149))
    fake_context.run_recognition_direct.side_effect = [
        miss,        # step 1: 回流 → miss
        tianfu,      # step 3: 天赋 → hit
        alias1_miss, # step 4 attempt 0: alias 1 → miss
        alias2_hit,  # step 4 attempt 0: alias 2 → hit (第一次 hit 即用)
        qian_hit,    # step 5: 前往 → hit
    ]

    argv = MagicMock()
    argv.custom_action_param = {
        "entry_name": ["秘境探险", "秋境探险"],
    }
    assert action.run(fake_context, argv) is True
    # alias 2 box 中心 (60+50, 400+20) = (110, 420)
    # 前往 box 中心 (834+143, 539+74) = (977, 613)
    calls = fake_context.tasker.controller.post_click.call_args_list
    assert len(calls) == 2
    assert calls[0].args == (110, 420)
    assert calls[1].args == (977, 613)


def test_multi_alias_all_miss_returns_false(action, fake_context, monkeypatch):
    """多 alias 全部不命中 → False。

    新算法:全部 miss 意味着:
        - step 1 回流 miss → normal path
        - step 3 天赋:也 miss,会滚 10 次都 miss,但不 return False(只是 warning)
        - step 4 找 entry:20 attempts × 2 aliases 都 miss → return False
    整个过程 0 次 post_click。
    """
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    miss = MagicMock(hit=False, box=None)
    fake_context.run_recognition_direct.return_value = miss

    argv = MagicMock()
    argv.custom_action_param = {
        "entry_name": ["秘境探险", "秋境探险"],
    }
    assert action.run(fake_context, argv) is False
    # 新算法 OCR 调用次数取决于 max_top_scroll + max_search_swipes × alias 数,
    # 不能硬编码具体次数,只验证 alias 至少被试了 2 次(每个 alias 一次)
    assert fake_context.run_recognition_direct.call_count >= 2
    fake_context.tasker.controller.post_click.assert_not_called()


# ============================================================
# OCR 参数校验 — ROI / threshold / order_by 传对
# ============================================================


def test_ocr_jocr_uses_correct_roi_and_threshold(
    action, fake_context, fake_reco_detail, monkeypatch,
):
    """JOCR 用 ROI=(0,66,219,627) + threshold=0.3 + order_by=Vertical。

    新算法会做 5 步 OCR,本测试关注 entry_name 搜索的 JOCR 参数
    (即 expected=["组织"] 那个 call)。其他 step (回流/忍界指引/天赋/前往)
    的 JOCR 参数不在本测试范围。

    注:为了让 list_roi = (0, 66, 219, 627) 而不是 returning 路径的 (209, 88, 200, 580),
    我们让 回流 check miss (走 normal player 路径)。
    """
    from maa.pipeline import JOCR, JRecognitionType
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    # step 1 (回流) miss → normal path;其他 step 都用 fake_reco_detail
    huiliu_miss = MagicMock(hit=False, box=None)
    fake_context.run_recognition_direct.side_effect = [
        huiliu_miss,  # step 1: 回流 → miss (走 normal path)
        fake_reco_detail,  # step 3: 天赋
        fake_reco_detail,  # step 4: entry_name 搜索 (本测试关注)
        fake_reco_detail,  # step 5: 前往
    ]
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}
    action.run(fake_context, argv)

    # 找 expected=["组织"] 那个 JOCR call
    jocr_calls = [
        call for call in fake_context.run_recognition_direct.call_args_list
        if len(call.args) >= 2
        and isinstance(call.args[1], JOCR)
        and call.args[1].expected == ["组织"]
    ]
    assert len(jocr_calls) >= 1, "no JOCR call with expected=['组织']"
    reco_type, jocr_obj, image = jocr_calls[0].args
    assert reco_type == JRecognitionType.OCR
    assert jocr_obj.expected == ["组织"]
    assert tuple(jocr_obj.roi) == (0, 66, 219, 627)
    assert jocr_obj.threshold == 0.3
    assert jocr_obj.order_by == "Vertical"


# ============================================================
# post_delay
# ============================================================


def test_post_delays_after_clicks(action, fake_context, fake_reco_detail):
    """OCR 命中 → 调 time.sleep 等页面切换 (在 _actions_core 里)。

    新算法 returning player 路径:
        - 0.3s (after 忍界指引 click,_wait_for_freezes 300ms)
        - 0.5s (after entry tab click,直接 time.sleep(0.5))
    普通路径只有 0.5s。本测试用 returning player (回退账号),验证 0.3 + 0.5 都被调。
    老版本的 1.5s 单一 post_delay 在新算法里被 0.3+0.5 替代。
    """
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    with patch("maafw_bridge._actions_core.time.sleep") as mock_sleep:
        action.run(fake_context, argv)
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        # returning player 路径:0.3s (after 忍界指引) + 0.5s (after entry tab)
        assert 0.3 in sleep_args, f"missing 0.3s wait, got {sleep_args}"
        assert 0.5 in sleep_args, f"missing 0.5s wait, got {sleep_args}"


# ============================================================
# 点击失败
# ============================================================


def test_click_raises_returns_false(action, fake_context, fake_reco_detail, monkeypatch):
    """post_click 抛异常 → False(但 OCR 命中过)。"""
    monkeypatch.setattr("maafw_bridge._actions_core.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    fake_context.tasker.controller.post_click.side_effect = RuntimeError("click failed")
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is False


# ============================================================
# 入口点: GoIntoEntryByGuide / NonlinearSwipe 注册
# ============================================================


def test_register_default_actions_calls_both():
    """register_default_custom_actions 注册 3 个 action (NonlinearSwipe / GoIntoEntryByGuide / CleanLogs)。"""
    from maafw_bridge.custom_actions import register_default_custom_actions
    fake_resource = MagicMock()
    results = register_default_custom_actions(fake_resource)
    assert "NonlinearSwipe" in results
    assert "GoIntoEntryByGuide" in results
    assert "CleanLogs" in results
    assert fake_resource.register_custom_action.call_count == 3


def test_register_handles_exception():
    """注册时单个 action 失败不阻断另一个。"""
    from maafw_bridge.custom_actions import register_default_custom_actions
    fake_resource = MagicMock()
    fake_resource.register_custom_action.side_effect = [
        True,    # NonlinearSwipe ok
        OSError("resource corrupted"),  # GoIntoEntryByGuide 失败
        True,    # CleanLogs ok (失败发生在中间,后续 action 不受影响)
    ]
    results = register_default_custom_actions(fake_resource)
    assert results["NonlinearSwipe"] is True
    assert results["GoIntoEntryByGuide"] is False
    assert results["CleanLogs"] is True
