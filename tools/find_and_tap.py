"""tools.find_and_tap — 全图模板匹配 + ADB 点击工具。

替代固定 ROI:截图后多尺度扫描找模板,找到中心后点击。

为什么不用固定 ROI:
    - 菜单滑动后位置变化 → 原坐标失效
    - 不同设备分辨率 → ROI 直接崩
    - OCR/UiAutomator 在 Cocos/Unity 自定义渲染游戏上不可用

核心策略:
    1. 截图(BGR ndarray)
    2. 多尺度模板匹配(默认 scale=[0.85..1.15])
    3. 跨尺度取 confidence 最高者
    4. 命中 → 取模板中心 → ADB tap
    5. 失败 → retry(可选 + swipe 重置)

对比 TemplateMatcher 内置 API 的差异:
    - TemplateMatcher.match 是 single-scale(假设模板和截图同分辨率)
    - 本工具负责 multi-scale + ADB 串联,职责单一,易于嵌入 task 节点

用法:
    python tools/find_and_tap.py <template.png>                      # 单次 find+tap
    python tools/find_and_tap.py <template.png> --no-tap --debug     # 只找不打,生成 debug 图
    python tools/find_and_tap.py <template.png> --swipe 80,800,80,200 # 先 swipe 再找
    python tools/find_and_tap.py <template.png> --threshold 0.8      # 调阈值
    python tools/find_and_tap.py <template.png> --tap-offset-y -0.25 # 偏上 25%(按钮热区)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# ADB 原子操作(独立函数,无状态)
# ============================================================


def screencap(adb_path: str, serial: str) -> np.ndarray:
    """ADB 截图 → BGR ndarray。"""
    out = subprocess.run(
        [adb_path, "-s", serial, "exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=15,
    )
    arr = np.frombuffer(out.stdout, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("screencap 失败:imdecode 返 None")
    return img


def adb_tap(adb_path: str, serial: str, x: int, y: int) -> int:
    """ADB tap → 返回码。"""
    r = subprocess.run(
        [adb_path, "-s", serial, "shell", "input", "tap", str(x), str(y)],
        capture_output=True,
        timeout=10,
    )
    return r.returncode


def adb_swipe(
    adb_path: str,
    serial: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
) -> int:
    """ADB swipe → 返回码。"""
    r = subprocess.run(
        [
            adb_path, "-s", serial, "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
        ],
        capture_output=True,
        timeout=10,
    )
    return r.returncode


# ============================================================
# 多尺度模板匹配
# ============================================================


def load_template(path: Path) -> np.ndarray:
    """加载模板 PNG,失败抛 RuntimeError。

    复用 recognition.template_matcher.load_template —— 它有 PIL fallback
    (绕开 cv2.imread 的 iCCP bug,跟 capture_template.py / core/ 一致)。
    """
    from recognition.template_matcher import load_template as _lt
    img = _lt(path)
    if img is None:
        raise RuntimeError(f"模板加载失败:{path}")
    return img


def multi_scale_match(
    template: np.ndarray,
    screen: np.ndarray,
    threshold: float = 0.75,
    scales: Sequence[float] | None = None,
) -> tuple[int, int, float, float] | None:
    """多尺度模板匹配。

    Args:
        template: BGR 模板图(H, W, 3)。
        screen: BGR 截图(H', W', 3)。
        threshold: 置信度阈值(默认 0.75,比 single-scale 0.85 略低以抵消多尺度噪声)。
        scales: 尺度列表(默认 7 档:0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)。

    Returns:
        ``(cx, cy, confidence, scale)`` 或 None。
        cx/cy 是模板中心在 screen 坐标系中的位置。
    """
    if scales is None:
        scales = (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)

    best: tuple[int, int, float, float] | None = None
    sh, sw = screen.shape[:2]
    for scale in scales:
        th, tw = template.shape[:2]
        nh, nw = int(round(th * scale)), int(round(tw * scale))
        if nh < 5 or nw < 5:
            continue
        if nh >= sh or nw >= sw:  # 模板比 screen 还大,本轮跳过
            continue
        scaled = cv2.resize(template, (nw, nh), interpolation=cv2.INTER_AREA)
        score_map = cv2.matchTemplate(screen, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(score_map)
        if max_val < threshold:
            continue
        cx = int(max_loc[0]) + nw // 2
        cy = int(max_loc[1]) + nh // 2
        if best is None or max_val > best[2]:
            best = (cx, cy, float(max_val), float(scale))
    return best


# ============================================================
# Debug 可视化
# ============================================================


def save_debug(
    screen: np.ndarray,
    template: np.ndarray,
    cx: int,
    cy: int,
    conf: float,
    scale: float,
    out_path: Path | None = None,
) -> Path:
    """保存带绿色匹配框 + 红色中心点的 debug 图。"""
    th, tw = template.shape[:2]
    nh, nw = int(round(th * scale)), int(round(tw * scale))
    x0, y0 = cx - nw // 2, cy - nh // 2
    x1, y1 = x0 + nw, y0 + nh

    debug_img = screen.copy()
    cv2.rectangle(debug_img, (x0, y0), (x1, y1), (0, 255, 0), 3)
    cv2.circle(debug_img, (cx, cy), 10, (0, 0, 255), -1)
    cv2.putText(
        debug_img,
        f"conf={conf:.3f} scale={scale:.2f}",
        (x0, max(20, y0 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
    )
    if out_path is None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = (
            PROJECT_ROOT
            / "screenshots"
            / "calibration"
            / f"findtap_{ts}_conf{conf:.2f}.png"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), debug_img)
    return out_path


# ============================================================
# 顶层 API
# ============================================================


def find_and_tap(
    template_path: Path,
    *,
    adb_path: str,
    serial: str,
    threshold: float = 0.75,
    scales: Sequence[float] | None = None,
    swipe_before: tuple[int, int, int, int] | None = None,
    swipe_retry: tuple[int, int, int, int] | None = None,
    max_retries: int = 3,
    retry_interval_sec: float = 0.4,
    debug: bool = False,
    do_tap: bool = True,
    tap_offset_y: float = 0.0,
) -> tuple[int, int, float, float] | None:
    """截图 → 多尺度找模板 → 命中即 tap。

    Args:
        template_path: 模板 PNG 路径。
        adb_path: ADB 可执行路径。
        serial: ADB 序列号(如 ``127.0.0.1:16384``)。
        threshold: 置信度阈值。
        scales: 多尺度列表(None 用默认 7 档)。
        swipe_before: 在第一次截图前 swipe 一次(适用:菜单初始位置未知)。
        swipe_retry: 每次 retry 前 swipe 一次(适用:菜单需要在 retry 间滑动重置)。
        max_retries: 最大重试次数(包含第一次)。
        retry_interval_sec: retry 间等待秒数。
        debug: 是否保存带框的 debug 图。
        do_tap: 是否真点击(False 时只找不打,用于先验证)。
        tap_offset_y: 命中后 y 偏移比例(占模板高度)。负值=向上,正值=向下。
            ``0.0`` = 视觉中心(默认,向后兼容);
            ``-0.25`` = 偏上 25%(真机验证稳的"按钮热区偏上规则");
            ``-0.33`` = 偏上 33%(大卡片推荐);
            实际偏移像素 = ``int(tpl_h * tap_offset_y)``,四舍五入到 int。

    Returns:
        ``(cx, cy, confidence, scale)`` 或 None(全部 retry 失败)。
        cy 已经是偏移后的最终 tap 坐标(用于验证 / 调试显示)。
    """
    template = load_template(template_path)
    tpl_h = template.shape[0]

    if swipe_before is not None:
        x1, y1, x2, y2 = swipe_before
        logger.info(f"pre-swipe: ({x1},{y1}) → ({x2},{y2})")
        adb_swipe(adb_path, serial, x1, y1, x2, y2)
        time.sleep(retry_interval_sec)

    for attempt in range(1, max_retries + 1):
        if attempt > 1 and swipe_retry is not None:
            x1, y1, x2, y2 = swipe_retry
            logger.info(f"retry-{attempt} swipe: ({x1},{y1}) → ({x2},{y2})")
            adb_swipe(adb_path, serial, x1, y1, x2, y2)
            time.sleep(retry_interval_sec)

        screen = screencap(adb_path, serial)
        hit = multi_scale_match(template, screen, threshold=threshold, scales=scales)
        if hit is None:
            logger.warning(f"attempt {attempt}/{max_retries}:模板未找到(thr={threshold})")
            time.sleep(retry_interval_sec)
            continue

        cx, cy, conf, scale = hit
        # 按钮热区偏上规则(V1.2 §1.2.0):命中后 y 按 tap_offset_y 比例偏移
        if tap_offset_y != 0.0:
            offset_px = int(round(tpl_h * tap_offset_y))
            cy_tap = cy + offset_px
            logger.info(
                f"tap_offset_y={tap_offset_y}: cy {cy} → {cy_tap} (Δ={offset_px}px, tpl_h={tpl_h})"
            )
            cy = cy_tap
        logger.success(
            f"✅ 命中 ({cx},{cy}) conf={conf:.3f} scale={scale:.2f} (attempt {attempt})"
        )
        if debug:
            p = save_debug(screen, template, cx, cy, conf, scale)
            logger.info(f"debug 图:{p}")
        if do_tap:
            rc = adb_tap(adb_path, serial, cx, cy)
            logger.info(f"ADB tap ({cx},{cy}) → rc={rc}")
        return (cx, cy, conf, scale)

    logger.error(f"❌ {max_retries} 次重试全部失败")
    return None


# ============================================================
# CLI
# ============================================================


def _parse_swipe(s: str) -> tuple[int, int, int, int]:
    parts = [int(p.strip()) for p in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("swipe 必须是 x1,y1,x2,y2 共 4 个整数")
    return tuple(parts)  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="find_and_tap",
        description="全图模板匹配 + ADB 点击(替代固定 ROI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # 单次 find+tap
  python tools/find_and_tap.py screenshots/calibration/templates/monthly_signin.png

  # 只找不打,生成 debug 图
  python tools/find_and_tap.py templates/x.png --no-tap --debug

  # 先 swipe 再找(适用初始菜单位置未知)
  python tools/find_and_tap.py templates/x.png --swipe-before 80,800,80,200

  # retry 间 swipe(适用多层菜单,每 retry 翻一页)
  python tools/find_and_tap.py templates/x.png --swipe-retry 80,800,80,200 --max-retries 5

  # 按钮热区偏上(真机验证:V1.2 §1.2.0 规则)
  python tools/find_and_tap.py templates/x.png --tap-offset-y -0.25
""",
    )
    parser.add_argument("template", type=Path, help="模板 PNG 路径(相对项目根或绝对)")
    parser.add_argument(
        "--adb-path",
        default=r"D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe",
        help="ADB 可执行路径",
    )
    parser.add_argument("--serial", default="127.0.0.1:16384", help="ADB 序列号")
    parser.add_argument("--threshold", type=float, default=0.75, help="置信度阈值(默认 0.75)")
    parser.add_argument(
        "--scales",
        type=str,
        default=None,
        help="自定义尺度列表,逗号分隔(默认 0.85..1.15 七档)",
    )
    parser.add_argument(
        "--swipe-before", type=str, default=None,
        help="首次截图前 swipe:x1,y1,x2,y2",
    )
    parser.add_argument(
        "--swipe-retry", type=str, default=None,
        help="每次 retry 前 swipe:x1,y1,x2,y2",
    )
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")
    parser.add_argument(
        "--retry-interval", type=float, default=0.4, help="retry 间等待秒数",
    )
    parser.add_argument("--debug", action="store_true", help="保存带框 debug 图")
    parser.add_argument("--no-tap", action="store_true", help="只找不打(用于验证)")
    parser.add_argument(
        "--tap-offset-y", type=float, default=0.0,
        help="命中后 y 偏移比例(占模板高度);负=向上. 0.0=视觉中心,-0.25=偏上 25%%",
    )

    args = parser.parse_args(argv)

    # loguru init(避免污染项目 logger)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<level>{level:7}</level> | <level>{message}</level>",
    )

    scales: Sequence[float] | None = None
    if args.scales:
        scales = tuple(float(s) for s in args.scales.split(","))

    swipe_before = _parse_swipe(args.swipe_before) if args.swipe_before else None
    swipe_retry = _parse_swipe(args.swipe_retry) if args.swipe_retry else None

    template_path: Path = args.template
    if not template_path.is_absolute():
        template_path = PROJECT_ROOT / template_path

    if not template_path.exists():
        logger.error(f"模板不存在:{template_path}")
        return 2

    result = find_and_tap(
        template_path,
        adb_path=args.adb_path,
        serial=args.serial,
        threshold=args.threshold,
        scales=scales,
        swipe_before=swipe_before,
        swipe_retry=swipe_retry,
        max_retries=args.max_retries,
        retry_interval_sec=args.retry_interval,
        debug=args.debug,
        do_tap=not args.no_tap,
        tap_offset_y=args.tap_offset_y,
    )

    if result is None:
        print("\n❌ 失败:模板未找到")
        return 3
    cx, cy, conf, scale = result
    mode = "命中" if args.no_tap else "已点击"
    print(f"\n✅ {mode}:({cx}, {cy}) conf={conf:.3f} scale={scale:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())