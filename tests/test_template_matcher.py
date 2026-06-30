"""test_template_matcher.py — TemplateMatcher 关键行为。

不依赖真实模板图;用 numpy 在 tmp_path 内构造 PNG,跑全功能验证。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from core.config_manager import TemplateMatchingConfig
from recognition.template_matcher import (
    MatchResult,
    TemplateMatcher,
    _normalize_roi,
    load_template,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def screen() -> np.ndarray:
    """构造一张 1000x800 BGR 测试图,左上角放一个独特的彩色图形。

    注意: 模板特征不能是「纯色背景 + 单一矩形」—— OpenCV 的 TM_CCOEFF_NORMED
    对大面积均匀的模板不敏感,会在多个位置给出 score ≈ 1.0。所以 fixture 用
    一张噪点背景 + 一个独特颜色矩形,确保匹配定位唯一。
    """
    rng = np.random.default_rng(seed=42)
    img = rng.integers(0, 256, size=(800, 1000, 3), dtype=np.uint8)
    # 在左上角 (50, 50) 处画一个独特颜色的矩形
    cv2.rectangle(img, (50, 50), (250, 150), (200, 100, 50), thickness=-1)  # BGR
    # 加一个内框以增加特征
    cv2.rectangle(img, (80, 80), (200, 130), (50, 200, 200), thickness=3)
    return img


@pytest.fixture
def template_path(tmp_path: Path, screen: np.ndarray) -> Path:
    """把 screen 的彩色矩形区域抠出来当模板,写到 tmp_path。"""
    tpl = screen[50:150, 50:250].copy()
    path = tmp_path / "blue_box.png"
    assert cv2.imwrite(str(path), tpl)
    return path


@pytest.fixture
def template_dir(tmp_path: Path, screen: np.ndarray) -> Path:
    """把模板放到一个目录里,模拟「多模板目录」用法。"""
    d = tmp_path / "templates"
    d.mkdir()
    tpl = screen[50:150, 50:250].copy()
    assert cv2.imwrite(str(d / "blue_box.png"), tpl)
    # 加一个无关模板(右下角 30x30 黑块)
    noise = np.zeros((30, 30, 3), dtype=np.uint8)
    assert cv2.imwrite(str(d / "noise.png"), noise)
    return d


# ============================================================
# match
# ============================================================


def test_match_finds_template(screen, template_path):
    m = TemplateMatcher()
    res = m.match(template_path, screen, threshold=0.9)
    assert res is not None
    assert isinstance(res, MatchResult)
    assert res.template_name == "blue_box.png"
    assert res.confidence > 0.9
    # 位置应该接近 (50, 50)
    assert abs(res.x - 50) <= 2
    assert abs(res.y - 50) <= 2
    assert res.width == 200
    assert res.height == 100


def test_match_with_roi_constrains_search(screen, template_path):
    """指定 ROI 在左上角,匹配仍然成功。"""
    m = TemplateMatcher()
    res = m.match(template_path, screen, roi=(0, 0, 400, 300), threshold=0.9)
    assert res is not None
    assert res.confidence > 0.9


def test_match_with_wrong_roi_returns_none(screen, template_path):
    """指定 ROI 到右下角,模板不在该区域,应返回 None。"""
    m = TemplateMatcher()
    res = m.match(template_path, screen, roi=(700, 700, 200, 50), threshold=0.9)
    assert res is None


def test_match_below_threshold_returns_none(tmp_path, screen):
    """用一个跟 screen 完全无关的模板 → score 应该低于 0.999999 → 返回 None。"""
    rng = np.random.default_rng(seed=99)
    unrelated = rng.integers(0, 256, size=(100, 200, 3), dtype=np.uint8)
    path = tmp_path / "unrelated.png"
    assert cv2.imwrite(str(path), unrelated)
    m = TemplateMatcher()
    res = m.match(path, screen, threshold=0.999999)
    assert res is None


def test_match_directory_picks_best(template_dir, screen):
    """目录里多个模板,match 取最佳。"""
    m = TemplateMatcher()
    res = m.match(template_dir, screen, threshold=0.9)
    assert res is not None
    assert res.template_name == "blue_box.png"


def test_match_screen_none_returns_none(template_path):
    m = TemplateMatcher()
    assert m.match(template_path, None) is None


def test_match_empty_screen_returns_none(template_path):
    m = TemplateMatcher()
    blank = np.zeros((0, 0, 3), dtype=np.uint8)
    assert m.match(template_path, blank) is None


def test_match_template_larger_than_screen_returns_none(tmp_path):
    """模板比 ROI 还大 → 跳过。"""
    big_screen = np.full((50, 50, 3), 100, dtype=np.uint8)
    big_tpl = np.full((200, 200, 3), 100, dtype=np.uint8)
    path = tmp_path / "big.png"
    assert cv2.imwrite(str(path), big_tpl)
    m = TemplateMatcher()
    assert m.match(path, big_screen) is None


def test_match_missing_template_returns_none(screen, tmp_path):
    m = TemplateMatcher()
    assert m.match(tmp_path / "does_not_exist.png", screen) is None


def test_match_empty_directory_returns_none(tmp_path, screen):
    """目录存在但为空 → 返回 None(不抛错)。"""
    d = tmp_path / "empty"
    d.mkdir()
    m = TemplateMatcher()
    assert m.match(d, screen) is None


def test_match_threshold_validation():
    m = TemplateMatcher()
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        m.match("foo.png", img, threshold=1.5)
    with pytest.raises(ValueError):
        m.match("foo.png", img, threshold=-0.1)


# ============================================================
# match_all
# ============================================================


def test_match_all_returns_multiple(template_dir, screen):
    m = TemplateMatcher()
    results = m.match_all(template_dir, screen, threshold=0.9)
    # noise.png 在屏幕里也能匹配(都是黑色 30x30),所以至少 1 个
    assert len(results) >= 1
    # 按 confidence 降序
    for i in range(len(results) - 1):
        assert results[i].confidence >= results[i + 1].confidence


def test_match_all_respects_max_results(template_dir, screen):
    m = TemplateMatcher()
    results = m.match_all(template_dir, screen, threshold=0.5, max_results=1)
    assert len(results) == 1


def test_match_all_empty_screen_returns_empty(template_dir):
    m = TemplateMatcher()
    assert m.match_all(template_dir, None) == []


# ============================================================
# exists
# ============================================================


def test_exists_true(screen, template_path):
    m = TemplateMatcher()
    assert m.exists(template_path, screen, threshold=0.9) is True


def test_exists_false_when_threshold_too_high(tmp_path, screen):
    """用无关模板 + 极高阈值 → exists 应该返回 False。"""
    rng = np.random.default_rng(seed=123)
    unrelated = rng.integers(0, 256, size=(100, 200, 3), dtype=np.uint8)
    path = tmp_path / "unrelated.png"
    assert cv2.imwrite(str(path), unrelated)
    m = TemplateMatcher()
    assert m.exists(path, screen, threshold=0.999999) is False


def test_exists_false_when_no_template(tmp_path, screen):
    m = TemplateMatcher()
    assert m.exists(tmp_path / "missing.png", screen) is False


# ============================================================
# 默认阈值从 ConfigManager 取
# ============================================================


def test_default_threshold_from_config_manager(tmp_path):
    from core.config_manager import ConfigManager, TemplateMatchingConfig
    cfg = ConfigManager(tmp_path, auto_load=True)
    # 显式改一下阈值
    cfg.app.template_matching.default_threshold = 0.5
    m = TemplateMatcher(cfg)
    img = np.full((100, 100, 3), 30, dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (60, 60), (200, 100, 50), thickness=-1)
    tpl = img[20:60, 20:60].copy()
    p = tmp_path / "t.png"
    assert cv2.imwrite(str(p), tpl)
    res = m.match(p, img)
    assert res is not None
    assert res.confidence > 0.5


def test_default_threshold_from_partial_config():
    """只传 TemplateMatchingConfig(无 ConfigManager)也能正常工作。"""
    cfg = TemplateMatchingConfig(default_threshold=0.5)
    m = TemplateMatcher(cfg)
    assert m._default_threshold == 0.5


# ============================================================
# helpers
# ============================================================


def test_normalize_roi_clamps_to_screen():
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    # 越界 ROI → 自动 clip
    assert _normalize_roi(img, (-50, -50, 500, 500)) == (0, 0, 200, 100)
    # 退化 ROI → 视为全图
    assert _normalize_roi(img, (10, 10, 0, 0)) == (0, 0, 200, 100)
    # None → 全图
    assert _normalize_roi(img, None) == (0, 0, 200, 100)
    # 正常 ROI
    assert _normalize_roi(img, (10, 10, 50, 50)) == (10, 10, 50, 50)


def test_normalize_roi_completely_outscreen_returns_full():
    """P1-STABLE-04: ROI 完全越界(都在屏幕外)→ 退化到全图,避免 cv2 报错。"""
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    # ROI 起点在右下角外,end 也超出
    assert _normalize_roi(img, (500, 500, 100, 100)) == (0, 0, 200, 100)
    # ROI 完全在右边界外
    assert _normalize_roi(img, (250, 50, 50, 50)) == (0, 0, 200, 100)
    # 负宽高 → 视为全图
    assert _normalize_roi(img, (10, 10, -5, -5)) == (0, 0, 200, 100)


def test_match_with_completely_outscreen_roi_falls_back_to_full_screen(tmp_path, screen):
    """P1-STABLE-04: ROI 完全越界时 match 不应抛 cv2 错误,应退化为全图搜索。"""
    tpl = screen[50:150, 50:250].copy()
    path = tmp_path / "blue_box.png"
    assert cv2.imwrite(str(path), tpl)
    m = TemplateMatcher()
    # ROI 完全在屏幕外 → 退化到全图 → 仍然能匹配
    res = m.match(path, screen, roi=(2000, 2000, 100, 100), threshold=0.9)
    assert res is not None
    assert res.confidence > 0.9


def test_load_template_returns_none_for_missing(tmp_path):
    assert load_template(tmp_path / "nope.png") is None