"""tools.capture_template — 模板采集工具。

P6 真实接入专用工具,用于在真实模拟器上采集页面模板 PNG。

不修改任何项目源代码,只向 ``resources/templates/<STATE>/`` 写入 PNG。
运行方式::

    python tools/capture_template.py HOME        # 采 HOME 页模板
    python tools/capture_template.py POPUP       # 采 POPUP 弹窗模板
    python tools/capture_template.py LOADING     # 采 LOADING 加载页模板
    python tools/capture_template.py HOME --from-image screenshots/foo.png
    python tools/capture_template.py HOME --list # 列出已有模板

参数说明:
    STATE               必填,目标 GameState 的 value (HOME / POPUP / LOADING)
    --from-image PATH   用本地图片代替 ADB 截图(用于离线整理)
    --list              列出该 state 目录已有模板,不入参采集
    --no-gui            强制用命令行输入 ROI 坐标(默认先尝试 tkinter GUI)
    --output-dir DIR    自定义输出根目录(默认 resources/templates)
    --device SERIAL     指定 ADB 序列号(覆盖 config)
    --no-verify         采集后不调用 TemplateMatcher 自检

采集流程:
    1. 截图(ADB 或本地图片)
    2. 让用户选 ROI(GUI 拖选 / 命令行输入 x,y,w,h)
    3. 裁剪 + 保存到 resources/templates/<state>/<state>_<n>.png
    4. (可选)用 TemplateMatcher 在原图上自检 → 打印 confidence

设计原则(V2):
    - 零项目源码侵入:不修改 core / device / recognizer / state 等模块
    - 容错:截图失败 / ROI 取消 / IO 错误都不抛到用户,只 log 警告
    - 可重复:同名已存在会询问是否覆盖(默认不覆盖,自动递增编号)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# 让 ``python tools/capture_template.py`` 也能 import 项目模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

# ---------- 日志初始化(避免污染项目 logger 配置) ----------
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<level>{level:7}</level> | <level>{message}</level>",
)


# ============================================================
# 核心:截图(ADB 或本地)
# ============================================================


def capture_from_adb(serial: str | None) -> np.ndarray | None:
    """从真实 ADB 设备截图。

    优先用 ConfigManager 配置的 adb_path / default_serial。
    """
    try:
        from core.config_manager import ConfigManager
        from device.adb_client import ADBClient, ADBError
    except Exception as exc:
        logger.error("import failed: {}", exc)
        return None

    try:
        cfg = ConfigManager(PROJECT_ROOT, auto_load=True)
    except Exception as exc:
        logger.error("ConfigManager init failed: {}", exc)
        return None

    # serial 显式覆盖
    if serial:
        cfg.app.adb.default_serial = serial

    try:
        client = ADBClient(cfg)
    except Exception as exc:
        logger.error("ADBClient init failed: {}", exc)
        logger.info("hint: 在 config/app_config.yaml 里配置 adb.adb_path 和 adb.default_serial")
        return None

    logger.info("ADBClient: path={}, serial={}", client.adb_path, client.serial or "<auto>")

    try:
        result = client.connect()
        if not result.success:
            logger.error("ADB connect failed: {}", result.message)
            return None
        logger.success("ADB connected: {}", client.serial)
    except ADBError as exc:
        logger.error("ADB connect error: {}", exc)
        return None

    try:
        shot = client.screenshot()
        if not shot.success or not isinstance(shot.payload, np.ndarray):
            logger.error("screenshot failed: {}", shot.message)
            return None
        arr = shot.payload
        logger.success("screenshot ok: {}x{}", arr.shape[1], arr.shape[0])

        # 同时落盘到 screenshots/ 方便参考
        out_dir = PROJECT_ROOT / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"capture_template_{ts}.png"
        try:
            cv2.imwrite(str(out_path), arr)
            logger.info("screenshot persisted: {}", out_path)
        except Exception as exc:
            logger.warning("failed to persist screenshot: {}", exc)
        return arr
    except ADBError as exc:
        logger.error("screenshot error: {}", exc)
        return None


def load_from_image(path: Path) -> np.ndarray | None:
    """从本地图片加载。"""
    if not path.exists():
        logger.error("image not found: {}", path)
        return None
    arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if arr is None:
        logger.error("cv2.imread failed for {}", path)
        return None
    logger.success("loaded image: {} ({}x{})", path, arr.shape[1], arr.shape[0])
    return arr


# ============================================================
# ROI 选择:GUI(tkinter) / 命令行
# ============================================================


def select_roi_gui(screen: np.ndarray) -> tuple[int, int, int, int] | None:
    """用 tkinter 做 ROI 选择(纯 Python 跨平台,不依赖 OpenCV highgui)。

    Returns:
        (x, y, w, h) 或 None(取消)
    """
    try:
        import tkinter as tk

        from PIL import Image, ImageTk
    except Exception as exc:
        logger.warning("tkinter/PIL 不可用 ({})。fallback 到命令行输入", exc)
        return select_roi_cli(screen)

    h, w = screen.shape[:2]
    # tkinter 在大屏上显示不下,缩放成 max 1200
    max_dim = 1200
    scale = min(1.0, max_dim / max(h, w))
    disp_w, disp_h = int(w * scale), int(h * scale)
    if scale < 1.0:
        disp_img = cv2.resize(screen, (disp_w, disp_h))
    else:
        disp_img = screen
    # BGR → RGB
    rgb = cv2.cvtColor(disp_img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)

    root = tk.Tk()
    root.title(f"选择 ROI · 缩放 {scale:.2f} · 拖鼠标选区后松手")
    root.geometry(f"{disp_w + 40}x{disp_h + 80}+100+100")

    canvas = tk.Canvas(root, width=disp_w, height=disp_h, cursor="cross")
    canvas.pack(pady=10)

    tk_img = ImageTk.PhotoImage(pil_img)
    canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)

    state: dict[str, Any] = {
        "x0": 0,
        "y0": 0,
        "x1": 0,
        "y1": 0,
        "rect": None,
        "done": False,
        "canceled": False,
    }

    def on_press(event: Any) -> None:
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            state["x0"],
            state["y0"],
            state["x0"],
            state["y0"],
            outline="red",
            width=2,
        )

    def on_drag(event: Any) -> None:
        state["x1"], state["y1"] = event.x, event.y
        if state["rect"] is not None:
            canvas.coords(
                state["rect"],
                state["x0"],
                state["y0"],
                state["x1"],
                state["y1"],
            )

    def on_release(event: Any) -> None:
        state["x1"], state["y1"] = event.x, event.y
        state["done"] = True
        root.destroy()

    def on_cancel() -> None:
        state["canceled"] = True
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.pack()
    tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)
    tk.Label(btn_frame, text="提示:拖选 ROI,松手确认;按 取消 按钮放弃").pack(side=tk.LEFT)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", lambda e: on_cancel())

    root.mainloop()

    if state["canceled"] or not state["done"]:
        return None
    x0, y0, x1, y1 = state["x0"], state["y0"], state["x1"], state["y1"]
    # 归一化:左上和右下
    rx0, rx1 = sorted([x0, x1])
    ry0, ry1 = sorted([y0, y1])
    # 还原到原图坐标系
    ox0 = int(rx0 / scale)
    oy0 = int(ry0 / scale)
    ox1 = int(rx1 / scale)
    oy1 = int(ry1 / scale)
    # clip 到原图范围
    ox0 = max(0, min(ox0, w - 1))
    oy0 = max(0, min(oy0, h - 1))
    ox1 = max(0, min(ox1, w))
    oy1 = max(0, min(oy1, h))
    rw = ox1 - ox0
    rh = oy1 - oy0
    if rw <= 0 or rh <= 0:
        logger.warning("ROI 退化为空,取消")
        return None
    return (ox0, oy0, rw, rh)


def select_roi_cli(screen: np.ndarray) -> tuple[int, int, int, int] | None:
    """命令行输入 ROI:提示用户输入 x y w h。"""
    h, w = screen.shape[:2]
    print(f"\n屏幕尺寸: {w}x{h}")
    print("请输入 ROI 矩形 (左上角 x,y + 宽高 w,h),或 'q' 取消:")
    print("  格式示例: 100 200 50 80  (x=100 y=200 w=50 h=80)")
    while True:
        try:
            raw = input("ROI> ").strip()
        except EOFError:
            return None
        if raw.lower() in {"q", "quit", "exit", "cancel", ""}:
            if raw == "":
                continue  # 空行重新问
            return None
        parts = raw.replace(",", " ").split()
        if len(parts) != 4:
            print("格式错误:需要 4 个数字 (x y w h)")
            continue
        try:
            x, y, ww, hh = (int(float(p)) for p in parts)
        except ValueError:
            print("格式错误:必须是数字")
            continue
        if x < 0 or y < 0 or ww <= 0 or hh <= 0:
            print("数值错误:x,y>=0 且 w,h>0")
            continue
        if x + ww > w or y + hh > h:
            print(f"超出屏幕范围(需 x+w<={w}, y+h<={h})")
            continue
        return (x, y, ww, hh)


# ============================================================
# 保存 + 自检
# ============================================================


def next_filename(state_dir: Path, state: str) -> Path:
    """生成下一个可用的文件名(避免覆盖已有)。"""
    n = 1
    while True:
        p = state_dir / f"{state.lower()}_{n:03d}.png"
        if not p.exists():
            return p
        n += 1
        if n > 999:
            # 退化,加 timestamp
            ts = time.strftime("%H%M%S")
            return state_dir / f"{state.lower()}_{ts}.png"


def save_template(
    screen: np.ndarray,
    roi: tuple[int, int, int, int],
    state: str,
    output_dir: Path,
) -> Path | None:
    """按 ROI 裁剪 + 保存到目标目录。"""
    x, y, w, h = roi
    cropped = screen[y : y + h, x : x + w].copy()
    state_dir = output_dir / state
    state_dir.mkdir(parents=True, exist_ok=True)
    path = next_filename(state_dir, state)
    try:
        ok = cv2.imwrite(str(path), cropped)
        if not ok:
            logger.error("cv2.imwrite returned False: {}", path)
            return None
    except Exception as exc:
        logger.error("save failed: {}", exc)
        return None
    logger.success("saved template: {} ({}x{})", path, w, h)
    return path


def verify_template(template_path: Path, screen: np.ndarray) -> float:
    """用 TemplateMatcher 在原图上自检,返回 max confidence。失败返 0.0。"""
    try:
        from recognition.template_matcher import TemplateMatcher
    except Exception as exc:
        logger.warning("cannot import TemplateMatcher ({}), skip verify", exc)
        return 0.0
    try:
        matcher = TemplateMatcher()
        result = matcher.match(template_path, screen, threshold=0.0)
        if result is None:
            return 0.0
        return float(result.confidence)
    except Exception as exc:
        logger.warning("verify error: {}", exc)
        return 0.0


# ============================================================
# 子命令
# ============================================================


def list_templates(state: str, output_dir: Path) -> int:
    state_dir = output_dir / state
    if not state_dir.exists():
        logger.info("state dir not found: {} (无模板)", state_dir)
        return 0
    files = sorted(p for p in state_dir.iterdir() if p.is_file() and p.suffix.lower() == ".png")
    if not files:
        logger.info("state '{}' 目录为空: {}", state, state_dir)
        return 0
    print(f"\n[{state}] 模板清单 ({len(files)} 个):")
    for f in files:
        size = f.stat().st_size
        print(f"  - {f.name:30s} {size:>8} bytes")
    return 0


def capture_one(
    state: str,
    *,
    from_image: Path | None,
    output_dir: Path,
    serial: str | None,
    no_gui: bool,
    no_verify: bool,
) -> int:
    """单次采集流程。"""
    # 1) 拿截图
    if from_image is not None:
        screen = load_from_image(from_image)
    else:
        screen = capture_from_adb(serial)
    if screen is None:
        logger.error("截图失败,退出")
        return 2

    # 2) ROI 选择
    if no_gui:
        roi = select_roi_cli(screen)
    else:
        roi = select_roi_gui(screen)
    if roi is None:
        logger.warning("ROI 取消,未保存任何模板")
        return 1

    # 3) 保存
    path = save_template(screen, roi, state, output_dir)
    if path is None:
        return 3

    # 4) 自检
    if not no_verify:
        logger.info("running self-verify on original screen...")
        conf = verify_template(path, screen)
        if conf > 0.0:
            logger.success("self-verify ok: confidence={:.4f}", conf)
        else:
            logger.warning("self-verify 没匹配到(可能模板在原图里没有出现 — 也可能是阈值太高)")

    print()
    print(f"✅ 模板已保存: {path}")
    print(f"   下一张可用名: {next_filename(output_dir / state, state).name}")
    print()
    return 0


# ============================================================
# 入口
# ============================================================


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="capture_template",
        description="Phase 6 模板采集工具:截图 → 选 ROI → 保存到 resources/templates/<STATE>/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python tools/capture_template.py HOME
  python tools/capture_template.py POPUP
  python tools/capture_template.py LOADING --from-image screenshots/foo.png
  python tools/capture_template.py HOME --list
  python tools/capture_template.py HOME --no-gui --device 127.0.0.1:7555
""",
    )
    parser.add_argument(
        "state",
        nargs="?",
        default=None,
        help="目标 GameState (HOME / POPUP / LOADING)",
    )
    parser.add_argument(
        "--from-image",
        type=Path,
        default=None,
        help="用本地图片代替 ADB 截图",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出该 state 已有模板,不入参采集",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="强制命令行输入 ROI(不弹 tkinter 窗口)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "resources" / "templates",
        help="模板根目录(默认 resources/templates)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="ADB 序列号覆盖(默认从 config 读)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="采集后不调用 TemplateMatcher 自检",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    state = (args.state or "").upper()

    if state not in {"HOME", "POPUP", "LOADING"}:
        print(f"错误:state 必须是 HOME / POPUP / LOADING,当前='{args.state}'")
        print("用法: python tools/capture_template.py HOME")
        return 64  # EX_USAGE

    output_dir: Path = args.output_dir
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("created output dir: {}", output_dir)

    if args.list:
        return list_templates(state, output_dir)

    return capture_one(
        state,
        from_image=args.from_image,
        output_dir=output_dir,
        serial=args.device,
        no_gui=args.no_gui,
        no_verify=args.no_verify,
    )


if __name__ == "__main__":
    raise SystemExit(main())
