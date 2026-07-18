"""test_page_recognizer.py — PageRecognizer.detect_state 关键行为。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from recognition.page_recognizer import PageRecognizer
from state_machine.game_state import GameState


def _save_template(directory: Path, name: str, img: np.ndarray) -> Path:
    """把 numpy 图保存为 PNG 到指定目录。"""
    p = directory / name
    assert cv2.imwrite(str(p), img)
    return p


@pytest.fixture
def screen() -> np.ndarray:
    """构造一张 800x1280 的测试图,左上角放一个亮蓝矩形(对应 HOME 模板)。"""
    img = np.full((1280, 800, 3), 30, dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (300, 200), (200, 100, 50), thickness=-1)
    return img


@pytest.fixture
def templates_root(tmp_path: Path) -> Path:
    """构造一个 4 个 state 都有模板的目录。HOME 模板对应 screen 里的蓝矩形。"""
    root = tmp_path / "templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        d = root / state.value
        d.mkdir(parents=True)
    # HOME 模板 = screen 左上角的 200x100 蓝矩形
    home_tpl = np.full((100, 200, 3), 30, dtype=np.uint8)
    cv2.rectangle(home_tpl, (0, 0), (200, 100), (200, 100, 50), thickness=-1)
    _save_template(root / GameState.HOME.value, "main_hall.png", home_tpl)
    # POPUP 模板 = 一个不匹配的模板(屏幕里没有)
    popup_tpl = np.full((50, 50, 3), 0, dtype=np.uint8)
    cv2.putText(popup_tpl, "POP", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    _save_template(root / GameState.POPUP.value, "popup.png", popup_tpl)
    # LOADING 模板 = 同样不匹配
    load_tpl = np.full((40, 40, 3), 0, dtype=np.uint8)
    _save_template(root / GameState.LOADING.value, "loading.png", load_tpl)
    return root


def test_detect_state_finds_home(templates_root, screen):
    pr = PageRecognizer(templates_root)
    result = pr.detect_state(screen)
    assert result.state == GameState.HOME
    assert result.confidence > 0.9
    assert "template_match:HOME" in result.method
    assert "main_hall" in result.method


def test_detect_state_screen_returns_unknown_for_empty_dirs(tmp_path):
    """屏幕非空但模板目录都空 → UNKNOWN + empty_templates 方法。"""
    root = tmp_path / "templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (root / state.value).mkdir(parents=True)
    pr = PageRecognizer(root)
    rng = np.random.default_rng(seed=7)
    blank = rng.integers(0, 256, size=(1280, 800, 3), dtype=np.uint8)
    result = pr.detect_state(blank)
    assert result.state == GameState.UNKNOWN
    assert result.confidence == 0.0
    assert result.method == "fallback:empty_templates"


def test_detect_state_returns_unknown_when_all_dirs_empty(tmp_path, screen):
    root = tmp_path / "empty_templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (root / state.value).mkdir(parents=True)
    pr = PageRecognizer(root)
    result = pr.detect_state(screen)
    assert result.state == GameState.UNKNOWN
    assert result.confidence == 0.0
    assert result.method == "fallback:empty_templates"


def test_detect_state_screen_none(templates_root):
    pr = PageRecognizer(templates_root)
    result = pr.detect_state(None)
    assert result.state == GameState.UNKNOWN
    assert result.confidence == 0.0


def test_detect_state_picks_best_among_states(templates_root):
    """构造一张跟 HOME 模板完美匹配的随机噪声图 + 把 POPUP/LOADING 模板覆盖为不同 noise。"""
    rng = np.random.default_rng(seed=11)
    screen = rng.integers(0, 256, size=(1280, 800, 3), dtype=np.uint8)
    # 在 (100, 100) 处贴一个 HOME 模板
    home_tpl_data = cv2.imread(str(templates_root / GameState.HOME.value / "main_hall.png"))
    assert home_tpl_data is not None
    h, w = home_tpl_data.shape[:2]
    screen[100:100 + h, 100:100 + w] = home_tpl_data

    pr = PageRecognizer(templates_root)
    result = pr.detect_state(screen)
    assert result.state == GameState.HOME


def test_recognition_result_validation():
    """RecognitionResult 必须 confidence ∈ [0,1] 且 state 必须是 GameState。"""
    from recognition.types import RecognitionResult
    r = RecognitionResult(state=GameState.HOME, confidence=0.5, method="x")
    assert r.confidence == 0.5
    with pytest.raises(ValueError):
        RecognitionResult(state=GameState.HOME, confidence=1.5, method="x")
    with pytest.raises(ValueError):
        RecognitionResult(state=GameState.HOME, confidence=-0.1, method="x")
    with pytest.raises(TypeError):
        RecognitionResult(state="HOME", confidence=0.5, method="x")


def test_is_recognized():
    from recognition.types import RecognitionResult
    assert RecognitionResult(state=GameState.HOME, confidence=0.5, method="x").is_recognized() is True
    assert RecognitionResult(state=GameState.UNKNOWN, confidence=0.0, method="x").is_recognized() is False


def test_to_dict():
    from recognition.types import RecognitionResult
    d = RecognitionResult(state=GameState.HOME, confidence=0.9, method="x").to_dict()
    assert d["state"] == "HOME"
    assert d["confidence"] == 0.9
    assert d["method"] == "x"
    assert "timestamp" in d


# ============================================================
# P6-REAL-02: PageRecognizer 健壮性
# ============================================================


def test_detect_state_with_templates_root_not_exist(tmp_path):
    """P6-REAL-02: 模板根目录完全不存在 → UNKNOWN + empty_templates, 不抛错。"""
    missing_root = tmp_path / "no_such_templates_dir"
    pr = PageRecognizer(missing_root)
    rng = np.random.default_rng(seed=0)
    screen = rng.integers(0, 256, size=(800, 1280, 3), dtype=np.uint8)
    result = pr.detect_state(screen)
    assert result.state == GameState.UNKNOWN
    assert result.confidence == 0.0
    # 全部 state 目录都「不存在」时,也应该用 empty_templates method
    assert result.method == "fallback:empty_templates"


def test_detect_state_warning_deduplicated(tmp_path):
    """P6-REAL-02: 空模板目录的 warning 每个 state 只打一次,后续 detect 不再 warning。

    通过白盒检查 _warned_empty_states 集合的去重行为(不依赖 loguru log 输出)。
    """
    root = tmp_path / "templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (root / state.value).mkdir(parents=True)
        # HOME / LOADING 留空,POPUP 放一张不匹配模板
    tpl = np.full((30, 30, 3), 0, dtype=np.uint8)
    cv2.imwrite(str(root / "POPUP" / "x.png"), tpl)

    pr = PageRecognizer(root)
    screen = np.full((800, 1280, 3), 200, dtype=np.uint8)

    # 第一次调用 → HOME / LOADING 应被标记
    pr.detect_state(screen)
    assert "HOME" in pr._warned_empty_states
    assert "LOADING" in pr._warned_empty_states
    first_count = len(pr._warned_empty_states)

    # 第二次调用 → warned 集合不应再增长(去重生效)
    pr.detect_state(screen)
    assert len(pr._warned_empty_states) == first_count


def test_detect_state_clears_warning_after_template_added(tmp_path):
    """P6-REAL-02: 模板加入后,下次 detect 应清掉 warned 标记(可重复状态切换)。"""
    root = tmp_path / "templates"
    (root / "HOME").mkdir(parents=True)
    pr = PageRecognizer(root)
    screen = np.full((800, 1280, 3), 200, dtype=np.uint8)
    pr.detect_state(screen)
    assert "HOME" in pr._warned_empty_states

    # 用户中途放入模板
    tpl = np.full((40, 40, 3), 30, dtype=np.uint8)
    cv2.rectangle(tpl, (5, 5), (35, 35), (200, 100, 50), thickness=-1)
    cv2.imwrite(str(root / "HOME" / "main.png"), tpl)
    pr.detect_state(screen)
    # warned 标记应被清掉
    assert "HOME" not in pr._warned_empty_states


def test_detect_state_handles_mixed_states_some_empty_some_with_templates(tmp_path):
    """P6-REAL-02: 部分 state 有模板,部分没有 → no_match(不是 empty_templates)。"""
    root = tmp_path / "templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (root / state.value).mkdir(parents=True)
    # POPUP 放一个和 screen 完全无关的随机模板(noise,屏幕里绝不会有)
    rng = np.random.default_rng(seed=999)
    unrelated = rng.integers(0, 256, size=(100, 100, 3), dtype=np.uint8)
    cv2.imwrite(str(root / "POPUP" / "x.png"), unrelated)

    pr = PageRecognizer(root, threshold=0.999)  # 极高阈值,任何 noise 模板都不会匹配
    screen = np.full((800, 1280, 3), 200, dtype=np.uint8)  # 纯色屏
    result = pr.detect_state(screen)
    assert result.state == GameState.UNKNOWN
    assert result.method == "fallback:no_match"


def test_detect_state_picks_highest_confidence_across_states(tmp_path):
    """P6-REAL-02: 多个 state 都命中,选 confidence 最高的(跨 state 取最佳)。"""
    root = tmp_path / "templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (root / state.value).mkdir(parents=True)

    rng = np.random.default_rng(seed=1)
    screen = rng.integers(0, 256, size=(800, 1280, 3), dtype=np.uint8)
    # HOME 模板 = screen[200:300, 200:400](完美匹配)
    home_tpl = screen[200:300, 200:400].copy()
    cv2.imwrite(str(root / "HOME" / "main.png"), home_tpl)
    # POPUP 模板在屏幕里不存在
    popup_tpl = np.full((30, 30, 3), 0, dtype=np.uint8)
    cv2.imwrite(str(root / "POPUP" / "x.png"), popup_tpl)
    # LOADING 模板 — 低置信度
    load_tpl = np.full((30, 30, 3), 100, dtype=np.uint8)
    cv2.imwrite(str(root / "LOADING" / "y.png"), load_tpl)

    pr = PageRecognizer(root, threshold=0.5)
    result = pr.detect_state(screen)
    assert result.state == GameState.HOME
    assert result.confidence > 0.9


def test_detect_state_corrupt_template_handled(tmp_path):
    """P6-REAL-02: 损坏的 PNG 模板(0 字节或非 PNG) → silent skip, 不影响其他模板。"""
    root = tmp_path / "templates"
    for state in (GameState.HOME, GameState.POPUP, GameState.LOADING):
        (root / state.value).mkdir(parents=True)

    # HOME 目录放一个损坏 PNG(0 字节)
    (root / "HOME" / "corrupt.png").write_bytes(b"")
    # HOME 再放一个有效模板
    good_tpl = np.full((50, 50, 3), 200, dtype=np.uint8)
    cv2.rectangle(good_tpl, (5, 5), (45, 45), (50, 100, 200), thickness=-1)
    cv2.imwrite(str(root / "HOME" / "good.png"), good_tpl)

    pr = PageRecognizer(root, threshold=0.5)
    screen = np.full((800, 1280, 3), 200, dtype=np.uint8)
    # 屏幕里贴上 good 模板
    screen[100:150, 100:150] = good_tpl

    result = pr.detect_state(screen)
    # 损坏模板被 silent skip,good 模板应该能命中
    assert result.state == GameState.HOME
    assert result.confidence > 0.9
    # corrupt 路径被记录
    assert any("corrupt" in k for k in pr._matcher._warned_corrupt)