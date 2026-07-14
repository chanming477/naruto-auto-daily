"""test_ocr_matcher.py — 本项目 OCRMatcher 行为测试。

依赖:
    - onnxruntime(必须装,否则整个测试文件 skip)
    - resources/narutomobile/model/ocr/{det,rec}.onnx + keys.txt(必须存在,阶段 8 起统一用 narutomobile 自带)

覆盖:
    - 构造:模型目录合法 / 不存在 / 缺文件
    - 截图校验:None / 空 / 单通道
    - ROI 规范化:None / 越界 / 退化
    - threshold 边界:None / 0 / 1 / 非法值
    - expected 形式:str / list / tuple
    - _load_keys 跳过 "character" 头
    - _normalize_text / _matches_expected 单测(不依赖模型)
    - 真实模型推理:在黑图/白图上不命中(不需要游戏截图)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


# 模型目录 = 项目根/resources/narutomobile/model/ocr (阶段 8 去重,2026-07-11)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = PROJECT_ROOT / "resources" / "narutomobile" / "model" / "ocr"


pytestmark = pytest.mark.skipif(
    not MODEL_DIR.is_dir() or not (MODEL_DIR / "det.onnx").exists(),
    reason=f"OCR models not found at {MODEL_DIR}",
)


# 额外 skip:onnxruntime 没装
try:
    import onnxruntime  # noqa: F401
    _HAS_ORT = True
except ImportError:
    _HAS_ORT = False

if not _HAS_ORT:
    pytestmark = pytest.mark.skipif(True, reason="onnxruntime not installed")


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def ocr_config():
    from recognition.ocr_matcher import OCRConfig
    return OCRConfig(model_dir=MODEL_DIR, default_threshold=0.3, use_gpu=False)


@pytest.fixture
def matcher(ocr_config):
    from recognition.ocr_matcher import OCRMatcher
    return OCRMatcher(ocr_config)


# ============================================================
# 构造校验
# ============================================================


def test_construct_with_valid_model_dir(matcher):
    """合法模型目录 → 构造成功,内部 session 不为空。"""
    assert matcher is not None
    assert matcher._det_sess is not None
    assert matcher._rec_sess is not None
    assert len(matcher._keys) > 100  # 中文字符表通常 6000+


def test_construct_with_missing_dir():
    """模型目录不存在 → FileNotFoundError。"""
    from recognition.ocr_matcher import OCRConfig, OCRMatcher
    cfg = OCRConfig(model_dir=Path("Z:/nonexistent_ocr_models"))
    with pytest.raises(FileNotFoundError, match="OCR model dir not found"):
        OCRMatcher(cfg)


def test_construct_with_missing_det():
    """缺 det.onnx → FileNotFoundError。"""
    from recognition.ocr_matcher import OCRConfig, OCRMatcher
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        (td_path / "rec.onnx").write_bytes(b"")
        (td_path / "keys.txt").write_text("a\nb\n")
        cfg = OCRConfig(model_dir=td_path)
        with pytest.raises(FileNotFoundError, match="det.onnx"):
            OCRMatcher(cfg)


def test_construct_with_missing_keys():
    """缺 keys.txt → FileNotFoundError。"""
    from recognition.ocr_matcher import OCRConfig, OCRMatcher
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        (td_path / "det.onnx").write_bytes(b"")
        (td_path / "rec.onnx").write_bytes(b"")
        cfg = OCRConfig(model_dir=td_path)
        with pytest.raises(FileNotFoundError, match="keys.txt"):
            OCRMatcher(cfg)


# ============================================================
# 截图校验
# ============================================================


def test_match_with_none_screen(matcher):
    """screen=None → None。"""
    assert matcher.match(["装备"], None) is None


def test_match_with_empty_screen(matcher):
    """screen.shape[0]=0 → None。"""
    screen = np.zeros((0, 0, 3), dtype=np.uint8)
    assert matcher.match(["装备"], screen) is None


def test_match_with_single_channel_screen(matcher):
    """单通道图(灰度)→ None(不合法)。"""
    screen = np.zeros((100, 100), dtype=np.uint8)
    assert matcher.match(["装备"], screen) is None


# ============================================================
# ROI 规范化
# ============================================================


def test_match_with_roi_none(matcher):
    """roi=None → 全图(不会崩)。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match(["装备"], screen) is None  # 黑图无文字


