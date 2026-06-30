#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump uiautomator 节点并查找包含特定关键字的属性。"""
import re
import subprocess
import sys

ADB = r'D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe'
DEV = '127.0.0.1:16384'

r = subprocess.run([ADB, '-s', DEV, 'shell', 'uiautomator', 'dump'],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
r2 = subprocess.run([ADB, '-s', DEV, 'shell', 'cat', '/sdcard/window_dump.xml'],
                    capture_output=True, text=True, encoding='utf-8', errors='replace')
xml = r2.stdout

# 搜索所有可能的属性名包含关键字的节点
keywords = sys.argv[1:] if len(sys.argv) > 1 else ['每日', '勾玉', '丰饶', '商城', '前往', '丰']
for kw in keywords:
    print(f'\n=== keyword: {kw} ===')
    # 任意属性 (text / content-desc / resource-id) 含 kw
    pat = r'(?:text|content-desc|resource-id)="([^"]*' + re.escape(kw) + r'[^"]*)"[^/]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    matches = re.findall(pat, xml)
    if not matches:
        print('  (no matches)')
        continue
    for m in matches[:20]:
        text, x1, y1, x2, y2 = m
        cx = (int(x1) + int(x2)) // 2
        cy = (int(y1) + int(y2)) // 2
        print(f'  "{text}"  bounds=[{x1},{y1}]-[{x2},{y2}]  center=({cx},{cy})')