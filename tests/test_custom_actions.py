"""test_custom_actions.py — GoIntoEntryByGuide / NonlinearSwipe 自定义 action 行为。

Maafw 自定义 action 继承自 maa.custom_action.CustomAction(C++ 类)。
测试用 MagicMock 替换 context.tasker.controller + context.run_recognition_direct,验证:
- 参数缺失 → False
- 截屏失败 → False
- OCR 命中 → 点击 + True(post_delay 跳过)
- OCR 不命中 → False
- 多 alias 命中 → 用第一个命中
- box 中心计算正确
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
    """OCR 命中 box=(80,300,120,50) → 点击 (80+60, 300+25) = (140, 325)。"""
    # 跳过 1.5s post_delay
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is True
    fake_context.tasker.controller.post_click.assert_called_once_with(140, 325)


def test_ocr_miss_returns_false(action, fake_context, fake_reco_miss, monkeypatch):
    """OCR 不命中 → False,不点击。"""
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_miss
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is False
    fake_context.tasker.controller.post_click.assert_not_called()


def test_ocr_returns_none_returns_false(action, fake_context, monkeypatch):
    """run_recognition_direct 返 None → False(没启动识别流程)。"""
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = None
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is False


# ============================================================
# 多 alias
# ============================================================


def test_multi_alias_first_hit_wins(action, fake_context, monkeypatch):
    """多 alias:第一个命中即用,不再试后续。"""
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    from maa.define import Rect
    # 第一个 alias "秘境探险" 不命中,第二个 "秋境探险" 命中
    miss = MagicMock(hit=False, box=None)
    hit = MagicMock(hit=True, box=Rect(x=60, y=400, w=100, h=40))
    fake_context.run_recognition_direct.side_effect = [miss, hit]

    argv = MagicMock()
    argv.custom_action_param = {
        "entry_name": ["秘境探险", "秋境探险"],
    }
    assert action.run(fake_context, argv) is True
    # 调用 2 次 OCR(alias × 2)
    assert fake_context.run_recognition_direct.call_count == 2
    # 点中第二个 alias 的 box 中心
    fake_context.tasker.controller.post_click.assert_called_once_with(110, 420)


def test_multi_alias_all_miss_returns_false(action, fake_context, monkeypatch):
    """多 alias 全部不命中 → False。"""
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    miss = MagicMock(hit=False, box=None)
    fake_context.run_recognition_direct.return_value = miss

    argv = MagicMock()
    argv.custom_action_param = {
        "entry_name": ["秘境探险", "秋境探险"],
    }
    assert action.run(fake_context, argv) is False
    assert fake_context.run_recognition_direct.call_count == 2
    fake_context.tasker.controller.post_click.assert_not_called()


# ============================================================
# OCR 参数校验 — ROI / threshold / order_by 传对
# ============================================================


def test_ocr_jocr_uses_correct_roi_and_threshold(
    action, fake_context, fake_reco_detail, monkeypatch,
):
    """JOCR 用 ROI=(0,66,219,627) + threshold=0.3 + order_by=Vertical。"""
    from maa.pipeline import JOCR, JRecognitionType
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}
    action.run(fake_context, argv)

    # 检查 OCR 调用
    call = fake_context.run_recognition_direct.call_args
    reco_type, jocr_obj, image = call.args
    assert reco_type == JRecognitionType.OCR
    assert isinstance(jocr_obj, JOCR)
    assert jocr_obj.expected == ["组织"]
    assert jocr_obj.roi == (0, 66, 219, 627)
    assert jocr_obj.threshold == 0.3
    assert jocr_obj.order_by == "Vertical"


# ============================================================
# post_delay
# ============================================================


def test_post_delay_1500ms(action, fake_context, fake_reco_detail):
    """OCR 命中 → 调 time.sleep(1.5) 等页面切换。"""
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    with patch("maafw_bridge.custom_actions.time.sleep") as mock_sleep:
        action.run(fake_context, argv)
        mock_sleep.assert_called_once_with(1.5)


# ============================================================
# 点击失败
# ============================================================


def test_click_raises_returns_false(action, fake_context, fake_reco_detail, monkeypatch):
    """post_click 抛异常 → False(但 OCR 命中过)。"""
    monkeypatch.setattr("maafw_bridge.custom_actions.time.sleep", lambda _: None)
    fake_context.run_recognition_direct.return_value = fake_reco_detail
    fake_context.tasker.controller.post_click.side_effect = RuntimeError("click failed")
    argv = MagicMock()
    argv.custom_action_param = {"entry_name": "组织"}

    assert action.run(fake_context, argv) is False


# ============================================================
# 入口点: GoIntoEntryByGuide / NonlinearSwipe 注册
# ============================================================


def test_register_default_actions_calls_both():
    """register_default_custom_actions 注册 2 个 action。"""
    from maafw_bridge.custom_actions import register_default_custom_actions
    fake_resource = MagicMock()
    results = register_default_custom_actions(fake_resource)
    assert "NonlinearSwipe" in results
    assert "GoIntoEntryByGuide" in results
    assert fake_resource.register_custom_action.call_count == 2


def test_register_handles_exception():
    """注册时单个 action 失败不阻断另一个。"""
    from maafw_bridge.custom_actions import register_default_custom_actions
    fake_resource = MagicMock()
    fake_resource.register_custom_action.side_effect = [
        True,    # NonlinearSwipe ok
        OSError("resource corrupted"),  # GoIntoEntryByGuide 失败
    ]
    results = register_default_custom_actions(fake_resource)
    assert results["NonlinearSwipe"] is True
    assert results["GoIntoEntryByGuide"] is False
