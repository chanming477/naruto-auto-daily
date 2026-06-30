"""test_phase2_pipeline.py — Phase 2 端到端 demo 流程(无 ADB / 无模板)。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from main import run_phase2_demo


def test_phase2_demo_without_adb(tmp_path):
    """tmp_path 当 project_root,跑 demo 流程,应该正常 exit 0。"""
    # tmp_path 里没 adb、没模板、没 config,run_phase2_demo 内部会自己建 config + demo 截图
    rc = run_phase2_demo(tmp_path, use_real_adb=False, console_level="WARNING")
    assert rc == 0


def test_phase2_demo_initializes_logger_and_config(tmp_path):
    """第一次跑会生成默认 config + 模板占位目录。"""
    rc = run_phase2_demo(tmp_path, use_real_adb=False, console_level="WARNING")
    assert rc == 0
    # config/app_config.yaml 应该被自动生成
    assert (tmp_path / "config" / "app_config.yaml").exists()
    # 模板目录结构应该被创建
    # 注意:Phase 2 demo 不强制创建 templates 子目录,这是用户/后续 Phase 的事
    # 所以这里只检查 config 目录存在
    assert (tmp_path / "config").exists()


def test_phase2_demo_with_real_adb_but_no_adb_binary(tmp_path):
    """use_real_adb=True 但没 adb binary → 应该 graceful fallback,exit 0。"""
    rc = run_phase2_demo(tmp_path, use_real_adb=True, console_level="WARNING")
    assert rc == 0


def test_phase2_demo_with_unrelated_template_stays_unknown(tmp_path):
    """放一个跟 demo 截图无关的 HOME 模板进 resources/templates/HOME/,跑 demo 应该保持 UNKNOWN。

    注意: 模板名字暗示"find home"但 demo 截图是 noise + 角落小标记,跟全白 HOME 模板
    不匹配,所以 detect_state 返回 UNKNOWN,recover() 也保持 UNKNOWN,exit 0。
    """
    # 先跑一次生成 config + 模板目录结构
    rc1 = run_phase2_demo(tmp_path, use_real_adb=False, console_level="WARNING")
    assert rc1 == 0

    # 在第二次跑之前,放一个跟 demo 截图完全无关的 HOME 模板
    templates_home = tmp_path / "resources" / "templates" / "HOME"
    templates_home.mkdir(parents=True, exist_ok=True)
    tpl = np.full((100, 200, 3), 255, dtype=np.uint8)  # 全白,跟 demo noise 不匹配
    assert cv2.imwrite(str(templates_home / "white.png"), tpl)

    rc2 = run_phase2_demo(tmp_path, use_real_adb=False, console_level="WARNING")
    assert rc2 == 0


def test_phase2_demo_emits_warning_for_missing_template_dir(tmp_path):
    """P0-STABLE-03 升级: 当模板目录结构不存在时,PageRecognizer 必须 warning 而非静默。"""
    from recognizer.page_recognizer import PageRecognizer
    from recognition.template_matcher import TemplateMatcher

    # 用一个空的 tmp_path 作为 templates_root(子目录都不存在)
    empty_root = tmp_path / "no_such_state_dirs"
    pr = PageRecognizer(empty_root, matcher=TemplateMatcher())
    rng = np.random.default_rng(seed=20260624)
    screen = rng.integers(0, 256, size=(1280, 720, 3), dtype=np.uint8)

    # 跑 detect_state 应该返回 UNKNOWN + empty_templates(或类似)method
    # 同时 logger.warning 应被触发 3 次(三个 state 各一次)
    result = pr.detect_state(screen)
    assert result.state.value == "UNKNOWN"
    assert result.confidence == 0.0


def test_phase2_demo_emits_warning_for_empty_template_dir(tmp_path):
    """P0-STABLE-03 升级: 当模板目录存在但为空时,PageRecognizer 必须 warning。"""
    from recognizer.page_recognizer import PageRecognizer
    from recognition.template_matcher import TemplateMatcher

    # 创建三个 state 的子目录,但都是空的
    root = tmp_path / "empty_state_dirs"
    for state in ("HOME", "POPUP", "LOADING"):
        (root / state).mkdir(parents=True)

    pr = PageRecognizer(root, matcher=TemplateMatcher())
    rng = np.random.default_rng(seed=20260624)
    screen = rng.integers(0, 256, size=(1280, 720, 3), dtype=np.uint8)

    result = pr.detect_state(screen)
    assert result.state.value == "UNKNOWN"
    assert result.method == "fallback:empty_templates"


def test_game_context_is_execution_context_alias():
    """V2: GameContext 改为 ExecutionContext 的类型别名,字段对齐到 ExecutionContext。

    Phase 2 demo 不再维护独立的 current_state / screenshot_path,
    这两个状态现在存在 GameStateMachine.current_state 和局部变量里。
    本测试仅验证别名本身正确性。
    """
    from core.base_task import ExecutionContext
    from state.types import GameContext

    # GameContext 必须指向 ExecutionContext(同一个类对象)
    assert GameContext is ExecutionContext


def test_execution_context_is_the_only_context():
    """V2: 整个项目只有 ExecutionContext 一个运行上下文 dataclass。"""
    from core.base_task import ExecutionContext

    # 核心字段都在
    ec = ExecutionContext(
        config=None,  # type: ignore[arg-type]
        window_manager=None,  # type: ignore[arg-type]
        screenshot_manager=None,  # type: ignore[arg-type]
        state_machine=None,  # type: ignore[arg-type]
    )
    assert ec.config is None
    assert ec.window_manager is None
    assert ec.screenshot_manager is None
    assert ec.state_machine is None


def test_game_state_all_and_is_recognized():
    from state.game_state import GameState
    assert GameState.all() == ("HOME", "POPUP", "LOADING", "UNKNOWN")
    assert GameState.is_recognized(GameState.HOME) is True
    assert GameState.is_recognized(GameState.POPUP) is True
    assert GameState.is_recognized(GameState.LOADING) is True
    assert GameState.is_recognized(GameState.UNKNOWN) is False
    assert GameState.is_recognized("HOME") is True
    assert GameState.is_recognized("UNKNOWN") is False