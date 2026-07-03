"""tasks.common_actions — 跨任务共享动作。

职责:
    封装 7 个公共动作,所有任务必须调用,禁止在任务内部复制:
        - ``go_home()``           尽力回到主页,失败不抛,仅 log warning + return False
        - ``close_popup()``       检测 POPUP 状态并尝试关闭
        - ``wait_loading()``      等待 LOADING 状态结束
        - ``ensure_state()``      确保当前是目标状态,否则 go_home + 重试
        - ``tap_template()``      v1.2 新增:基于模板匹配的点击,替代硬编码 adb.tap(x, y)
        - ``dismiss_x()``         v1.2 新增:点右上 X 关闭按钮(候选 3 模板),替代 adb.tap(1826, 84)
        - ``tap_home_button()``   v1.2 新增:点主页按钮,替代 adb.tap(85, 760)

模块级工具函数(不是类方法):
        - ``make_recovery_chain()`` v1.2 P1 #3 新增:recover() 标准链抽取,7 task 共用

设计原则(V2):
    - **全程 try/except 包裹**,任何异常都被捕获,绝不向上抛。
    - ``go_home`` / ``ensure_state`` 都是「尽力回」语义,失败不阻塞任务结果。
    - 不依赖 core.base_task.ExecutionContext,直接接受所需模块(adb/recognizer/
      game_sm/config)。这样测试可以单独 mock 这些模块而不必构造 ExecutionContext。

依赖:
    - device.adb_client.ADBClient  (screenshot + keyevent + tap)
    - recognizer.page_recognizer.PageRecognizer
    - state_machine.game_state_machine.GameStateMachine
    - state.game_state.GameState
    - core.config_manager.ConfigManager
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from loguru import logger

from device.types import ActionResult
from state.game_state import GameState

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from device.adb_client import ADBClient
    from recognizer.page_recognizer import PageRecognizer
    from state_machine.game_state_machine import GameStateMachine

__all__ = ["CommonActions", "make_recovery_chain"]


class CommonActions:
    """跨任务共享动作库。

    Args:
        adb_client: 设备操作句柄(screenshot / tap / keyevent)。
        recognizer: 页面识别器(detect_state)。
        game_sm: 游戏状态机(update_state / current_state)。
        config: 全局配置(读 inter_task_delay / 默认超时等)。
        project_root: 项目根目录(留给将来读取模板等)。

    Notes:
        - 所有方法 **不抛异常**,内部异常被捕获并 log warning + 返回 bool/None。
        - ``go_home`` / ``ensure_state`` 是「尽力回」语义 — 失败不阻塞调用方。
    """

    def __init__(
        self,
        *,
        adb_client: "ADBClient",
        recognizer: "PageRecognizer",
        game_sm: "GameStateMachine",
        config: "ConfigManager",
        project_root: Path,
    ) -> None:
        self._adb = adb_client
        self._recognizer = recognizer
        self._game_sm = game_sm
        self._config = config
        self._project_root = Path(project_root).resolve()
        self._logger = logger.bind(component="common_actions")

    @property
    def adb(self) -> "ADBClient":
        """公开只读访问 ADB 客户端。

        Phase 5 优化: 替代 ``ctx.common_actions._adb`` 私有属性访问,
        让任务代码和测试 mock 都有稳定的公开 API。
        """
        return self._adb

    # ----- public actions --------------------------------------------------

    def go_home(self, max_press_back: int = 5) -> bool:
        """尽力回到主页。

        流程:
            0. 先快速检查:若当前已是 HOME → 立即返回 True,不按任何键
            1. 最多按 ``max_press_back`` 次 BACK 键
            2. 最后按一次 HOME 键
            3. 每次按键后截图 + detect_state;命中 HOME 即返回 True
            4. (P1-STABLE-02) 连续 2 次 keyevent 失败 → 视为 ADB 断连,提前 return False,
               不再坚持按完所有键

        Args:
            max_press_back: 按 BACK 键的最大次数。

        Returns:
            True 表示已识别到 HOME 状态,False 表示尽力回但失败(或疑似 ADB 断连)。
            **不抛异常**。
        """
        log = self._logger
        # P1-STABLE-02: 连续 N 次 keyevent 失败时识别 ADB 断连,提前退出
        # (不浪费 max_press_back 次按键)
        DISCONNECT_FAIL_STREAK = 2
        fail_streak = 0
        try:
            # 0. 快速检查:已经在 HOME 就直接返回,避免不必要的按键
            if self._is_current_state(GameState.HOME):
                log.info("go_home: already at HOME, no keypress needed")
                return True

            for i in range(max_press_back):
                key_result = self._adb.keyevent("BACK")
                if not key_result.success:
                    fail_streak += 1
                    log.warning(
                        "go_home: BACK keyevent failed (streak={}/{}): {}",
                        fail_streak, DISCONNECT_FAIL_STREAK, key_result.message,
                    )
                    if fail_streak >= DISCONNECT_FAIL_STREAK:
                        log.error(
                            "go_home: ADB appears disconnected ({} consecutive keyevent failures); "
                            "aborting early (P1-STABLE-02)", fail_streak,
                        )
                        return False
                else:
                    fail_streak = 0
                time.sleep(self._inter_key_delay_sec())
                if self._is_current_state(GameState.HOME):
                    log.info("go_home: reached HOME via BACK (attempt {}/{})", i + 1, max_press_back)
                    return True

            # 最后一次:HOME 键
            home_result = self._adb.keyevent("HOME")
            if not home_result.success:
                fail_streak += 1
                log.warning(
                    "go_home: HOME keyevent failed (streak={}/{}): {}",
                    fail_streak, DISCONNECT_FAIL_STREAK, home_result.message,
                )
                if fail_streak >= DISCONNECT_FAIL_STREAK:
                    log.error(
                        "go_home: ADB appears disconnected after HOME key attempt; "
                        "aborting (P1-STABLE-02)",
                    )
                    return False
            else:
                fail_streak = 0
            time.sleep(self._inter_key_delay_sec())
            if self._is_current_state(GameState.HOME):
                log.info("go_home: reached HOME via HOME key")
                return True

            log.warning("go_home failed: cannot reach HOME after {} BACK + 1 HOME presses",
                        max_press_back)
            return False
        except Exception as exc:
            log.warning("go_home raised: {}", exc)
            return False

    # ----- Phase 4 增量: 单按键强化版(供 RecoveryManager 调度) -------

    def safe_back(self, max_retries: int = 3) -> bool:
        """按 BACK 键,失败时本地循环重试(``max_retries`` 控制总尝试次数)。

        P0-BUG-04: 旧实现只调 1 次 adb.keyevent,``max_retries`` 参数被丢弃。
        现在:
            - 尝试次数 = max_retries(默认 3)
            - 每次失败 sleep inter_key_delay_sec(共享 ``go_home`` 的退避)
            - 任何一次成功立即返 True
            - 全部失败才返 False

        与 ``go_home`` 的区别: ``go_home`` 是「多步策略(BACK×N + HOME + 截图)」
        本方法是「单按键强化版」,给 RecoveryManager / 业务任务做精细化控制。

        Args:
            max_retries: 最多尝试次数(含首次),默认 3。<=1 表示不重试。

        Returns:
            True 表示 BACK 按成功(adb 返回 success);False 表示所有重试都失败。
            **不抛异常**。
        """
        log = self._logger
        attempts = max(1, int(max_retries))
        try:
            for i in range(1, attempts + 1):
                result = self._adb.keyevent("BACK")
                if result.success:
                    if i > 1:
                        log.success("safe_back: BACK succeeded on attempt {}/{}", i, attempts)
                    else:
                        log.debug("safe_back: BACK success (attempt 1/{})", attempts)
                    return True
                log.warning(
                    "safe_back: BACK attempt {}/{} failed: {}",
                    i, attempts, result.message,
                )
                if i < attempts:
                    time.sleep(self._inter_key_delay_sec())
            log.error("safe_back: all {} attempts failed", attempts)
            return False
        except Exception as exc:
            log.warning("safe_back raised: {}", exc)
            return False

    def safe_home(self, max_retries: int = 3) -> bool:
        """按 HOME 键,失败时本地循环重试(``max_retries`` 控制总尝试次数)。

        P1-QUAL-01: 旧实现只调 1 次 adb.keyevent,``max_retries`` 被丢弃。
        现在行为同 ``safe_back``:循环 ``max_retries`` 次,任一成功即返 True。

        Args:
            max_retries: 最多尝试次数(含首次),默认 3。<=1 表示不重试。

        Returns:
            True 表示 HOME 按成功;False 表示所有重试都失败。
            **不抛异常**。
        """
        log = self._logger
        attempts = max(1, int(max_retries))
        try:
            for i in range(1, attempts + 1):
                result = self._adb.keyevent("HOME")
                if result.success:
                    if i > 1:
                        log.success("safe_home: HOME succeeded on attempt {}/{}", i, attempts)
                    else:
                        log.debug("safe_home: HOME success (attempt 1/{})", attempts)
                    return True
                log.warning(
                    "safe_home: HOME attempt {}/{} failed: {}",
                    i, attempts, result.message,
                )
                if i < attempts:
                    time.sleep(self._inter_key_delay_sec())
            log.error("safe_home: all {} attempts failed", attempts)
            return False
        except Exception as exc:
            log.warning("safe_home raised: {}", exc)
            return False

    def dismiss_popup(
        self,
        popup_close_template: Path | None = None,
        *,
        max_attempts: int = 2,
    ) -> bool:
        """检测并关闭 POPUP(强化版,Phase 4 增量)。

        与 ``close_popup`` 的区别:
            - ``close_popup`` 只做一次检测,失败就返 False。
            - ``dismiss_popup`` 最多尝试 ``max_attempts`` 次(每次都先 ``safe_back`` 一次
              再 ``close_popup`` 验证),适合「弹窗位置可能变动」的真实场景。

        复用 ``safe_back`` + ``close_popup``,**不**复制 BACK/HOME 序列。

        Args:
            popup_close_template: 可选 POPUP 关闭按钮模板路径(暂未实现 tap)。
            max_attempts: 最多尝试次数。

        Returns:
            True 表示 POPUP 已关闭(状态变成 HOME 或非 POPUP);False 表示尽力但失败。
            **不抛异常**。
        """
        log = self._logger
        try:
            for attempt in range(1, max_attempts + 1):
                if self._game_sm.current_state != GameState.POPUP:
                    log.debug("dismiss_popup: not POPUP, no-op success (attempt {}/{})",
                              attempt, max_attempts)
                    return True
                # 先按一次 BACK(多数弹窗 BACK 可关),再 verify
                self.safe_back()
                time.sleep(self._inter_key_delay_sec())
                if self._game_sm.current_state != GameState.POPUP:
                    log.success("dismiss_popup: BACK closed popup (attempt {}/{})",
                                attempt, max_attempts)
                    return True
                # BACK 没关掉,调 close_popup(模板化关闭留 Phase 5+)
                if not self.close_popup(popup_close_template):
                    log.debug("dismiss_popup: close_popup attempt {}/{} returned False",
                              attempt, max_attempts)
            log.warning("dismiss_popup: failed after {} attempts", max_attempts)
            return False
        except Exception as exc:
            log.warning("dismiss_popup raised: {}", exc)
            return False

    def observe(self) -> GameState:
        """主动截图 + 识别 + 更新 game_sm,返回识别后的状态。

        公共 API(Phase 4 增量),供 ``RecoveryManager`` 等外部模块使用。
        与 ``_reobserve_current_state`` 的区别:这是 public,有返回值;
        内部仍走 ``_capture_screenshot + recognizer.detect_state + game_sm.update_state``。

        Returns:
            识别后的 ``GameState``。失败时返回当前 ``game_sm.current_state``(不抛)。
        """
        try:
            arr = self._capture_screenshot()
            if arr is None:
                return self._game_sm.current_state
            result = self._recognizer.detect_state(arr)
            self._game_sm.update_state(
                result.state, source="common_actions.observe",
            )
            return result.state
        except Exception as exc:
            self._logger.debug("observe raised: {}", exc)
            return self._game_sm.current_state

    # ----- P0 增量:游戏前台守护 --------------------------------------------
    #
    # 背景:narutomobile 在 6/25 因为 close_qq_app 把游戏切到后台,导致后续
    # 10 个任务全部失败(全部被记为 SUCCEEDED 是它的另一个 bug)。
    # 我们在每个任务开始前强制确保游戏在前台,杜绝任务间状态污染。
    #
    # 游戏包名:com.tencent.KiHan 启动 Activity:.MainActivity
    # 默认是 narutomobile / 用户当前真机的同一款游戏,可由调用方覆盖。

    DEFAULT_GAME_PACKAGE = "com.tencent.KiHan"
    DEFAULT_GAME_ACTIVITY = "com.tencent.KiHan.MainActivity"

    def _shell_capture(self, shell_args: list[str], timeout: float = 5.0) -> str | None:
        """跑一条 ``adb shell`` 命令,返回 stdout(utf-8 解码)。失败返 None。

        不复用 ADBClient._shell_action(它只返 bool 不返 output)。
        """
        log = self._logger
        try:
            import subprocess

            adb = self._adb.adb_path
            serial = self._adb.serial or ""
            cmd = [adb]
            if serial:
                cmd += ["-s", serial]
            cmd += ["shell"] + shell_args
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return r.stdout
            log.debug("_shell_capture rc={} err={}", r.returncode, r.stderr[:200])
            return None
        except Exception as exc:
            log.warning("_shell_capture raised: {}", exc)
            return None

    def _is_game_in_foreground(self, package_name: str | None = None) -> bool:
        """检测游戏是否在前台(通过 dumpsys window 找 mCurrentFocus)。

        注意:用 ``dumpsys window``(不带 ``windows``),后者不包含
        ``mCurrentFocus`` 行,会导致误判游戏不在前台。
        """
        log = self._logger
        pkg = package_name or self.DEFAULT_GAME_PACKAGE
        out = self._shell_capture(["dumpsys", "window"], timeout=8.0)
        if out is None:
            log.warning("_is_game_in_foreground: dumpsys failed, assume not in foreground")
            return False
        # mCurrentFocus=Window{xxx com.tencent.KiHan/com.tencent.KiHan.MainActivity}
        # mFocusedApp=ActivityRecord{xxx com.tencent.KiHan/.MainActivity}
        for line in out.splitlines():
            if ("mCurrentFocus" in line or "mFocusedApp" in line) and pkg in line:
                log.debug("foreground detected: {}", line.strip()[:200])
                return True
        return False

    def ensure_game_in_foreground(
        self,
        package_name: str | None = None,
        activity: str | None = None,
        *,
        post_wait_sec: float = 2.0,
    ) -> bool:
        """P0 守护:确保游戏在前台,不在就拉起。

        Args:
            package_name: 游戏包名。默认 ``com.tencent.KiHan``。
            activity: 启动 Activity。默认 ``com.tencent.KiHan.MainActivity``。
            post_wait_sec: 启动后等待秒数(让游戏从 logo 走到主页)。

        Returns:
            True 表示游戏最终在前台;False 表示尽力但失败。
            **不抛异常**。
        """
        log = self._logger
        pkg = package_name or self.DEFAULT_GAME_PACKAGE
        act = activity or self.DEFAULT_GAME_ACTIVITY
        try:
            # 1. 已经在前台 → 直接返回
            if self._is_game_in_foreground(pkg):
                log.debug("ensure_game_in_foreground: {} already in foreground", pkg)
                return True

            # 2. 不在前台 → 启动游戏
            log.warning(
                "ensure_game_in_foreground: {} NOT in foreground, launching...", pkg,
            )
            self._shell_capture(
                ["am", "start", "-a", "android.intent.action.MAIN",
                 "-c", "android.intent.category.LAUNCHER",
                 "-n", f"{pkg}/{act}"],
                timeout=10.0,
            )
            time.sleep(post_wait_sec)

            # 3. 二次验证
            if self._is_game_in_foreground(pkg):
                log.success("ensure_game_in_foreground: launched {} OK", pkg)
                return True

            log.error(
                "ensure_game_in_foreground: {} still not in foreground after launch",
                pkg,
            )
            return False
        except Exception as exc:
            log.warning("ensure_game_in_foreground raised: {}", exc)
            return False

    def close_popup(
        self,
        popup_close_template: Path | None = None,
        *,
        popup_close_templates_dir: Path | None = None,
    ) -> bool:
        """检测 POPUP 状态并尝试关闭。

        流程:
            1. 若当前不是 POPUP → return True(no-op)
            2. 若传了 ``popup_close_template``(单文件)→ 模板匹配 + tap
            3. 若传了 ``popup_close_templates_dir``(目录)→ 目录里所有 PNG 任一命中即 tap
                (fallback chain — UI 漂移时多模板兜底)
            4. 都没传 → 警告并 return False

        Args:
            popup_close_template: 单个关闭按钮模板路径。
            popup_close_templates_dir: 关闭按钮模板目录,目录下所有 PNG 都会尝试。

        Returns:
            True 表示当前没 POPUP,或已成功关闭;False 表示检测到 POPUP 但无法关闭。
        """
        log = self._logger
        try:
            current = self._game_sm.current_state
            if current != GameState.POPUP:
                return True  # no popup, no-op success
            if popup_close_template is None and popup_close_templates_dir is None:
                log.warning("close_popup: POPUP detected but no template/dir provided")
                return False

            # 单文件模式
            if popup_close_template is not None:
                return self.tap_template(
                    popup_close_template, name=popup_close_template.stem,
                )

            # 目录模式:遍历 PNG,任一命中即 tap
            assert popup_close_templates_dir is not None
            tpl_dir = Path(popup_close_templates_dir)
            if not tpl_dir.is_dir():
                log.warning("close_popup: template dir not found: {}", tpl_dir)
                return False
            for tpl in sorted(tpl_dir.glob("*.png")):
                if self.tap_template(tpl, name=tpl.stem):
                    log.info("close_popup: dismissed via {}", tpl.stem)
                    return True
                # 单个不命中,继续试下一个(fallback chain)
            log.warning(
                "close_popup: no template in {} matched", tpl_dir,
            )
            return False
        except Exception as exc:
            log.warning("close_popup raised: {}", exc)
            return False

    # ----- v1.3 新增:15-JumpBack recovery 链(本项目版) -----------------
    # narutomobile merged.json back_main_screen 链有 15 个 recovery action。
    # 本项目原版只有通用 close_popup,没有专门方法。这里把"实际有模板的"
    # 几个补上,模板缺失的标 TODO 等 user 裁模板。
    # 模板默认在 ``resources/templates/actions/SharedNode/`` 下。

    def _shared_template(self, name: str) -> Path:
        """SharedNode 下的模板默认路径。"""
        return self._project_root / "resources" / "templates" / "actions" / "SharedNode" / f"{name}.png"

    def close_chat(self) -> bool:
        """关闭聊天框 — 模板 ``chat_close_button.png``。"""
        return self.tap_template(
            self._shared_template("chat_close_button"), name="close_chat",
        )

    def weekly_sign(self) -> bool:
        """每周签到弹窗关闭 — 模板 ``weekly_sign.png``(注意:user 2026-06-30 说每周签到当前无入口)。"""
        return self.tap_template(
            self._shared_template("weekly_sign"), name="weekly_sign",
        )

    def close_friend_rank(self) -> bool:
        """关闭好友排行榜弹窗 — TODO 模板缺失,需 user 裁。"""
        self._logger.warning("close_friend_rank: 模板缺失,需 user 裁 (TODO)")
        return False

    def im_come_back(self) -> bool:
        """IM 重连弹窗 — 关闭 "我回来了" 按钮。TODO 模板缺失。"""
        self._logger.warning("im_come_back: 模板缺失,需 user 裁 (TODO)")
        return False

    def im_come_back_award(self) -> bool:
        """IM 重连奖励弹窗 — 领奖后关闭。TODO 模板缺失。"""
        self._logger.warning("im_come_back_award: 模板缺失,需 user 裁 (TODO)")
        return False

    def level_up(self) -> bool:
        """升级弹窗 — 关闭 "升级" 提示。TODO 模板缺失。"""
        self._logger.warning("level_up: 模板缺失,需 user 裁 (TODO)")
        return False

    def direct_hit_quit(self) -> bool:
        """直接退出对局 — 关闭 "中途退出" 确认弹窗。TODO 模板缺失。"""
        self._logger.warning("direct_hit_quit: 模板缺失,需 user 裁 (TODO)")
        return False

    def shut_social_media(self, package: str = "com.tencent.mobileqq") -> bool:
        """杀 QQ/微信进程 — 等价于 narutomobile ``shut_social_media`` StopApp。

        实现:``adb shell am force-stop <package>``。
        ADBClient 当前没暴露 ``stop_app`` 公共方法,这里走 ``_shell_action``(内部统一入口,
        含重试 + 日志)。如果将来 ADBClient 加公共 ``stop_app`` 方法,改一行即可。
        """
        log = self._logger
        try:
            # _shell_action 是 ADBClient 内部统一 shell 入口
            shell_action = getattr(self._adb, "_shell_action", None)
            if shell_action is None:
                log.warning("shut_social_media: ADBClient has no _shell_action")
                return False
            r = shell_action(
                ["am", "force-stop", package],
                description=f"force-stop {package}",
            )
            return bool(r.success)
        except Exception as exc:
            log.warning("shut_social_media raised: {}", exc)
            return False

    def wait_loading(
        self,
        timeout_sec: float = 30.0,
        poll_interval_sec: float = 1.0,
    ) -> bool:
        """等待 LOADING 状态结束。

        ⚠ 已知限制 (P1-QUAL-03):
            当前实现 **被动** 轮询 ``game_sm.current_state`` 缓存值,
            **不主动** screenshot + detect_state。
            适用场景: 游戏状态变化由外部触发(如任务执行完后 ``recover`` 切到 HOME,
            或另一个线程检测到页面切走并调 ``game_sm.update_state()``)。
            单纯靠本方法,LOADING 状态不会自动转出(因为没人触发 update_state)。
            Phase 4+ 应改为每次轮询都执行 ``_capture_screenshot() + recognizer.detect_state()``。

        Args:
            timeout_sec: 总超时(秒)。
            poll_interval_sec: 两次轮询间隔(秒)。

        Returns:
            True 表示 LOADING 已结束(或从未 LOADING);False 表示超时。
        """
        log = self._logger
        try:
            deadline = time.monotonic() + max(0.0, timeout_sec)
            while time.monotonic() < deadline:
                if self._game_sm.current_state != GameState.LOADING:
                    return True
                time.sleep(max(0.05, poll_interval_sec))
            log.warning("wait_loading: timeout after {}s", timeout_sec)
            return False
        except Exception as exc:
            log.warning("wait_loading raised: {}", exc)
            return False

    def ensure_state(
        self,
        target: GameState,
        max_attempts: int = 3,
    ) -> bool:
        """确保当前状态是 ``target``,否则 go_home + 重新识别。

        Args:
            target: 期望的目标 GameState。
            max_attempts: 最多尝试次数(每次都先 detect + 不命中则 go_home)。

        Returns:
            True 表示当前 == target;False 表示达到 max_attempts 仍未命中。
            **不抛异常**。
        """
        log = self._logger
        try:
            for attempt in range(1, max_attempts + 1):
                current = self._game_sm.current_state
                if current == target:
                    return True
                log.debug("ensure_state: current={}, target={}, attempt={}/{}",
                          current.value, target.value, attempt, max_attempts)
                if not self.go_home():
                    # P1-STABLE-03: go_home 失败,主动截图 + 重新识别
                    # (不要直接读 game_sm 缓存 — 游戏状态可能已经变化但缓存没更新)
                    log.debug(
                        "ensure_state: go_home failed, taking fresh screenshot to re-detect "
                        "(P1-STABLE-03)",
                    )
                    self._reobserve_current_state()
                    if self._game_sm.current_state == target:
                        return True
            return False
        except Exception as exc:
            log.warning("ensure_state raised: {}", exc)
            return False

    # ----- helpers --------------------------------------------------------

    def _is_current_state(self, target: GameState) -> bool:
        """检测当前状态: 截图 + detect_state + update_state + 比较。"""
        try:
            current = self._game_sm.current_state
            if current == target:
                return True
            # 主动观测一次,可能 game_sm 缓存过期
            arr = self._capture_screenshot()
            if arr is None:
                return current == target
            result = self._recognizer.detect_state(arr)
            self._game_sm.update_state(result.state, source="common_actions.observation")
            return result.state == target
        except Exception as exc:
            self._logger.warning("_is_current_state raised: {}", exc)
            return False

    def _reobserve_current_state(self) -> None:
        """主动截图 + 重新识别 + 更新 game_sm 缓存。

        P1-STABLE-03: 用于 ``ensure_state`` 在 ``go_home`` 失败后,
        不依赖 game_sm 缓存值,直接重新观测一次。
        失败静默(P0 仍然走 ``ensure_state`` 的 max_attempts 重试)。
        """
        try:
            arr = self._capture_screenshot()
            if arr is None:
                return
            result = self._recognizer.detect_state(arr)
            self._game_sm.update_state(
                result.state, source="common_actions.reobserve",
            )
        except Exception as exc:
            self._logger.debug("_reobserve_current_state raised: {}", exc)

    def _capture_screenshot(self) -> np.ndarray | None:
        """从 ADBClient 拿一张截图;失败返回 None(不抛)。"""
        try:
            shot = self._adb.screenshot()
            if shot.success and isinstance(shot.payload, np.ndarray):
                return shot.payload
            self._logger.debug("_capture_screenshot: adb.screenshot returned no payload")
            return None
        except Exception as exc:
            self._logger.warning("_capture_screenshot raised: {}", exc)
            return None

    def _inter_key_delay_sec(self) -> float:
        """按两次键之间的间隔。默认 0.5s,可被配置覆盖。"""
        try:
            # 复用 scheduler 的 inter_task_delay_sec 作为参考
            return max(0.05, float(self._config.app.scheduler.inter_task_delay_sec) / 2.0)
        except Exception:
            return 0.5

    # ----- v1.2 模板化点击(P0 #1 替代硬编码坐标) ---------------------

    # 默认阈值:与 PROJECT_PLAN.md v1.2 §1.2.0 的 find_and_tap 一致(0.75)
    _DEFAULT_TEMPLATE_THRESHOLD = 0.75

    def tap_template(
        self,
        template_path: Path | str,
        *,
        threshold: float | None = None,
        name: str | None = None,
        tap_offset_y: float = 0.0,
    ) -> bool:
        """基于模板匹配的点击 — 替代 ``adb.tap(x, y)`` 硬编码坐标。

        流程:
            1. 截图(``_capture_screenshot``)
            2. ``TemplateMatcher.match(template, screen, threshold=...)``
            3. 若 conf ≥ threshold,``adb.tap(cx, cy_adjusted)``
            4. 任何步骤失败都 log warning + 返回 False,**不抛异常**

        Args:
            template_path: 模板路径(相对项目根的 PNG,或绝对路径)。
            threshold: 匹配置信度阈值,None 时用 ``_DEFAULT_TEMPLATE_THRESHOLD = 0.75``。
            name: 日志用的模板名(如 ``"x_right_top"``),None 时用 template_path.stem。
            tap_offset_y: 命中后 Y 坐标的相对偏移(0.0 = 视觉中心)。
                负值向上偏,正值向下偏。推荐 -0.25(50-100px 按钮,V1.2 §1.2.0 强制)。
                公式: ``cy_实际 = cy_中心 + int(template_height * tap_offset_y)``

        Returns:
            True 表示匹配成功且 tap 已执行;False 表示截图失败 / 模板不存在 / 阈值不足 / tap 失败。
        """
        log = self._logger
        thr = threshold if threshold is not None else self._DEFAULT_TEMPLATE_THRESHOLD
        display_name = name or Path(template_path).stem

        try:
            screen = self._capture_screenshot()
            if screen is None:
                log.warning("tap_template({}): screenshot failed", display_name)
                return False

            # 延迟导入避免循环依赖
            from recognition.template_matcher import TemplateMatcher

            matcher = TemplateMatcher()
            result = matcher.match(Path(template_path), screen, threshold=thr)
            if result is None:
                log.warning(
                    "tap_template({}): no match (threshold={})",
                    display_name, thr,
                )
                return False

            cx, cy = result.center
            if tap_offset_y != 0.0:
                tpl_h = result.height
                cy = cy + int(tpl_h * tap_offset_y)
                log.info(
                    "tap_template({}) at ({}, {}) [offset_y={}] conf={:.3f} scale={:.3f}",
                    display_name, cx, cy, tap_offset_y, result.confidence, result.scale,
                )
            else:
                log.info(
                    "tap_template({}) at ({}, {}) conf={:.3f} scale={:.3f}",
                    display_name, cx, cy, result.confidence, result.scale,
                )
            tap_result = self._adb.tap(int(cx), int(cy))
            if not tap_result.success:
                log.warning("tap_template({}): tap failed: {}", display_name, tap_result.message)
                return False
            return True

        except Exception as exc:
            log.warning("tap_template({}) raised: {}", display_name, exc)
            return False

    def dismiss_x(self, *, threshold: float | None = None) -> bool:
        """点右上角 X 关闭按钮 — 用模板匹配替代 ``adb.tap(1826, 84)`` 硬编码。

        候选模板(按优先级尝试):
            1. ``x_right_top.png`` — 标准右上 X(弹窗/活动页/二级页通用)
            2. ``x.png`` — 通用 X(可能位置略偏)
            3. ``green_masked_x.png`` — 绿色遮罩下的 X(部分弹窗带绿底)

        Args:
            threshold: 匹配阈值,None 用默认 0.75。

        Returns:
            True 表示至少一个候选模板匹配并 tap 成功。
        """
        shared = self._project_root / "resources" / "templates" / "actions" / "shared"
        candidates = [
            (shared / "x_right_top.png", "x_right_top"),
            (shared / "x.png", "x"),
            (shared / "green_masked_x.png", "green_masked_x"),
        ]
        log = self._logger
        thr = threshold if threshold is not None else self._DEFAULT_TEMPLATE_THRESHOLD

        # 截图一次,所有候选共享
        try:
            screen = self._capture_screenshot()
            if screen is None:
                log.warning("dismiss_x: screenshot failed")
                return False
        except Exception as exc:
            log.warning("dismiss_x: capture raised: {}", exc)
            return False

        from recognition.template_matcher import TemplateMatcher
        matcher = TemplateMatcher()

        for tpl_path, name in candidates:
            if not tpl_path.exists():
                continue
            result = matcher.match(tpl_path, screen, threshold=thr)
            if result is None:
                continue
            cx, cy = result.center
            log.info(
                "dismiss_x via {} at ({}, {}) conf={:.3f}",
                name, cx, cy, result.confidence,
            )
            tap_result = self._adb.tap(int(cx), int(cy))
            if tap_result.success:
                return True
            log.warning("dismiss_x via {}: tap failed: {}", name, tap_result.message)
        log.warning("dismiss_x: none of the X templates matched (threshold={})", thr)
        return False

    def tap_home_button(self, *, threshold: float | None = None) -> bool:
        """点左下角主页按钮 — 用模板匹配替代 ``adb.tap(85, 760)`` 硬编码。

        候选模板:
            - ``home_button_v3.png`` — 主页橙色按钮(标准)

        Args:
            threshold: 匹配阈值,None 用默认 0.75。

        Returns:
            True 表示匹配并 tap 成功。
        """
        shared = self._project_root / "resources" / "templates" / "actions" / "shared"
        tpl = shared / "home_button_v3.png"
        if not tpl.exists():
            self._logger.warning("tap_home_button: template missing: {}", tpl)
            return False
        return self.tap_template(tpl, threshold=threshold, name="home_button_v3")


def make_recovery_chain(
    common: "CommonActions",
    *,
    double_x: bool = False,
    log: Any = None,
) -> bool:
    """标准 recover 链 — v1.2 P1 #3 抽取,7 个 task 共用。

    原 7 个 task 的 ``recover()`` 都重复同一模式::

        # 单层弹窗
        common.dismiss_x()
        time.sleep(0.5)
        common.tap_home_button()
        time.sleep(1.0)

        # 双层弹窗(邮件页 / 活跃度页,先关外层再关内层)
        common.dismiss_x()
        time.sleep(0.5)
        common.dismiss_x()
        time.sleep(0.5)
        common.tap_home_button()
        time.sleep(1.0)

    抽到这一处,所有 task 改成单行调用::

        def recover(self, ctx):
            if ctx.common_actions is None:
                return False
            return make_recovery_chain(
                ctx.common_actions,
                double_x=True,
                log=ctx.bind_logger(self.task_id),
            )

    Args:
        common: :class:`CommonActions` 实例(提供 ``dismiss_x`` / ``tap_home_button``)。
        double_x: True 时连续点两次 X(用于双层弹窗嵌套场景)。
        log: loguru logger,None 时用模块全局 :data:`logger`。

    Returns:
        True 表示链执行完毕(每个步骤内部已 try,不抛异常);
        任何异常被吞掉 → 返 False + log.warning("recover chain failed: ...")。

    Notes:
        - 严格禁止调用系统 BACK 键(会触发"是否退出游戏"弹窗)
        - 不抛异常,所有失败降级为 log warning + return False
    """
    _log = log or logger
    try:
        common.dismiss_x()
        time.sleep(0.5)
        if double_x:
            common.dismiss_x()
            time.sleep(0.5)
        common.tap_home_button()
        time.sleep(1.0)
        _log.info("recover chain done (double_x={})", double_x)
        return True
    except Exception as e:
        _log.warning("recover chain failed: {}", e)
        return False
