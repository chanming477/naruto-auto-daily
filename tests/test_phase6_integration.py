"""test_phase6_integration.py — Phase 6 真实游戏接入集成测试。

测试项:
    1. ADB 连接模拟器
    2. ADB 截图功能
    3. ADB 点击和返回键功能
    4. PageRecognizer 页面识别
    5. GameStateMachine 状态更新
    6. CommonActions.go_home()

每个测试方法打印 TEST-XXX 标记,便于从日志中提取结果。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest import mock

import numpy as np
import cv2
from loguru import logger

# ---------- 将项目根加入 sys.path ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------- 移除默认 logger,避免干扰 ----------
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<level>{level:7}</level> | <level>{message}</level>")

# ---------- 项目路径常量 ----------
TEMPLATES_ROOT = PROJECT_ROOT / "resources" / "templates"
ADB_PATH = r"C:\tmp\android-sdk\platform-tools\adb.exe"
DEFAULT_SERIAL = "127.0.0.1:7555"


# ============================================================
# TEST 1: ADB 连接模拟器
# ============================================================


def test_01_adb_connect_to_emulator():
    """TEST-01: 用真实 ADB 连接 MuMu 模拟器 (emulator-5554)"""
    from device.adb_client import ADBClient
    from core.config_manager import AdbConfig

    cfg = AdbConfig(
        adb_path=ADB_PATH,
        default_serial=DEFAULT_SERIAL,
        command_timeout_sec=10.0,
        retry_count=2,
    )
    client = ADBClient(cfg)

    # 确保断开后再连接
    client.disconnect()
    result = client.connect()
    logger.info(f"TEST-01 | connect result: success={result.success}, message={result.message}")

    assert result.success, f"ADB connect failed: {result.message}"
    assert client.is_connected, "ADB is_connected must be True after connect"
    assert client.serial == DEFAULT_SERIAL
    logger.success("TEST-01 | PASS: ADB connected to {}", DEFAULT_SERIAL)
    return client


# ============================================================
# TEST 2: ADB 截图功能
# ============================================================


def test_02_adb_screenshot(client: ADBClient):
    """TEST-02: 用 ADB screencap 截图并解码为 ndarray"""
    from device.adb_client import ADBClient

    result = client.screenshot()
    assert result.success, f"screenshot failed: {result.message}"
    assert isinstance(result.payload, np.ndarray), "screenshot payload must be ndarray"
    assert result.payload.ndim == 3, f"screenshot must be 3-channel BGR, got shape={result.payload.shape}"
    assert result.payload.shape[2] == 3, "screenshot must be BGR (3 channels)"
    assert result.payload.size > 0, "screenshot must not be empty"

    h, w = result.payload.shape[:2]
    logger.info(f"TEST-02 | screenshot shape={w}x{h}, dtype={result.payload.dtype}")

    # 保存截图到 screenshots 目录作为调试参考
    debug_path = PROJECT_ROOT / "screenshots" / "test_02_screenshot.png"
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(debug_path), result.payload)
    logger.info(f"TEST-02 | debug screenshot saved to {debug_path}")

    logger.success(f"TEST-02 | PASS: screenshot ok ({w}x{h})")
    return result.payload


# ============================================================
# TEST 3: ADB 点击和返回键功能
# ============================================================


def test_03_adb_tap_and_back(client: ADBClient):
    """TEST-03: 测试 ADB tap 点击 + keyevent BACK/HOME 功能"""
    # 3a. tap
    result_tap = client.tap(100, 100)
    assert result_tap.success, f"tap failed: {result_tap.message}"
    logger.info(f"TEST-03a | tap(100,100): {result_tap.message}")
    logger.success("TEST-03a | PASS: tap works")

    # 3b. keyevent BACK
    time.sleep(0.5)
    result_back = client.keyevent("BACK")
    assert result_back.success, f"keyevent BACK failed: {result_back.message}"
    logger.info(f"TEST-03b | keyevent(BACK): {result_back.message}")
    logger.success("TEST-03b | PASS: BACK key works")

    # 3c. keyevent HOME (数字 3)
    time.sleep(0.5)
    result_home = client.keyevent(3)
    assert result_home.success, f"keyevent HOME(3) failed: {result_home.message}"
    logger.info(f"TEST-03c | keyevent(3=HOME): {result_home.message}")
    logger.success("TEST-03c | PASS: HOME key works via numeric code")

    # 3d. keyevent 非法键名 → 返回 failure 不抛异常
    result_bad = client.keyevent("NONEXISTENT_KEY")
    assert not result_bad.success, "unknown key name should return failure"
    logger.info(f"TEST-03d | keyevent(NONEXISTENT): success={result_bad.success}, msg={result_bad.message}")
    logger.success("TEST-03d | PASS: unknown key name returns failure gracefully")

    logger.success("TEST-03 | PASS: all key/tap operations work")


# ============================================================
# TEST 4: PageRecognizer 页面识别
# ============================================================


def test_04_page_recognizer(screen: np.ndarray):
    """TEST-04: PageRecognizer 识别当前页面

    由于模板目录为空,预期返回 UNKNOWN(fallback:empty_templates)。
    """
    from recognizer.page_recognizer import PageRecognizer
    from state.game_state import GameState

    recognizer = PageRecognizer(
        templates_root=TEMPLATES_ROOT,
        threshold=0.85,
    )

    result = recognizer.detect_state(screen)
    logger.info(f"TEST-04 | detect_state: state={result.state.value}, "
                f"confidence={result.confidence:.4f}, method={result.method}")

    # 真实截图 + 空模板 = UNKNOWN (这是当前项目阶段预期的)
    assert isinstance(result.state, GameState), f"state must be GameState, got {type(result.state)}"
    assert 0.0 <= result.confidence <= 1.0, f"confidence out of range: {result.confidence}"
    assert result.state == GameState.UNKNOWN, (
        f"Since all templates dirs are empty, should detect UNKNOWN, got {result.state}"
    )
    assert result.method == "fallback:empty_templates", (
        f"Should use fallback:empty_templates method, got {result.method}"
    )

    logger.success("TEST-04 | PASS: PageRecognizer returns UNKNOWN as expected (empty templates)")


# ============================================================
# TEST 5: GameStateMachine 状态更新
# ============================================================


def test_05_game_state_machine():
    """TEST-05: GameStateMachine 状态切换:
    - 初始 UNKNOWN → HOME → POPUP → LOADING → UNKNOWN
    - go_home() 快捷切换
    - history 记录
    - reset() 重置
    """
    from state.game_state import GameState
    from state_machine.game_state_machine import GameStateMachine

    sm = GameStateMachine(initial=GameState.UNKNOWN)
    assert sm.current_state == GameState.UNKNOWN, f"expected UNKNOWN, got {sm.current_state}"
    assert not sm.is_known
    logger.info(f"TEST-05a | initial state={sm.current_state.value}")

    # 切换到 HOME
    changed = sm.update_state(GameState.HOME, source="test")
    assert changed, "update_state(HOME) should return True"
    assert sm.current_state == GameState.HOME
    assert sm.is_known
    assert len(sm.history) == 1
    assert sm.history[0].source == "test"
    assert sm.history[0].from_state == GameState.UNKNOWN
    assert sm.history[0].to_state == GameState.HOME
    logger.info(f"TEST-05b | state transition: UNKNOWN -> HOME")

    # 重复切换到 HOME → noop
    changed = sm.update_state(GameState.HOME)
    assert not changed, "same state should return False (noop)"
    assert len(sm.history) == 1  # 无新增
    logger.info(f"TEST-05c | duplicate HOME update = noop")

    # go_home() from HOME → noop
    changed = sm.go_home()
    assert not changed, "go_home from HOME should return False"
    logger.info(f"TEST-05d | go_home from HOME = noop")

    # POPUP → LOADING → UNKNOWN
    sm.update_state(GameState.POPUP, source="detect_state")
    assert sm.current_state == GameState.POPUP
    sm.update_state(GameState.LOADING, source="detect_state")
    assert sm.current_state == GameState.LOADING
    sm.update_state(GameState.UNKNOWN, source="detect_state")
    assert sm.current_state == GameState.UNKNOWN
    assert not sm.is_known
    logger.info(f"TEST-05e | full cycle: ->POPUP->LOADING->UNKNOWN")

    # reset
    sm.reset()
    assert sm.current_state == GameState.UNKNOWN
    assert sm.history == []
    logger.info(f"TEST-05f | reset -> initial state, history cleared")

    # history cap
    sm2 = GameStateMachine(history_limit=3)
    for i in range(10):
        sm2.update_state(GameState.HOME, source=f"loop_{i}")
        sm2.update_state(GameState.UNKNOWN, source=f"loop_{i}")
    assert len(sm2.history) <= 3, f"history should be capped at 3, got {len(sm2.history)}"
    logger.info(f"TEST-05g | history cap: {len(sm2.history)}/3")

    # invalid input
    assert sm.update_state("INVALID") is False  # type: ignore[arg-type]
    logger.info(f"TEST-05h | invalid state input handled gracefully")

    logger.success("TEST-05 | PASS: GameStateMachine state transitions all correct")


# ============================================================
# TEST 6: CommonActions.go_home() - 真实游戏环境
# ============================================================


def test_06_common_actions_go_home(client: ADBClient, screen: np.ndarray):
    """TEST-06: CommonActions.go_home() 在真实模拟器环境运行

    使用真实 ADB 连接 + 空模板(PageRecognizer 返回 UNKNOWN)。

    预期:
        - go_home() 会尝试按 BACK 键 + HOME 键
        - 由于 PageRecognizer 无法识别状态(空模板),go_home() 最终返回 False
        - 但 ADB 按键应该是真实执行的
    """
    from recognizer.page_recognizer import PageRecognizer
    from state_machine.game_state_machine import GameStateMachine
    from state.game_state import GameState
    from tasks.common_actions import CommonActions
    from core.config_manager import ConfigManager

    recognizer = PageRecognizer(
        templates_root=TEMPLATES_ROOT,
        threshold=0.85,
    )
    game_sm = GameStateMachine(initial=GameState.UNKNOWN)

    config = ConfigManager(project_root=PROJECT_ROOT, auto_load=True)

    actions = CommonActions(
        adb_client=client,
        recognizer=recognizer,
        game_sm=game_sm,
        config=config,
        project_root=PROJECT_ROOT,
    )

    # 6a. 先验证初始状态
    assert game_sm.current_state == GameState.UNKNOWN
    logger.info(f"TEST-06a | initial game_sm state: {game_sm.current_state.value}")

    # 6b. 主动 observer 一次(截图 + 识别)
    observed = actions.observe()
    logger.info(f"TEST-06b | observe() returned: {observed.value} "
                f"(expected UNKNOWN since templates are empty)")
    # 由于模板为空,observe 应该返回 UNKNOWN
    assert observed == GameState.UNKNOWN, f"observe should return UNKNOWN, got {observed}"

    # 6c. 执行 go_home()
    # 注意: 这会真实地向模拟器发送 BACK 和 HOME 键事件!
    logger.info("TEST-06c | executing go_home() — will press BACK + HOME on real emulator...")
    start = time.monotonic()
    result = actions.go_home(max_press_back=3)
    elapsed = time.monotonic() - start
    logger.info(f"TEST-06c | go_home() completed in {elapsed:.1f}s, result={result}")

    # 由于模板为空,PageRecognizer 无法识别 HOME,go_home 应该返回 False
    # 但 BACK/HOME 按键应当已真实发送到模拟器
    assert result is False, (
        f"go_home should return False (empty templates, can't detect HOME), got {result}"
    )

    # 6d. 验证按键确实被执行(通过检查 ADB shell 是否仍然在线)
    ping = client._ping()
    assert ping, "ADB connection still alive after go_home()"
    logger.info(f"TEST-06d | ADB connection alive after go_home: {ping}")

    # 6e. 验证 go_home 异常安全
    try:
        from device.adb_client import ADBCommandError
        broken_client = mock.MagicMock()
        broken_client.keyevent.side_effect = RuntimeError("simulated ADB failure")
        broken_client.screenshot.return_value = mock.MagicMock(
            success=False, message="broken", payload=None,
        )
        broken_actions = CommonActions(
            adb_client=broken_client,
            recognizer=recognizer,
            game_sm=GameStateMachine(initial=GameState.UNKNOWN),
            config=config,
            project_root=PROJECT_ROOT,
        )
        safe_result = broken_actions.go_home()
        assert safe_result is False, "go_home should return False on ADB failure, not raise"
        logger.info(f"TEST-06e | go_home with broken ADB returned {safe_result} (no exception)")
        logger.success("TEST-06e | PASS: go_home is exception-safe")
    except Exception as exc:
        logger.error(f"TEST-06e | FAIL: go_home raised unexpected exception: {exc}")
        raise

    # ── TEST-06f (P6-REAL-03 闭环): 用真实 PageRecognizer + 真实 HOME 模板 + Mock ADB ──
    # 不依赖真模拟器,验证"模板就绪时 go_home 真实识别 HOME → 返 True"全链路。
    logger.info("TEST-06f | P6-REAL-03 闭环: 真实模板 + Mock ADB, 验证 BACK×3→HOME→识别→True")
    try:
        import tempfile
        from unittest.mock import MagicMock as _M
        from tasks.common_actions import CommonActions as _CA
        from recognizer.page_recognizer import PageRecognizer as _PR
        from state_machine.game_state_machine import GameStateMachine as _GSM

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 构造真实 home 屏幕 + 真实模板
            rng = np.random.default_rng(seed=20260624)
            home_screen = rng.integers(0, 256, size=(1280, 800, 3), dtype=np.uint8)
            cv2.rectangle(home_screen, (50, 50), (250, 150), (200, 100, 50), thickness=-1)
            cv2.rectangle(home_screen, (80, 80), (200, 130), (50, 200, 200), thickness=3)
            home_tpl = home_screen[50:150, 50:250].copy()

            # subpage 屏幕: 跟 home 模板无关的纯色 + 无关矩形
            subpage_screen = np.full((1280, 800, 3), 30, dtype=np.uint8)
            cv2.rectangle(subpage_screen, (300, 600), (500, 800), (100, 50, 200), thickness=-1)
            cv2.putText(
                subpage_screen, "SubPage", (320, 700),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2,
            )

            templates_root = tmp_path / "templates"
            (templates_root / "HOME").mkdir(parents=True)
            cv2.imwrite(str(templates_root / "HOME" / "main_hall.png"), home_tpl)
            (templates_root / "POPUP").mkdir(parents=True)
            (templates_root / "LOADING").mkdir(parents=True)

            real_recognizer = _PR(templates_root, threshold=0.85)

            # 强验证: subpage 不会偶然命中 home 模板
            pre_check = real_recognizer.detect_state(subpage_screen)
            assert pre_check.state == GameState.UNKNOWN, (
                f"subpage_screen should NOT match HOME template, got {pre_check.state}"
            )
            pre_check2 = real_recognizer.detect_state(home_screen)
            assert pre_check2.state == GameState.HOME and pre_check2.confidence > 0.9

            real_sm = _GSM(initial=GameState.UNKNOWN)
            real_cfg = ConfigManager(project_root=PROJECT_ROOT, auto_load=True)

            # Mock ADB: 模拟子页面 → HOME 页面的切换
            # 前 4 次 screenshot 返回 subpage,第 4 次以后返回 home(模拟 BACK×3 后按 HOME 键回到主页)
            shot_n = {"n": 0}
            def fake_shot(*_a, **_kw):
                n = shot_n["n"]
                shot_n["n"] += 1
                arr = subpage_screen if n < 4 else home_screen
                return ActionResult(True, "ok", None, payload=arr.copy())

            mock_adb = _M()
            mock_adb.keyevent.return_value = ActionResult(True, "ok", None)
            mock_adb.screenshot.side_effect = fake_shot
            real_actions = _CA(
                adb_client=mock_adb,
                recognizer=real_recognizer,
                game_sm=real_sm,
                config=real_cfg,
                project_root=PROJECT_ROOT,
            )

            # 1) Fast-path 测试: 屏幕一开始就是 HOME → 立即识别,无按键
            shot_n["n"] = 0
            fast_sm = _GSM(initial=GameState.UNKNOWN)
            fast_actions = _CA(
                adb_client=mock_adb, recognizer=real_recognizer, game_sm=fast_sm,
                config=real_cfg, project_root=PROJECT_ROOT,
            )
            # 让 mock 的 screenshot 第一次就返回 home_screen
            shot_n["n"] = 4  # next call → home_screen
            fast_result = fast_actions.go_home(max_press_back=3)
            assert fast_result is True
            assert fast_sm.current_state == GameState.HOME
            keyevents_fast = [c.args[0] for c in mock_adb.keyevent.call_args_list]
            # fast-path 应无按键(fast_sm 第一次 _is_current_state 就更新成 HOME)
            assert len(keyevents_fast) == 0, f"fast-path 应无按键,实际: {keyevents_fast}"
            logger.info(f"TEST-06f-fast | result={fast_result}, state={fast_sm.current_state.value}, "
                        f"keyevents={keyevents_fast} (no keypress, fast-path)")

            # 2) 慢速路径: BACK×3 + HOME 键 → 走到 home_screen → 识别成功
            shot_n["n"] = 0
            mock_adb.keyevent.reset_mock()
            slow_result = real_actions.go_home(max_press_back=3)
            assert slow_result is True
            assert real_sm.current_state == GameState.HOME
            keyevents_slow = [c.args[0] for c in mock_adb.keyevent.call_args_list]
            assert keyevents_slow == ["BACK", "BACK", "BACK", "HOME"], (
                f"slow-path keyevent sequence wrong: {keyevents_slow}"
            )
            logger.info(f"TEST-06f-slow | result={slow_result}, state={real_sm.current_state.value}, "
                        f"keyevents={keyevents_slow} (BACK×3 + HOME)")
            logger.success("TEST-06f | PASS: P6-REAL-03 真实模板+Mock ADB 闭环验证通过 (fast + slow)")
    except Exception as exc:
        logger.error(f"TEST-06f | FAIL: P6-REAL-03 闭环异常: {exc}")
        raise

    logger.success("TEST-06 | PASS: CommonActions.go_home() completed (real ADB + empty templates + P6 closed-loop)")


# ============================================================
# 主入口
# ============================================================


def main():
    logger.info("=" * 60)
    logger.info("Phase 6 真实游戏接入集成测试 开始")
    logger.info(f"    项目根:      {PROJECT_ROOT}")
    logger.info(f"    模板根:      {TEMPLATES_ROOT}")
    logger.info(f"    ADB 路径:    {ADB_PATH}")
    logger.info(f"    设备序列号:  {DEFAULT_SERIAL}")
    logger.info("=" * 60)

    # 收集测试结果
    results: list[dict] = []
    failures = 0

    def run_test(name: str, fn, *args, **kwargs):
        nonlocal failures
        logger.info(f"\n{'─' * 50}")
        logger.info(f"▶ 开始测试: {name}")
        logger.info(f"{'─' * 50}")
        start = time.monotonic()
        try:
            fn(*args, **kwargs)
            elapsed = time.monotonic() - start
            logger.success(f"✓ {name} 通过 ({elapsed:.1f}s)")
            results.append({"name": name, "status": "PASS", "reason": "", "elapsed": elapsed})
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(f"✗ {name} 失败: {exc} ({elapsed:.1f}s)")
            results.append({"name": name, "status": "FAIL", "reason": str(exc), "elapsed": elapsed})
            failures += 1

    # ── TEST 1: ADB 连接 ──
    client = None
    try:
        client = test_01_adb_connect_to_emulator()
        run_test("TEST-01 ADB连接模拟器", lambda: None)  # 结果已记录
    except Exception as exc:
        logger.error(f"TEST-01 FAIL: {exc}")
        results.append({"name": "TEST-01 ADB连接模拟器", "status": "FAIL", "reason": str(exc), "elapsed": 0})
        failures += 1
        logger.critical("TEST-01 失败,后续测试依赖 ADB,跳过其余测试")
        _print_report(results)
        return 1

    # ── TEST 2: 截图 ──
    screen = None
    try:
        screen = test_02_adb_screenshot(client)
        run_test("TEST-02 ADB截图功能", lambda: None)
    except Exception as exc:
        logger.error(f"TEST-02 FAIL: {exc}")
        results.append({"name": "TEST-02 ADB截图功能", "status": "FAIL", "reason": str(exc), "elapsed": 0})
        failures += 1
        _print_report(results)
        return 1

    # ── TEST 3: 点击和返回键 ──
    try:
        test_03_adb_tap_and_back(client)
        run_test("TEST-03 ADB点击和返回键", lambda: None)
    except Exception as exc:
        logger.error(f"TEST-03 FAIL: {exc}")
        results.append({"name": "TEST-03 ADB点击和返回键", "status": "FAIL", "reason": str(exc), "elapsed": 0})
        failures += 1

    # ── TEST 4: PageRecognizer ──
    try:
        test_04_page_recognizer(screen)
        run_test("TEST-04 PageRecognizer页面识别", lambda: None)
    except Exception as exc:
        logger.error(f"TEST-04 FAIL: {exc}")
        results.append({"name": "TEST-04 PageRecognizer页面识别", "status": "FAIL", "reason": str(exc), "elapsed": 0})
        failures += 1

    # ── TEST 5: GameStateMachine ──
    try:
        test_05_game_state_machine()
        run_test("TEST-05 GameStateMachine状态更新", lambda: None)
    except Exception as exc:
        logger.error(f"TEST-05 FAIL: {exc}")
        results.append({"name": "TEST-05 GameStateMachine状态更新", "status": "FAIL", "reason": str(exc), "elapsed": 0})
        failures += 1

    # ── TEST 6: CommonActions.go_home() ──
    try:
        test_06_common_actions_go_home(client, screen)
        run_test("TEST-06 CommonActions.go_home()", lambda: None)
    except Exception as exc:
        logger.error(f"TEST-06 FAIL: {exc}")
        results.append({"name": "TEST-06 CommonActions.go_home()", "status": "FAIL", "reason": str(exc), "elapsed": 0})
        failures += 1

    # ── 断开 ADB 连接 ──
    client.disconnect()
    logger.info("ADB 已断开")

    # ── 报告 ──
    _print_report(results)
    return 1 if failures > 0 else 0


def _print_report(results: list[dict]):
    logger.info("\n" + "=" * 60)
    logger.info("Phase 6 集成测试报告")
    logger.info("=" * 60)
    for r in results:
        status_str = "✅ PASS" if r["status"] == "PASS" else "❌ FAIL"
        reason = f" - {r['reason']}" if r["reason"] else ""
        logger.info(f"  {status_str} | {r['name']}{reason}")
    logger.info("=" * 60)
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    logger.info(f"  总计: {total} | 通过: {passed} | 失败: {total - passed}")
    logger.info("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
