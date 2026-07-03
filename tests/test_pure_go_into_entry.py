"""test_pure_go_into_entry.py — 本项目版 GoIntoEntryByGuide 行为测试。

测试覆盖:
    - 构造接受 adb + ocr
    - go:OCR 命中 → tap + True
    - go:OCR 不命中 → 不 tap + False
    - go:截屏失败 → False
    - go:点击失败 → False
    - go_any:多 alias,首个命中即用
    - go_any:全 miss → False
    - go_any:空 list → False
    - post_delay 通过 mock time.sleep 验证
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from device.types import ActionResult
from tasks.pure_actions.go_into_entry_by_guide import (
    DEFAULT_POST_DELAY_MS,
    GoIntoEntryByGuide,
    LEFT_MENU_ROI,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fake_adb() -> MagicMock:
    adb = MagicMock()
    # 默认截屏成功,返 BGR ndarray
    adb.screenshot.return_value = ActionResult(
        success=True,
        message="ok",
        next_state=None,
        payload=np.zeros((1080, 1920, 3), dtype=np.uint8),
    )
    # 默认 tap 成功
    adb.tap.return_value = ActionResult(success=True, message="ok", next_state=None, payload=None)
    return adb


@pytest.fixture
def fake_ocr() -> MagicMock:
    ocr = MagicMock()
    from recognition.ocr_matcher import OCRMatchResult
    # 默认:不命中(返 None)
    ocr.match.return_value = None
    ocr.match_all.return_value = []
    # 准备一个命中样本
    ocr._hit_result = OCRMatchResult(
        text="组织", x=80, y=300, width=120, height=50, confidence=0.92,
    )
    return ocr


@pytest.fixture
def guide(fake_adb, fake_ocr) -> GoIntoEntryByGuide:
    return GoIntoEntryByGuide(fake_adb, fake_ocr)


# ============================================================
# 常量
# ============================================================


def test_left_menu_roi_matches_narutomobile():
    """LEFT_MENU_ROI 必须跟 narutomobile ninja_guide_find_funtion_entry.roi 一致。"""
    assert LEFT_MENU_ROI == (0, 66, 219, 627)


def test_default_post_delay_is_1500ms():
    """post_delay 默认 1500ms(跟 narutomobile goto_group_by_guide.post_delay 一致)。"""
    assert DEFAULT_POST_DELAY_MS == 1500


# ============================================================
# 构造
# ============================================================


def test_construct(fake_adb, fake_ocr):
    g = GoIntoEntryByGuide(fake_adb, fake_ocr)
    assert g._adb is fake_adb
    assert g._ocr is fake_ocr
    assert g._post_delay_ms == 1500
    assert g._threshold == 0.3


def test_construct_with_custom_params(fake_adb, fake_ocr):
    g = GoIntoEntryByGuide(fake_adb, fake_ocr, post_delay_ms=500, threshold=0.5)
    assert g._post_delay_ms == 500
    assert g._threshold == 0.5


# ============================================================
# go:单 alias
# ============================================================


def test_go_ocr_hit_taps_center(guide, fake_adb, fake_ocr):
    """OCR 命中 box=(80,300,120,50) → 点击 (140, 325)。"""
    fake_ocr.match.return_value = fake_ocr._hit_result
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep") as mock_sleep:
        assert guide.go("组织") is True
    # 截屏一次
    fake_adb.screenshot.assert_called_once()
    # OCR 用 LEFT_MENU_ROI + 单 alias(go() 内部转成 go_any(["组织"]),逐个尝试)
    call = fake_ocr.match.call_args
    expected, screen = call.args[:2]
    assert expected == "组织"  # 单 alias 字符串(go_any 逐个尝试)
    assert call.kwargs["roi"] == LEFT_MENU_ROI
    # 点击中心
    fake_adb.tap.assert_called_once_with(140, 325)
    # post_delay 调用
    mock_sleep.assert_called_once_with(1.5)


def test_go_ocr_miss_returns_false(guide, fake_adb, fake_ocr):
    """OCR 不命中 → False,不点击。"""
    fake_ocr.match.return_value = None
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep"):
        assert guide.go("组织") is False
    fake_adb.tap.assert_not_called()


def test_go_screenshot_failed_returns_false(guide, fake_adb, fake_ocr):
    """截屏失败 → False。"""
    fake_adb.screenshot.return_value = ActionResult(
        success=False, message="adb error", next_state=None, payload=None,
    )
    assert guide.go("组织") is False
    fake_ocr.match.assert_not_called()


def test_go_screenshot_payload_none_returns_false(guide, fake_adb, fake_ocr):
    """截屏成功但 payload=None → False。"""
    fake_adb.screenshot.return_value = ActionResult(
        success=True, message="ok", next_state=None, payload=None,
    )
    assert guide.go("组织") is False


def test_go_tap_failed_returns_false(guide, fake_adb, fake_ocr):
    """OCR 命中但 tap 失败 → False。"""
    fake_ocr.match.return_value = fake_ocr._hit_result
    fake_adb.tap.return_value = ActionResult(
        success=False, message="tap failed", next_state=None, payload=None,
    )
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep"):
        assert guide.go("组织") is False


# ============================================================
# go_any:多 alias
# ============================================================


def test_go_any_first_hit_wins(guide, fake_adb, fake_ocr):
    """多 alias,首次命中即用,只点击一次。"""
    from recognition.ocr_matcher import OCRMatchResult
    miss_result = None  # 第一个 alias miss
    hit_result = OCRMatchResult(
        text="秋境探险", x=60, y=400, width=100, height=40, confidence=0.85,
    )
    # 第一次 match miss,第二次 hit
    fake_ocr.match.side_effect = [miss_result, hit_result]
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep"):
        assert guide.go_any(["秘境探险", "秋境探险"]) is True
    # 调 2 次 OCR(每个 alias 一次)
    assert fake_ocr.match.call_count == 2
    # 点击第二个 alias 的 box 中心
    fake_adb.tap.assert_called_once_with(110, 420)


def test_go_any_all_miss_returns_false(guide, fake_ocr):
    """多 alias 全 miss → False。"""
    fake_ocr.match.return_value = None
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep"):
        assert guide.go_any(["秘境探险", "秋境探险"]) is False
    assert fake_ocr.match.call_count == 2


def test_go_any_empty_returns_false(guide, fake_ocr):
    """空 alias 列表 → False,不调 OCR。"""
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep"):
        assert guide.go_any([]) is False
    fake_ocr.match.assert_not_called()


# ============================================================
# post_delay
# ============================================================


def test_post_delay_skipped_when_zero(guide, fake_adb, fake_ocr, monkeypatch):
    """post_delay_ms=0 → 不调 time.sleep。"""
    fake_ocr.match.return_value = fake_ocr._hit_result
    guide2 = GoIntoEntryByGuide(fake_adb, fake_ocr, post_delay_ms=0)
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep") as mock_sleep:
        guide2.go("组织")
        mock_sleep.assert_not_called()


def test_post_delay_custom_value(guide, fake_adb, fake_ocr):
    """post_delay_ms=500 → time.sleep(0.5)。"""
    fake_ocr.match.return_value = fake_ocr._hit_result
    guide2 = GoIntoEntryByGuide(fake_adb, fake_ocr, post_delay_ms=500)
    with patch("tasks.pure_actions.go_into_entry_by_guide.time.sleep") as mock_sleep:
        guide2.go("组织")
        mock_sleep.assert_called_once_with(0.5)
