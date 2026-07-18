"""recovery.recovery_manager — 4 个异常场景的统一恢复(Phase 4)。

职责:
    单一职责:把「未知状态/弹窗/加载超时/ADB 异常」这 4 类典型故障的恢复动作
    集中起来,**所有真实导航/按键逻辑委托给 ``CommonActions``**,
    **不**复制 go_home / close_popup / wait_loading 内部实现。

设计要点:
    - **不**做状态切换 — 状态切换是 ``GameStateMachine.update_state`` 的职责;
      本模块只负责「探测 + 动作」,调用方拿到返回值后自己决定是否 update_state。
      (典型: ``GameStateMachine.recover(recovery_manager)`` 会调 ``recover_unknown``
       拿到结果,然后调 ``update_state``。)
    - **不**重试 — 重试是 ``RetryManager`` 的职责,RecoveryManager 在内部按需
      调 RetryManager(本期先留出 hook,默认不强制)。
    - **复用** CommonActions 的 ``go_home`` / ``close_popup`` / ``wait_loading``,
      不复制 BACK/HOME 键序列。
    - **截图归档** — 恢复成功时调 ``ScreenshotManager.save_recovery`` 落盘证据。

公开 API:
    RecoveryManager
        .recover_unknown()       -> GameState
        .recover_popup()         -> bool
        .recover_loading_timeout() -> bool
        .recover_adb_error()     -> bool
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from state_machine.game_state import GameState

if TYPE_CHECKING:
    from core.screenshot_manager import ScreenshotManager
    from device.adb_client import ADBClient
    from recovery.retry_manager import RetryManager
    from state_machine.game_state_machine import GameStateMachine

__all__ = ["RecoveryManager"]


class RecoveryManager:
    """4 个异常场景的统一恢复器。

    Args:
        common_actions: 跨任务动作库(所有导航/按键都委托给它)。
            ``tasks.common_actions`` 已于 2026-07-14 随旧 Navigator 删除,保留参数
            便于向后兼容(调用方传 Any mock 即可);生产环境不应再使用。
        game_sm: 游戏状态机(读 current_state / update_state)。
        adb_client: ADB 句柄(用于 recover_adb_error 重连)。
        screenshot_manager: 可选,用于 ``save_recovery`` 归档恢复成功的截图。
            None 时跳过归档(测试场景)。
        retry_manager: 可选,内部动作重试。None 时不重试(一次性动作)。
        config: 可选,ConfigManager(读 ``app.recovery`` 段阈值);None 时用硬编码默认。
    """

    def __init__(
        self,
        game_sm: "GameStateMachine",
        adb_client: "ADBClient",
        common_actions: Any = None,
        screenshot_manager: "ScreenshotManager | None" = None,
        retry_manager: "RetryManager | None" = None,
        config: "object | None" = None,
    ) -> None:
        self._common = common_actions
        self._game_sm = game_sm
        self._adb = adb_client
        self._screenshot = screenshot_manager
        self._retry = retry_manager
        # 阈值:从 cfg.app.recovery 读(缺失用硬编码)
        # P1-STABLE-02 修复: 旧用 ``getattr(...) or default`` 会在配置值为 0 时
        # 错误替换为 default(因为 ``0 or 3 == 3``)。改用显式 ``is None`` 判断。
        rec = getattr(getattr(config, "app", None), "recovery", None) if config is not None else None
        self._max_unknown = int(rec.max_unknown_retries) if rec is not None and getattr(rec, "max_unknown_retries", None) is not None else 3
        self._max_popup = int(rec.max_popup_retries) if rec is not None and getattr(rec, "max_popup_retries", None) is not None else 3
        self._max_loading_sec = float(rec.max_loading_seconds) if rec is not None and getattr(rec, "max_loading_seconds", None) is not None else 60.0
        self._adb_reconnect = int(rec.adb_reconnect_attempts) if rec is not None and getattr(rec, "adb_reconnect_attempts", None) is not None else 2
        self._logger = logger.bind(component="recovery_manager")

    # ----- recover_unknown --------------------------------------------

    def recover_unknown(self) -> GameState:
        """UNKNOWN → 通过多次截图重试 + CommonActions.go_home 退出。

        策略:
            1. 检查当前是否真是 UNKNOWN;不是则直接返回 current(防御性)。
            2. **不**自己截图 — 复用 ``CommonActions.observe()`` 截图 + 识别 +
               更新 game_sm(公共 API,Phase 4 增量)。
            3. 最多 ``max_unknown_retries`` 次,命中任意已识别状态就返回。
            4. 全部 UNKNOWN → 调 ``go_home()`` 再来一轮,仍不行返 UNKNOWN。

        Returns:
            恢复后的 GameState(可能仍是 UNKNOWN)。

        Footgun 防护 (2026-07-18): common_actions=None 时,observe/go_home 都会
        AttributeError 炸。本方法提前返 UNKNOWN,让上层知道"没救"而不是崩。
        """
        if self._common is None:
            self._logger.warning(
                "recover_unknown: common_actions=None, 跳过恢复(生产代码不应走到这里)"
            )
            return GameState.UNKNOWN
        if self._game_sm.current_state != GameState.UNKNOWN:
            self._logger.debug(
                "recover_unknown: not UNKNOWN, returning current={}",
                self._game_sm.current_state.value,
            )
            return self._game_sm.current_state

        self._logger.warning("recover_unknown: entering recovery flow")

        for attempt in range(1, self._max_unknown + 1):
            # 公共 API:截图 + detect + update_state 一次,返回识别结果
            current = self._common.observe()
            if current != GameState.UNKNOWN:
                self._logger.success(
                    "recover_unknown: identified {} on attempt {}/{}",
                    current.value, attempt, self._max_unknown,
                )
                self._save_recovery_snapshot(current, "unknown")
                return current
            self._logger.debug(
                "recover_unknown: attempt {}/{} still UNKNOWN",
                attempt, self._max_unknown,
            )

        # 全部重试都 UNKNOWN:最后用 go_home 兜底
        self._logger.warning(
            "recover_unknown: {} attempts exhausted, falling back to go_home",
            self._max_unknown,
        )
        if self._common.go_home():
            # go_home 成功的话,CommonActions 内部已经把 game_sm 切到 HOME
            current = self._game_sm.current_state
            if current != GameState.UNKNOWN:
                self._save_recovery_snapshot(current, "unknown:go_home")
                return current

        self._logger.error("recover_unknown: failed; state stays UNKNOWN")
        return GameState.UNKNOWN

    # ----- recover_popup ----------------------------------------------

    def recover_popup(self) -> bool:
        """POPUP → 关闭弹窗 + go_home。

        策略:
            1. 检查当前是否真是 POPUP;不是则直接返 True(没弹窗就不需要恢复)。
            2. 调 ``CommonActions.safe_back()``(单次 BACK)→ ``observe()`` 刷新
               game_sm(P1-QUAL-02:旧版只 safe_back 立即读 game_sm 缓存,感知
               不到 BACK 之后的实际页面变化)。
            3. BACK 关掉 → 返 True。
            4. BACK 没关掉 → 调 ``CommonActions.close_popup()`` + ``go_home()``。
            5. 最多 ``max_popup_retries`` 次;全失败返 False。

        Returns:
            True 表示弹窗已关闭且回到主页;False 表示尽力但失败。

        Footgun 防护 (2026-07-18): common_actions=None 时,所有 self._common.X
        会 AttributeError 炸。提前返 False,让 caller 知道"救不了"而不是崩。
        """
        if self._common is None:
            self._logger.warning(
                "recover_popup: common_actions=None, 跳过恢复(生产代码不应走到这里)"
            )
            return False
        if self._game_sm.current_state != GameState.POPUP:
            self._logger.debug(
                "recover_popup: not POPUP, no recovery needed (current={})",
                self._game_sm.current_state.value,
            )
            return True

        self._logger.warning("recover_popup: entering recovery flow")

        for attempt in range(1, self._max_popup + 1):
            # 1) 先按 BACK
            self._common.safe_back()
            # 2) P1-QUAL-02: BACK 不会更新 game_sm,必须 observe 一次刷新
            self._common.observe()
            if self._game_sm.current_state != GameState.POPUP:
                self._logger.success(
                    "recover_popup: BACK + observe closed popup (attempt {}/{})",
                    attempt, self._max_popup,
                )
                self._save_recovery_snapshot(self._game_sm.current_state, "popup:back")
                return True
            # 3) BACK 没关掉,调 close_popup + go_home
            self._common.close_popup()
            self._common.go_home()
            # 4) go_home 内部应已切回 HOME,observe 确认
            self._common.observe()
            if self._game_sm.current_state == GameState.HOME:
                self._logger.success(
                    "recover_popup: recovered on attempt {}/{}",
                    attempt, self._max_popup,
                )
                self._save_recovery_snapshot(GameState.HOME, "popup")
                return True
            self._logger.debug(
                "recover_popup: attempt {}/{} still not HOME", attempt, self._max_popup,
            )

        self._logger.error("recover_popup: failed after {} attempts", self._max_popup)
        return False

    # ----- recover_loading_timeout ------------------------------------

    def recover_loading_timeout(self) -> bool:
        """LOADING 卡住超过阈值 → 等待 + 退出策略。

        策略:
            1. 检查当前是否真是 LOADING;不是则返 True。
            2. 调 ``CommonActions.wait_loading(timeout_sec=max_loading_seconds)`` 等待。
            3. wait_loading 失败 → 调 ``go_home()`` 强制跳出。
            4. go_home 成功 → 返 True;否则返 False。

        Returns:
            True 表示 LOADING 已结束或强制跳出;False 表示仍在 LOADING。

        Notes:
            已知限制: ``CommonActions.wait_loading`` 是**被动**轮询(P1-QUAL-03),
            不会主动触发 game_sm 状态切换。本方法依赖「外部有机制触发 update_state」
            (例如:截图线程、或任务内的某个动作副作用)。Phase 5+ 应改为主动观测。

        Footgun 防护 (2026-07-18): common_actions=None 时,wait_loading/go_home
        会 AttributeError 炸。提前返 False。
        """
        if self._common is None:
            self._logger.warning(
                "recover_loading_timeout: common_actions=None, 跳过恢复(生产代码不应走到这里)"
            )
            return False
        if self._game_sm.current_state != GameState.LOADING:
            self._logger.debug(
                "recover_loading_timeout: not LOADING (current={}), no recovery needed",
                self._game_sm.current_state.value,
            )
            return True

        self._logger.warning(
            "recover_loading_timeout: waiting up to {}s for LOADING to end",
            self._max_loading_sec,
        )
        loaded = self._common.wait_loading(timeout_sec=self._max_loading_sec)
        if loaded:
            self._logger.success("recover_loading_timeout: LOADING ended")
            self._save_recovery_snapshot(self._game_sm.current_state, "loading")
            return True

        # 等待超时 → go_home 强制跳出
        self._logger.warning(
            "recover_loading_timeout: timeout after {}s, forcing go_home",
            self._max_loading_sec,
        )
        if self._common.go_home():
            self._save_recovery_snapshot(GameState.HOME, "loading:go_home")
            return True

        self._logger.error("recover_loading_timeout: failed; LOADING persists")
        return False

    # ----- recover_adb_error ------------------------------------------

    def recover_adb_error(self) -> bool:
        """ADB 异常 → 断开 + 重连 + 验证。

        策略:
            1. 调 ``adb.disconnect()``(失败不抛,只看返回值)。
            2. 调 ``adb.connect()`` 重连,最多 ``adb_reconnect_attempts`` 次。
            3. 每次重连后调 ``adb.is_connected`` 验证(注意:这是**弱**验证,
               Phase 5+ 应用 ``_ping()`` 做强校验)。

        Returns:
            True 表示 ADB 重新可用;False 表示重连失败。
        """
        self._logger.warning("recover_adb_error: entering ADB recovery flow")

        # 1. 断开
        try:
            self._adb.disconnect()
        except Exception as exc:  # ADBClient 自身也会 catch,这里是双保险
            self._logger.warning("recover_adb_error: disconnect raised: {}", exc)

        # 2. 重连 + 验证
        for attempt in range(1, self._adb_reconnect + 1):
            try:
                result = self._adb.connect()
                if result.success and self._adb.is_connected:
                    self._logger.success(
                        "recover_adb_error: reconnected on attempt {}/{}",
                        attempt, self._adb_reconnect,
                    )
                    self._save_recovery_snapshot(
                        self._game_sm.current_state, "adb_error",
                    )
                    return True
                self._logger.debug(
                    "recover_adb_error: connect attempt {}/{} returned success={}: {}",
                    attempt, self._adb_reconnect, result.success, result.message,
                )
            except Exception as exc:
                self._logger.warning(
                    "recover_adb_error: connect attempt {}/{} raised: {}",
                    attempt, self._adb_reconnect, exc,
                )
            # 短暂等待再重试
            if attempt < self._adb_reconnect:
                time.sleep(0.5)

        self._logger.error(
            "recover_adb_error: failed after {} reconnect attempts",
            self._adb_reconnect,
        )
        return False

    # ----- helpers ----------------------------------------------------

    def _save_recovery_snapshot(
        self,
        state: GameState,
        recovery_type: str,
    ) -> None:
        """恢复成功时归档截图。

        P1-STABLE-01 修复: 旧实现用 ``ScreenshotManager.capture()``(Windows
        PrintWindow / mss 截桌面,在生产环境会截到桌面而非游戏画面)。
        现在改用 ``ADBClient.screenshot()`` 截真实设备画面;若 ADB 返回失败
        或未连接,降级用 ``screenshot_manager``(开发期 mock 用)。
        """
        if self._screenshot is None:
            return
        try:
            # 优先 ADB 截图(真实设备画面)
            arr = self._capture_via_adb()
            if arr is None:
                # 降级:ScreenshotManager 截本地窗口(开发 / 调试用)
                arr = self._screenshot.capture()
            if arr is None:
                return
            self._screenshot.save_recovery(
                arr,
                recovery_type=recovery_type,
                state_after=state,
            )
        except Exception as exc:  # 归档失败不影响主流程
            self._logger.debug(
                "save_recovery_snapshot failed (ignored): {}",
                exc,
            )

    def _capture_via_adb(self):
        """通过 ``ADBClient.screenshot()`` 拿设备截图(返回 ndarray 或 None)。

        与 ScreenshotManager 的区别: ScreenshotManager 走 Windows PrintWindow / mss,
        截本地桌面;ADBClient 走 ``adb exec-out screencap``,截真实设备画面。
        """
        try:
            result = self._adb.screenshot()
            if result.success and result.payload is not None:
                return result.payload
            self._logger.debug(
                "_capture_via_adb: adb.screenshot returned no payload: {}",
                result.message,
            )
            return None
        except Exception as exc:
            self._logger.debug("_capture_via_adb raised: {}", exc)
            return None
