"""tools/capture_calibration.py — 校准截图快速采集工具。

用法:
    # 在用户当前界面截图,自动命名存到 screenshots/calibration/
    python tools/capture_calibration.py <label> [--device 127.0.0.1:16384]

    # 例如:用户点击了"邮件"入口后
    python tools/capture_calibration.py mail_envelope_open

    # 输出:screenshots/calibration/20260626_1430_mail_envelope_open.png
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ADB_PATH = r"D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe"
DEFAULT_SERIAL = "127.0.0.1:16384"
CALIB_ROOT = Path(r"D:\火影自动日常\screenshots\calibration")


def capture(label: str, serial: str) -> Path:
    """截一张图,按时间戳 + label 命名存到 calibration 目录。"""
    CALIB_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = CALIB_ROOT / f"{ts}_{label}.png"
    if not label.replace("_", "").isalnum():
        raise ValueError(f"label 仅支持字母数字下划线: {label!r}")
    cmd = [ADB_PATH, "-s", serial, "exec-out", "screencap", "-p"]
    print(f"[capture] {label} via {serial} -> {out.name}")
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"adb screencap 失败: {proc.stderr.decode('utf-8', 'replace')}")
    out.write_bytes(proc.stdout)
    size = out.stat().st_size
    print(f"[capture] saved: {out} ({size} bytes)")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="快速截图工具(校准用)")
    p.add_argument("label", help="截图标签,字母数字下划线")
    p.add_argument("--device", default=DEFAULT_SERIAL, help="ADB serial")
    args = p.parse_args()
    try:
        capture(args.label, args.device)
    except Exception as e:
        print(f"[capture] FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
