"""真机 dry-run v2: 用 PIL 保存截图 + 视觉分析 ROI."""
from __future__ import annotations
import sys, time, pathlib, datetime
PROJECT_ROOT = pathlib.Path(r"D:\火影自动日常")
sys.path.insert(0, str(PROJECT_ROOT))

ADB_PATH = r"D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe"
SERIAL = "127.0.0.1:16384"

import numpy as np
import cv2
from PIL import Image
from loguru import logger

LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOGS_DIR / f"dryrun_v2_{datetime.datetime.now().strftime('%H%M%S')}.log"
logger.add(str(log_file), encoding="utf-8", level="DEBUG")

from device.adb_client import ADBClient

adb = ADBClient(adb_path=ADB_PATH, serial=SERIAL)
conn = adb.connect()
print(f"[adb] connect: success={conn.success}")

SNAP_DIR = PROJECT_ROOT / "screenshots" / "dryrun_v2"
SNAP_DIR.mkdir(parents=True, exist_ok=True)

# 直接拿原始截图, 全屏保存
def snap(label):
    r = adb.screenshot()
    if not r.success or r.payload is None:
        return None
    img = r.payload  # BGR uint8
    out = SNAP_DIR / f"{label}.png"
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    pil.save(str(out))
    print(f"  saved: {out.name} ({img.shape})")
    return img

# 抓 3 张: 当前主页 / 点 ninja_guide 后 / 兜底后
img0 = snap("00_home_initial")

# 在 1920x1080 截图上画 ROI 框, 看每个 ROI 包含什么
def draw_rois(img, rois_dict, out_path):
    vis = img.copy()
    colors = {
        'ninja_guide': (0, 255, 0),
        'group_list_no_group': (255, 0, 0),
        'group_gameplay_btn': (0, 255, 255),
        'go_to_signin': (255, 0, 255),
        'notice_x': (0, 165, 255),
        'copper_pray': (255, 255, 0),
    }
    for name, (x, y, w, h) in rois_dict.items():
        c = colors.get(name, (255, 255, 255))
        cv2.rectangle(vis, (x, y), (x + w, y + h), c, 3)
        cv2.putText(vis, name, (x + 5, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2)
    cv2.imwrite(str(out_path), vis)
    print(f"  ROI 框图: {out_path.name}")

rois = {
    'ninja_guide': (900, 580, 220, 160),
    'group_list_no_group': (94, 30, 474, 173),
    'group_gameplay_btn': (44, 382, 177, 118),
    'go_to_signin': (239, 533, 178, 144),
    'notice_x': (706, 157, 274, 172),
    'copper_pray': (476, 542, 200, 80),
}

if img0 is not None:
    draw_rois(img0, rois, SNAP_DIR / "00_home_with_rois.png")

# 在主页 ROI 上直接做模板匹配, 报告结果
from recognition.template_matcher import TemplateMatcher, load_template
matcher = TemplateMatcher()

# 测试 find_ninja_guide 用的 3 个模板 (前 2 个不存在)
tests = [
    ("shared/ninja_guide_v3.png", (900, 580, 220, 160)),
    ("group/group_list.png", (94, 30, 474, 173)),
    ("group/group_gameplay_undone.png", (44, 382, 177, 118)),
    ("group/group_ac_undone.png", (44, 382, 177, 118)),
]
print()
print("=" * 60)
print("主页上 ROI 模板匹配结果")
print("=" * 60)
for tpl_name, roi in tests:
    p = PROJECT_ROOT / "resources" / "templates" / "actions" / tpl_name
    if not p.exists():
        print(f"  {tpl_name}: NOT FOUND")
        continue
    img = load_template(p)
    if img is None:
        print(f"  {tpl_name}: load_template returned None")
        continue
    print(f"  {tpl_name}: template shape={img.shape}, ROI={roi}")
    # 全图匹配(不限 ROI)看哪命中
    r = matcher.match(p, img0, threshold=0.7)
    if r is not None:
        print(f"    -> FULL match: pos=({r.x},{r.y}) conf={r.confidence:.3f}")
    else:
        print(f"    -> FULL match: NONE (threshold=0.7)")
    # ROI 限制内匹配
    r2 = matcher.match(p, img0, roi=roi, threshold=0.7)
    if r2 is not None:
        print(f"    -> ROI match: pos=({r2.x},{r2.y}) conf={r2.confidence:.3f}")
    else:
        print(f"    -> ROI match: NONE")