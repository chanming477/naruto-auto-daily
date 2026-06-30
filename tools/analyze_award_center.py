import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
import os

# 加载奖励中心截图
img = cv2.imread('C:/tmp/phase6_02_award_center.png')
H, W = img.shape[:2]
print('Image size:', W, 'x', H)

# 分析左侧导航栏区域 (x: 0-400, 整个高度)
left_nav = img[:, :400, :]
cv2.imwrite('C:/tmp/phase6_left_nav.png', left_nav)
print('Left nav saved: 0-' + str(W) + 'x0-' + str(H))

# 逐行扫描，找"登录送礼"的大致位置
# 转换为灰度
gray = cv2.cvtColor(left_nav, cv2.COLOR_BGR2GRAY)

# 找白色文字区域 (登录送礼是白色高亮的)
# 白色文字在蓝色按钮上: BGR ~ (255, 100, 50) range
b, g, r = cv2.split(left_nav)
white_mask = (r > 200) & (g > 180) & (b > 180)
rows_with_white = np.where(white_mask.any(axis=1))[0]
if len(rows_with_white) > 0:
    print('White text rows:', rows_with_white.min(), '-', rows_with_white.max())
    # 显示前10个有白色文字的行
    for row in rows_with_white[:20]:
        cols = np.where(white_mask[row])[0]
        if cols.max() - cols.min() > 30:  # 宽度>30的白色区域
            print('  Row', row, ': x', cols.min(), '-', cols.max(), 'width=', cols.max()-cols.min())

# 分析顶部区域 (0-250) 找导航按钮
top_area = img[:250, :, :]
print('\nTop 250px colors:')
for row in [50, 100, 150, 200]:
    for col in [50, 100, 150, 200, 250, 300, 350]:
        b_val = top_area[row, col, 0]
        g_val = top_area[row, col, 1]
        r_val = top_area[row, col, 2]
        if max(b_val, g_val, r_val) > 100:
            print('  (' + str(row) + ',' + str(col) + '): BGR=(' + str(b_val) + ',' + str(g_val) + ',' + str(r_val) + ')')

# 找导航栏中的所有按钮 (蓝色背景区域)
blue_nav = left_nav.copy()
blue_mask = (left_nav[:, :, 0] > 150) & (left_nav[:, :, 1] > 80) & (left_nav[:, :, 1] < 180) & (left_nav[:, :, 2] < 120)
# 膨胀一下连通区域
kernel = np.ones((5, 5), np.uint8)
blue_mask_dilated = cv2.dilate(blue_mask.astype(np.uint8), kernel)
contours, _ = cv2.findContours(blue_mask_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print('\nBlue nav button regions:')
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if h > 30 and w > 50 and x < 380:
        print('  Button at x=' + str(x) + '-' + str(x+w) + ' y=' + str(y) + '-' + str(y+h) + ' size=' + str(w) + 'x' + str(h))

# 保存完整分析图
output = img.copy()
# 画导航区域边框
cv2.rectangle(output, (0, 0), (380, H), (0, 255, 0), 2)
# 标注点击区域
cv2.imwrite('C:/tmp/phase6_award_analysis.png', output)
print('\nAnalysis saved to C:/tmp/phase6_award_analysis.png')

# 具体分析：左侧导航栏按钮位置
print('\n=== 左侧导航栏分析 ===')
# 左侧导航栏大约在 x: 0-380 区域
nav_gray = cv2.cvtColor(left_nav[:, :380, :], cv2.COLOR_BGR2GRAY)
# 中等亮度区域（按钮文字）
_, text_mask = cv2.threshold(nav_gray, 150, 255, cv2.THRESH_BINARY)
# 找连通区域
cnts, _ = cv2.findContours(text_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print('Text regions in left nav:')
text_regions = []
for cnt in sorted(cnts, key=lambda c: cv2.boundingRect(c)[1]):
    x, y, w, h = cv2.boundingRect(cnt)
    if h > 20 and w > 30:
        text_regions.append((y, y+h, x, x+w))
        print('  y=' + str(y) + '-' + str(y+h) + ' x=' + str(x) + '-' + str(x+w))
