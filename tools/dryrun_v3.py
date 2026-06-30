"""真机 dry-run v3: 验证 P0 补丁 + OCR 接入。

测试项:
    1. P0-1: ensure_game_in_foreground() 在游戏不在前台时拉起
    2. P0-2: pre_flight() 钩子在 BaseTask.execute() 早期执行
    3. P0-3: PIL 截图工具 save_image_pil 能用(cv2.imwrite 失败的场景)
    4. OCR: pipeline click_go_to_signin 和 try_pursuit_entry 走 OCR 路径
"""
from __future__ import annotations
import sys, time, pathlib, datetime

PROJECT_ROOT = pathlib.Path(r"D:\火影自动日常")
sys.path.insert(0, str(PROJECT_ROOT))

ADB_PATH = r"D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe"
SERIAL = "127.0.0.1:16384"

import numpy as np
from loguru import logger

LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOGS_DIR / f"dryrun_v3_{datetime.datetime.now().strftime('%H%M%S')}.log"
logger.add(str(log_file), encoding="utf-8", level="DEBUG")
logger.info("=== P0+OCR dry-run 启动 ===")

# 1) 测试 PIL 截图工具
print("=" * 60)
print("[Test 1] PIL 截图工具 save_image_pil")
print("=" * 60)
from core.screenshot_utils import save_image_pil

# 拿一张真机截图
from device.adb_client import ADBClient
adb = ADBClient(adb_path=ADB_PATH, serial=SERIAL)
r = adb.screenshot()
if not r.success or r.payload is None:
    print("FAIL: adb screenshot failed")
    sys.exit(1)
print(f"  截图 shape: {r.payload.shape}")

# cv2.imwrite 已知失败, PIL 替代
test_path = PROJECT_ROOT / "screenshots" / "dryrun_v3" / "test_pil.png"
ok = save_image_pil(r.payload, str(test_path))
print(f"  save_image_pil result: {ok}, exists: {test_path.exists()}")
if test_path.exists():
    print(f"  size: {test_path.stat().st_size} bytes")

# 2) 测试 ensure_game_in_foreground
print()
print("=" * 60)
print("[Test 2] CommonActions.ensure_game_in_foreground()")
print("=" * 60)
from unittest.mock import MagicMock
from tasks.common_actions import CommonActions
from state.game_state import GameState
from state_machine.game_state_machine import GameStateMachine
from recognizer.page_recognizer import PageRecognizer
from core.config_manager import ConfigManager

cfg = ConfigManager(PROJECT_ROOT, auto_load=True)
game_sm = GameStateMachine(initial=GameState.UNKNOWN)
recognizer = PageRecognizer(
    PROJECT_ROOT / "resources" / "templates",
    matcher=__import__('recognition.template_matcher', fromlist=['TemplateMatcher']).TemplateMatcher(cfg),
)
common = CommonActions(
    adb_client=adb,
    recognizer=recognizer,
    game_sm=game_sm,
    config=cfg,
    project_root=PROJECT_ROOT,
)

t0 = time.time()
fg_ok = common.ensure_game_in_foreground()
print(f"  ensure_game_in_foreground: {fg_ok} ({time.time()-t0:.2f}s)")

# 再用 dumpsys 验证游戏在前台
import subprocess
r = subprocess.run(
    [ADB_PATH, '-s', SERIAL, 'shell', 'dumpsys', 'window', 'windows'],
    capture_output=True, text=True, timeout=8,
)
for ln in r.stdout.split('\n'):
    if 'mCurrentFocus' in ln and 'KiHan' in ln:
        print(f"  mCurrentFocus: {ln.strip()[:200]}")
        break

# 3) 测试 OCR 在真机截图上的运行速度
print()
print("=" * 60)
print("[Test 3] OCR on real screenshot")
print("=" * 60)
from tasks.navigator import _get_ocr_engine
t0 = time.time()
engine = _get_ocr_engine()
print(f"  rapidocr 加载: {time.time()-t0:.2f}s")

# 重新拿截图(避免 r 被 subprocess 覆盖)
screen_for_ocr = adb.screenshot().payload
if engine and screen_for_ocr is not None:
    t0 = time.time()
    ocr_result, ocr_elapsed = engine(screen_for_ocr)
    print(f"  全屏 OCR: {time.time()-t0:.2f}s, 识别到 {len(ocr_result) if ocr_result else 0} 条")
    if ocr_result:
        # 显示前 15 条
        for item in ocr_result[:15]:
            try:
                box, text, conf = item
                print(f"    '{text}' (conf={conf:.2f})")
            except Exception:
                pass

    # OCR 找"组织"和"前往"
    print()
    print("=== OCR 找特定文字 ===")
    targets = ["组织", "前往", "追击", "签到", "奖励", "铜币", "宝箱", "活跃"]
    for target in targets:
        t0 = time.time()
        result_t, _ = engine(screen_for_ocr)
        elapsed = time.time() - t0
        found = False
        if result_t:
            for item in result_t:
                try:
                    box, text, conf = item
                    if target in str(text):
                        x_center = sum(pt[0] for pt in box) / 4
                        y_center = sum(pt[1] for pt in box) / 4
                        print(f"  '{target}' 命中 '{text}' @ ({x_center:.0f},{y_center:.0f}) conf={conf:.2f} ({elapsed:.2f}s)")
                        found = True
                        break
                except Exception:
                    continue
        if not found:
            print(f"  '{target}' 未命中 ({elapsed:.2f}s)")

# 4) 跑 pipeline (看 OCR 节点行为)
print()
print("=" * 60)
print("[Test 4] Pipeline dry-run (灰图 → 全部 on_error → verify_done)")
print("=" * 60)
from tasks.pipeline_runner import PipelineRunner
from tasks.group_signin_task import _build_group_signin_pipeline

runner = PipelineRunner(
    adb, PROJECT_ROOT,
    PROJECT_ROOT / "resources" / "templates" / "actions",
    logger,
    ref_width=1920, ref_height=1080,
)
nav = runner.make_navigator()
# 注入截图覆盖:返回真机截图
nav._capture = lambda: screen_for_ocr
pipe = _build_group_signin_pipeline(nav)

t0 = time.time()
result = nav.run(pipe, max_total_iterations=15, max_idle_iterations=4)
print(f"  success: {result.success}")
print(f"  last_node: {result.last_node}")
print(f"  iters: {result.total_iterations}")
print(f"  history: {'->'.join(result.history)}")
print(f"  elapsed: {time.time()-t0:.2f}s")

print()
print("=" * 60)
print("全部完成")
print("=" * 60)