def test_match_with_roi_out_of_bounds(matcher):
    """roi 越界 → 自动 clip(不崩,大概率不命中)。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match(["装备"], screen, roi=(1900, 1000, 200, 200)) is None


def test_match_with_zero_size_roi(matcher):
    """roi w=0 → None。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match(["装备"], screen, roi=(100, 100, 0, 100)) is None


# ============================================================
# threshold 边界
# ============================================================


def test_match_with_threshold_zero(matcher):
    """threshold=0 → 不会因为阈值过滤(可以正常返回 None/结果)。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match(["装备"], screen, threshold=0) is None


def test_match_with_threshold_one(matcher):
    """threshold=1.0 → 要求 100% 置信度(几乎不会命中)。"""
    screen = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    # 白图无文字
    assert matcher.match(["装备"], screen, threshold=1.0) is None


def test_match_with_invalid_threshold(matcher):
    """threshold=1.5 → ValueError。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="threshold must be in"):
        matcher.match(["装备"], screen, threshold=1.5)


# ============================================================
# expected 形式
# ============================================================


def test_match_with_str_expected(matcher):
    """expected 是单 str → 不崩,黑图无文字 → None。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match("装备", screen) is None


def test_match_with_list_expected(matcher):
    """expected 是 list → 不崩,黑图无文字 → None。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match(["装备", "组织"], screen) is None


def test_match_with_tuple_expected(matcher):
    """expected 是 tuple → 不崩。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.match(("装备", "组织"), screen) is None


# ============================================================
# match_all / exists
# ============================================================


def test_match_all_returns_list(matcher):
    """match_all 永远返 list(空 list 也行)。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    result = matcher.match_all(["装备", "组织"], screen)
    assert isinstance(result, list)


def test_match_all_max_results_limits(matcher):
    """max_results=3 → 最多返 3 个。"""
    screen = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    result = matcher.match_all(["x", "y", "z"], screen, max_results=3)
    assert len(result) <= 3


def test_exists_returns_bool(matcher):
    """exists 是 match 的布尔包装。"""
    screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert matcher.exists(["装备"], screen) is False


# ============================================================
# 内部函数(不依赖模型)
# ============================================================


def test_normalize_text_strips_whitespace():
    """_normalize_text 去除全部空白。"""
    from recognition.ocr_matcher import OCRMatcher
    assert OCRMatcher._normalize_text("装 备") == "装备"
    assert OCRMatcher._normalize_text("  组 织  ") == "组织"
    assert OCRMatcher._normalize_text("\n\t\r") == ""


def test_matches_expected_exact():
    """精确匹配。"""
    from recognition.ocr_matcher import OCRMatcher
    assert OCRMatcher._matches_expected("装备", {"装备", "组织"}) is True
    assert OCRMatcher._matches_expected("组", {"装备", "组织"}) is True  # 包含
    assert OCRMatcher._matches_expected("金", {"装备", "组织"}) is False


def test_load_keys_skips_character_header(tmp_path):
    """_load_keys 跳过 PaddleOCR 风格的 'character' 表头。"""
    from recognition.ocr_matcher import OCRMatcher
    keys_file = tmp_path / "keys.txt"
    keys_file.write_text("character\n装\n备\n", encoding="utf-8")
    keys = OCRMatcher._load_keys(keys_file)
    assert "character" not in keys
    assert "装" in keys
    assert "备" in keys
    assert keys == ["装", "备"]


def test_load_keys_handles_empty_lines(tmp_path):
    """_load_keys 跳过空行。"""
    from recognition.ocr_matcher import OCRMatcher
    keys_file = tmp_path / "keys.txt"
    keys_file.write_text("装\n\n备\n\n", encoding="utf-8")
    keys = OCRMatcher._load_keys(keys_file)
    assert keys == ["装", "备"]


# ============================================================
# 默认模型目录 helper
# ============================================================


def test_load_default_ocr_model_dir():
    """load_default_ocr_model_dir 返回 {project_root}/resources/narutomobile/model/ocr(阶段 8 去重)。"""
    from recognition.ocr_matcher import load_default_ocr_model_dir
    p = load_default_ocr_model_dir(PROJECT_ROOT)
    assert p == PROJECT_ROOT / "resources" / "narutomobile" / "model" / "ocr"
    assert p.is_dir()  # narutomobile 已自带 OCR 模型
