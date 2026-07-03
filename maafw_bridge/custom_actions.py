"""maafw_bridge.custom_actions — Python 端实现的 CustomAction 替代 narutomobile 缺失的 C++ plugin。

narutomobile v1.3.35 的 ``merged.json`` 用了 2 个 custom action:
    - ``NonlinearSwipe``(4 节点):非线性曲线滑动,模拟人手 swipe
    - ``GoIntoEntryByGuide``(9 节点):通过忍者指引左侧菜单 OCR 找 tab 文字 + 点击进入

narutomobile 没提供对应 C++ plugin 二进制(``MaaPluginDemo.dll`` 是 demo 模板,无 MAA_PLUGIN_ENTRY 导出)。
我们用 Python 端实现,注册到 ``maafw_bridge.MaaTaskerSingleton.resource``。

GoIntoEntryByGuide 的设计来源(``merged.json`` 调用点全部 9 处):
    - ``open_secret_realm_by_guide`` / ``open_black_market_merchant_by_guide``:
      ``entry_name=["秘境探险","秋境探险"]``(双 alias)
    - ``goto_group_by_guide`` / ``goto_rebel_ninja_by_guide`` / ``sky_ground_entry`` /
      ``stronghold_entry``: ``entry_name="组织"``
    - ``mission_office_in_ninja_guide``: ``entry_name="任务集会所"``
    - ``go_into_shugyou_no_michi_by_guide``: ``entry_name="修行之路"``
    - ``goto_duel_field_by_guide``: ``entry_name="忍术对战"``

每个调用点都遵循同一模板::
    {
      "recognition": "Custom:IsInNinjaGuide",     # 调用方保证"在忍者指引页"
      "action":      "Custom:GoIntoEntryByGuide", # 找 tab + 点击
      "post_delay":  1500                          # 等待页面切换
    }

实现:``run_recognition_direct(JRecognitionType.OCR, JOCR(...), image)`` 走 Maafw 内置 OCR。
OCR 模型 narutomobile 已自带(``model/ocr/{det,rec}.onnx + keys.txt``),免依赖。

15-JumpBack recovery 链 / OCR 节点 narutomobile 完整(15/15 + 6 个 OCR 节点都齐),走 maafw 引擎时自动生效,
不需要 Python 端再实现。``back_main_screen`` 的 ``inverse=true`` + 15 节点 next 链是 narutomobile
5 层健壮性的核心;具体分析见 ``docs/narutomobile_back_main_screen_analysis.md``。

注册时机:
    - ``MaaTaskerSingleton.init(cfg)`` 完成后自动调 ``register_default_custom_actions(resource)``
"""

from __future__ import annotations

import json
import random
import time
from typing import Any

try:
    from maa.custom_action import CustomAction  # type: ignore
    from maa.context import Context  # type: ignore
    from maa.pipeline import JOCR, JRecognitionType  # type: ignore
    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    CustomAction = None  # type: ignore
    Context = None  # type: ignore
    JOCR = None  # type: ignore
    JRecognitionType = None  # type: ignore
    _MAAFW_AVAILABLE = False

from loguru import logger

_LOG = logger.bind(component="maafw.custom_action")


# ----- NonlinearSwipe --------------------------------------------------------


