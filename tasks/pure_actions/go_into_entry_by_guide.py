"""tasks.pure_actions.go_into_entry_by_guide — 本项目版 GoIntoEntryByGuide。

设计来源:
    narutomobile ``merged.json`` 9 个调用点(``goto_group_by_guide`` 等)用
    C++ 插件做"在忍者指引页 OCR 找 tab + 点击"。

本项目实现(走本项目 OCR + ADBClient,不走 maa / narutomobile):
    1. ``adb.screenshot()`` 拿 BGR ndarray
    2. ``OCRMatcher.match(entry_name, image, roi=LEFT_MENU_ROI)`` OCR 找左侧菜单 tab
    3. 命中 → ``adb.tap(box.center)``
    4. ``time.sleep(post_delay_ms / 1000)`` 等页面切换
    5. 返回 True

API:
    GoIntoEntryByGuide(adb, ocr)
        .go(entry_name) -> bool       -- 单 alias
        .go_any([name, name2, ...]) -> bool   -- 多 alias,任一命中即用

调用方约束(由调用方保证):
    1. 调用方应先验证"在忍者指引页"(模板匹配 in_ninja_guide.png)
    2. 调用方应已处理完主流程(open_ninja_guide / back_main_screen)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from device.adb_client import ADBClient
    from recognition.ocr_matcher import OCRMatcher

_LOG = logger.bind(component="pure_actions.go_into_entry")


# 忍者指引左侧菜单 ROI — 来自 narutomobile ninja_guide_find_funtion_entry.roi
LEFT_MENU_ROI: tuple[int, int, int, int] = (0, 66, 219, 627)

DEFAULT_POST_DELAY_MS: int = 1500  # narutomobile goto_group_by_guide.post_delay
DEFAULT_OCR_THRESHOLD: float = 0.3  # narutomobile OCR 节点默认


class GoIntoEntryByGuide:
    """本项目版 GoIntoEntryByGuide — 纯 Python,不走 maa / narutomobile。"""

    def __init__(
        self,
        adb: "ADBClient",
        ocr: "OCRMatcher",
        *,
        post_delay_ms: int = DEFAULT_POST_DELAY_MS,
        threshold: float = DEFAULT_OCR_THRESHOLD,
    ) -> None:
        self._adb = adb
        self._ocr = ocr
        self._post_delay_ms = int(post_delay_ms)
        self._threshold = float(threshold)

    def go(self, entry_name: str) -> bool:
        """OCR 找 entry_name tab + 点击。失败返 False。"""
        return self.go_any([entry_name])

    def go_any(self, entry_names: list[str] | tuple[str, ...]) -> bool:
        """多 alias OCR 找 tab,任一命中即点击。全部不命中返 False。

        行为:对每个 alias **单独调一次** ``OCRMatcher.match``(传单 alias 字符串),
        第一个命中即点击。失败时日志能精确到是哪个 alias 没找到。

        对齐 narutomobile C++ GoIntoEntryByGuide 的"逐个 alias 尝试"语义。
        """
        if not entry_names:
            _LOG.warning("GoIntoEntryByGuide.go_any: empty entry_names")
            return False

        # 1. 截屏(只截一次,所有 alias 复用)
        sr = self._adb.screenshot()
        if not sr.success or sr.payload is None:
            _LOG.warning("GoIntoEntryByGuide: screenshot failed: {}", sr.message)
            return False
        image = sr.payload

        # 2. 逐个 alias 尝试 OCR
        for name in entry_names:
            result = self._ocr.match(
                name,  # 单 alias 字符串
                image,
                roi=LEFT_MENU_ROI,
                threshold=self._threshold,
            )
            if result is None:
                _LOG.debug("GoIntoEntryByGuide: alias '{}' not found, trying next", name)
                continue
            # 命中 → 点击
            cx, cy = result.center
            tap_r = self._adb.tap(cx, cy)
            if not tap_r.success:
                _LOG.warning(
                    "GoIntoEntryByGuide: tap({},{}) failed: {}", cx, cy, tap_r.message,
                )
                return False
            # 等页面切换
            if self._post_delay_ms > 0:
                time.sleep(self._post_delay_ms / 1000.0)
            _LOG.info(
                "GoIntoEntryByGuide: clicked alias='{}' text='{}' at ({}, {}) "
                "box=({},{},{},{}) conf={:.3f}",
                name, result.text, cx, cy,
                result.x, result.y, result.width, result.height,
                result.confidence,
            )
            return True

        # 全部 alias 都不命中
        _LOG.warning(
            "GoIntoEntryByGuide: all aliases {} not found in left menu ROI={}",
            entry_names, LEFT_MENU_ROI,
        )
        return False
