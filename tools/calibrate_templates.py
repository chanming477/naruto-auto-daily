"""回到首页并截 6 张覆盖所有任务入口 ROI 的截图"""
import subprocess, time, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from device.adb_client import ADBClient
import cv2, numpy as np

adb_path = 'C:/tmp/android-sdk/platform-tools/adb.exe'
serial = '127.0.0.1:7555'
adb = ADBClient(adb_path=adb_path, serial=serial)

def screencap():
    out = subprocess.run([adb_path, '-s', serial, 'exec-out', 'screencap', '-p'], capture_output=True).stdout
    arr = np.frombuffer(out, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

def save(name, img):
    path = 'C:/tmp/phase6_' + name + '.png'
    cv2.imwrite(path, img)
    print('Saved ' + path + ' (' + str(img.shape) + ', ' + str(os.path.getsize(path)) + ' bytes)')

# 1. 回到首页
print('=== 回到首页 ===')
for _ in range(8):
    subprocess.run([adb_path, '-s', serial, 'shell', 'input', 'keyevent', '4'])  # KEYCODE_BACK
    time.sleep(0.5)
time.sleep(2)
home = screencap()
save('home_full', home)

# 2. 截 ROI 区域（参考 narutomobile 源码 ROI）
print('\n=== 截 ROI 区域 ===')
ROIs = {
    # 任务入口 ROI
    'roi_award_btn': (1194, 314, 72, 66),       # "奖励"按钮
    'roi_activity_btn': (1194, 132, 50, 42),    # "活动/招募"按钮
    'roi_mail_entry': (1800, 400, 80, 80),      # 信封图标（估算，右侧图标栏）
    'roi_ninja_guide': (934, 597, 178, 123),    # 忍界指引
    'roi_weekly_sign': (533, 555, 217, 96),     # 每周签到
    'roi_right_icons': (1700, 80, 200, 950),    # 右侧图标栏（找信封、活动等）
    'roi_top_right': (1700, 0, 220, 200),       # 右上区域
    # 全部区域
    'roi_full_screen': (0, 0, 1920, 1080),
    # 主页特征
    'roi_left_nav_main': (0, 0, 280, 1080),     # 左侧玩家信息区
    'roi_bottom_main': (0, 700, 1920, 380),     # 底部功能区
}
for name, (x, y, w, h) in ROIs.items():
    if name == 'roi_full_screen':
        cv2.imwrite('C:/tmp/phase6_' + name + '.png', home)
        print('Saved ' + name)
        continue
    x = max(0, min(x, home.shape[1]))
    y = max(0, min(y, home.shape[0]))
    w = min(w, home.shape[1] - x)
    h = min(h, home.shape[0] - y)
    crop = home[y:y+h, x:x+w]
    cv2.imwrite('C:/tmp/phase6_' + name + '.png', crop)
    print('Saved ' + name + ' size=' + str(w) + 'x' + str(h))

# 3. 验证一些原版模板在我们模拟器上能不能匹配（如果不能则提示）
print('\n=== 验证 narutomobile 原版模板 ===')
from recognition.template_matcher import TemplateMatcher
tm = TemplateMatcher()
# 拿全部 SharedNode 模板来 match
import glob
shared_templates = glob.glob('D:/自动日常源码带/narutomobile-main/assets/resource/base/image/SharedNode/*.png')
print('Trying ' + str(len(shared_templates)) + ' SharedNode templates against current screen...')
matched = []
for tpl in shared_templates:
    try:
        r = tm.match(tpl, home, threshold=0.6)
        if r:
            matched.append((os.path.basename(tpl), round(r.confidence, 3), r.center))
    except Exception as e:
        pass
matched.sort(key=lambda x: -x[1])
print('Matched ' + str(len(matched)) + ' templates:')
for name, conf, center in matched[:20]:
    print('  ' + name + ': conf=' + str(conf) + ' center=' + str(center))