class NonlinearSwipeAction(CustomAction if CustomAction else object):
    """非线性曲线 swipe 替代品 — 多次小步 swipe 模拟人手曲线轨迹。

    narutomobile 的 NonlinearSwipe 参数::
        {
          "start_x": int,
          "start_y": int,
          "end_x": int,
          "end_y": int,
          "after_swipe_delay": int (ms)
        }

    实现:5 段直线 swipe,每段随机加 ±5 像素 noise + 中间 bezier 偏移。
    """

    SEGMENTS = 5
    NOISE_PX = 5

    def run(  # type: ignore[override]
        self,
        context: "Context",
        argv: Any,
    ) -> bool:
        params = _parse_custom_action_param(argv)
        try:
            sx = int(params.get("start_x", 0))
            sy = int(params.get("start_y", 0))
            ex = int(params.get("end_x", 0))
            ey = int(params.get("end_y", 0))
            delay = int(params.get("after_swipe_delay", 100))
        except (TypeError, ValueError, AttributeError) as exc:
            _LOG.warning("NonlinearSwipe param parse failed: {}", exc)
            return False

        ctrl = context.tasker.controller
        # 5 段 swipe:每段从当前 bezier 点到下一个 bezier 点
        # bezier 中点偏移 = (sy→ey 中点的 x 方向 ±NOISE_PX)
        for i in range(1, self.SEGMENTS + 1):
            t = i / self.SEGMENTS
            # 当前 bezier 插值
            mid_x = sx + (ex - sx) * t
            mid_y = sy + (ey - sy) * t
            # 曲线偏移:中间段往 x 方向偏移 noise
            if 1 <= i < self.SEGMENTS:
                mid_x += random.randint(-self.NOISE_PX, self.NOISE_PX)
                mid_y += random.randint(-self.NOISE_PX, self.NOISE_PX)
            # 当前段起点 = 上一个 bezier 点
            t_prev = (i - 1) / self.SEGMENTS
            from_x = sx + (ex - sx) * t_prev
            from_y = sy + (ey - sy) * t_prev
            if 1 <= (i - 1) < self.SEGMENTS:
                from_x += random.randint(-self.NOISE_PX, self.NOISE_PX)
                from_y += random.randint(-self.NOISE_PX, self.NOISE_PX)

            job = ctrl.post_swipe(
                int(from_x), int(from_y), int(mid_x), int(mid_y),
                duration=max(50, delay // self.SEGMENTS),
            )
            job.wait()

        # 完成后延迟
        if delay > 0:
            import time
            time.sleep(delay / 1000)

        _LOG.debug(
            "NonlinearSwipe done: ({},{}) -> ({},{}) delay={}ms",
            sx, sy, ex, ey, delay,
        )
        return True


# ----- GoIntoEntryByGuide ----------------------------------------------------


class GoIntoEntryByGuideAction(CustomAction if CustomAction else object):
    """GoIntoEntryByGuide — 通过忍者指引页 OCR 找 tab 文字 + 点击进入。

    设计来源:narutomobile ``merged.json`` 9 个调用点全部遵循同一模板。
    调用方约束(由 ``merged.json`` 节点顺序保证,不需要本 action 验证):
        1. ``recognition: Custom:IsInNinjaGuide`` 已先验证"在忍者指引页"
        2. ``previous node(open_ninja_guide / ninja_guide_in_ninja_guide)`` 已处理过主流程
        3. ``post_delay`` 1500ms 等页面切换

    实现步骤:
        1. ``controller.post_screencap()`` 拿 numpy image
        2. ``context.run_recognition_direct(JRecognitionType.OCR, JOCR(expected=..., roi=...), image)``
           在左侧菜单 ROI ``(0, 66, 219, 627)`` 找 ``entry_name``(支持多 alias,如
           ``["秘境探险","秋境探险"]``)
        3. 命中 → ``RecognitionDetail.box`` 算中心 → ``controller.post_click(x, y)``
        4. ``time.sleep(post_delay_ms / 1000)`` 等页面切换
        5. 返回 True(让外层 next 节点验证进 tab 成功)

    失败:截屏空 / OCR 不命中 → 返回 False → 调用方 ``[JumpBack]`` 链兜底
    (通常 ``ninja_guide_to_funtion_retry`` → 再到 ``back_main_screen`` → 整体 ret=false
    但 pipeline 走完,Python 侧走 best-effort "stopped" 路径)。

    配置(``custom_action_param``):
        entry_name: ``str | List[str]``   -- 要找的 tab 文字
            单 alias: ``"组织"``
            多 alias: ``["秘境探险","秋境探险"]``(任一命中即可)
    """

    # 忍者指引左侧菜单 ROI — 来自 narutomobile ninja_guide_find_funtion_entry.roi
    ROI_MENU: tuple[int, int, int, int] = (0, 66, 219, 627)

    # post_delay 默认值 — 来自 narutomobile goto_group_by_guide.post_delay
    DEFAULT_POST_DELAY_MS: int = 1500

    # OCR threshold — narutomobile OCR 节点默认 0.3
    OCR_THRESHOLD: float = 0.3

    def run(  # type: ignore[override]
        self,
        context: "Context",
        argv: Any,
    ) -> bool:
        params = _parse_custom_action_param(argv)
        raw = params.get("entry_name", "")
        if not raw:
            _LOG.warning("GoIntoEntryByGuide: missing entry_name param")
            return False
        entry_names: list[str] = [raw] if isinstance(raw, str) else list(raw)

        # 1. 截屏
        try:
            ctrl = context.tasker.controller
            screencap_job = ctrl.post_screencap()
            image = screencap_job.wait().get()
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("GoIntoEntryByGuide: screencap failed: {}", exc)
            return False
        if image is None:
            _LOG.warning("GoIntoEntryByGuide: screencap returned None image")
            return False

        # 2. OCR 找 entry_name(多 alias 试一遍,任一命中即用)
        box = None
        matched: str | None = None
        for name in entry_names:
            try:
                jocr = JOCR(
                    expected=[name],
                    roi=self.ROI_MENU,
                    threshold=self.OCR_THRESHOLD,
                    order_by="Vertical",  # 左侧菜单 tab 是纵向排列
                )
                reco = context.run_recognition_direct(
                    JRecognitionType.OCR, jocr, image,
                )
            except Exception as exc:  # noqa: BLE001
                _LOG.warning(
                    "GoIntoEntryByGuide: OCR call failed for '{}': {}",
                    name, exc,
                )
                continue
            if reco is None:
                continue
            if getattr(reco, "hit", False) and getattr(reco, "box", None):
                box = reco.box
                matched = name
                break

        if box is None or matched is None:
            _LOG.warning(
                "GoIntoEntryByGuide: '{}' not found in ninja guide menu ROI={}",
                entry_names, self.ROI_MENU,
            )
            return False

        # 3. 点击 box 中心
        x = box.x + box.w // 2
        y = box.y + box.h // 2
        try:
            click_job = ctrl.post_click(x, y)
            click_job.wait()
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("GoIntoEntryByGuide: click failed at ({}, {}): {}", x, y, exc)
            return False

        # 4. 等页面切换(narutomobile post_delay: 1500ms)
        time.sleep(self.DEFAULT_POST_DELAY_MS / 1000)

        _LOG.info(
            "GoIntoEntryByGuide: clicked '{}' at ({}, {}) box=({},{},{},{})",
            matched, x, y, box.x, box.y, box.w, box.h,
        )
        return True


# ----- registry --------------------------------------------------------------


def _parse_custom_action_param(argv: Any) -> dict[str, Any]:
    """把 ``argv.custom_action_param`` 安全解析成 dict。

    maafw 5.10.4 在不同入口下 ``custom_action_param`` 可能是:
      - ``dict``(直接给 dict)— 罕见,某些 override path
      - ``str``(JSON 字符串)— C 回调路径(ctypes)实际行为,**主要场景**

    这里两种都兼容,失败返 ``{}`` 让 caller fallback。
    """
    raw = getattr(argv, "custom_action_param", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    # 其他类型(str-bytes-like 等)— 尝试走 str 路径
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def register_default_custom_actions(resource: Any) -> dict[str, bool]:
    """注册自定义 action 到 resource。

    Args:
        resource: maa.resource.Resource 实例(已 post_bundle 完成)。

    Returns:
        ``{action_name: registered}`` 字典,True 表示注册成功。
    """
    if not _MAAFW_AVAILABLE or resource is None:
        return {}

    results: dict[str, bool] = {}
    for name, cls in (
        ("NonlinearSwipe", NonlinearSwipeAction),
        ("GoIntoEntryByGuide", GoIntoEntryByGuideAction),
    ):
        try:
            instance = cls()
            resource.register_custom_action(name, instance)
            results[name] = True
            _LOG.info("registered custom action: {}", name)
        except Exception as exc:  # noqa: BLE001
            results[name] = False
            _LOG.warning("failed to register custom action {}: {}", name, exc)
    return results