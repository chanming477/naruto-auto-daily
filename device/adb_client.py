"""device.adb_client — ADB 子进程封装。

职责:
    通过 ``subprocess`` 调起 ``adb`` 命令,提供 5 个动作:
        connect(serial) — ``adb connect <host:port>``
        disconnect()    — 断开当前序列号
        screenshot()    — ``adb exec-out screencap -p`` → bytes
        tap(x, y)       — ``adb shell input tap <x> <y>``
        swipe(x1, y1, x2, y2, duration_ms=300)
                         — ``adb shell input swipe <x1> <y1> <x2> <y2> <duration_ms>``

设计要点:
    - ADB 缺失时构造抛 ``ADBUnavailableError``;调用方据此走 graceful fallback。
    - 每次命令有超时(``AdbConfig.command_timeout_sec``),超时抛 ``ADBTimeoutError``。
    - 所有命令的开始/结束/失败都打 loguru 日志(DEBUG 级别,生产环境 INFO 看不到噪音)。
    - 所有异常都被 ADBClient 捕获并包装为 ``ADBError`` 子类,返回 ``ActionResult(success=False)``。
    - 不持有 socket 长连接,全部走短进程 —— 简单可靠,与 MaaFramework 风格一致。
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from loguru import logger

from device.types import ActionResult

if TYPE_CHECKING:
    from core.config_manager import AdbConfig, ConfigManager

__all__ = ["ADBClient", "ADBError", "ADBUnavailableError", "ADBTimeoutError",
           "ADBCommandError"]


# ============================================================
# Exceptions
# ============================================================


class ADBError(Exception):
    """ADBClient 抛出的所有异常的基类。"""


class ADBUnavailableError(ADBError):
    """ADB 二进制不在 PATH,或显式配置的 adb_path 不存在。"""


class ADBTimeoutError(ADBError):
    """ADB 命令超过 ``command_timeout_sec`` 仍未返回。"""


class ADBCommandError(ADBError):
    """ADB 命令执行失败(返回码非 0 或 stderr 有内容)。"""


# ============================================================
# Client
# ============================================================


class ADBClient:
    """ADB 子进程封装。"""

    def __init__(
        self,
        config: "ConfigManager | AdbConfig | None" = None,
        *,
        adb_path: str | None = None,
        serial: str | None = None,
    ) -> None:
        """初始化并定位 ``adb`` 可执行文件。

        Args:
            config: 完整 ConfigManager 或单独的 AdbConfig;
                    None 时使用 ``adb`` 默认查找 + 默认超时 10s。
            adb_path: 显式覆盖 ``adb`` 路径(优先级最高)。
            serial: 显式覆盖默认序列号(如 ``"127.0.0.1:7555"``)。

        Raises:
            ADBUnavailableError: ``adb`` 不在 PATH 且未显式配置路径。
        """
        self._config_obj = config
        adb_cfg = self._extract_adb_config(config)
        self._adb_path = self._resolve_adb_path(adb_cfg, adb_path)
        self._serial = self._resolve_serial(adb_cfg, serial)
        self._timeout_sec = self._resolve_timeout(adb_cfg)
        self._retry_count = self._resolve_retry(adb_cfg)
        self._connected: bool = False
        logger.bind(component="adb").debug(
            "ADBClient initialized: path={}, serial={}, timeout={}s, retry={}",
            self._adb_path, self._serial or "<auto>", self._timeout_sec, self._retry_count,
        )

    # ----- properties ----------------------------------------------------

    @property
    def adb_path(self) -> str:
        return self._adb_path

    @property
    def serial(self) -> str | None:
        return self._serial

    @property
    def is_connected(self) -> bool:
        """返回客户端是否成功执行过 ``connect()``。

        ⚠ 注意: ADB 是无状态短命令,这个属性 **不保证** 设备当前仍连着。
        设备可能在两次命令之间被拔掉 / 离线 / 授权过期。如需强校验,
        调用私有方法 ``_ping()``(会真发一条 ``adb get-state``)。
        """
        return self._connected

    # ----- public actions ------------------------------------------------

    def connect(self, serial: str | None = None) -> ActionResult:
        """连接 ADB 设备。

        Args:
            serial: 目标序列号(如 ``"127.0.0.1:7555"`` 或 ``"emulator-5554"``);
                    None 时使用构造时指定的或 ``adb devices`` 自动选第一个。

        Returns:
            ActionResult: success 表示连接命令成功,
            ``next_state`` 不变(纯连接动作)。
        """
        target = serial or self._serial
        cmd = [self._adb_path]
        if target:
            cmd += ["connect", target]
        else:
            cmd += ["devices"]
        try:
            out = self._run(cmd, timeout=self._timeout_sec, check=False)
            text = (out.stdout or b"").decode("utf-8", errors="replace").strip()
            if target and ("connected to" in text.lower() or "already connected" in text.lower()):
                self._serial = target
                self._connected = self._ping()  # 二次校验:ADB connect 命令成功不代表设备在线
                if not self._connected:
                    return ActionResult(
                        False,
                        f"adb connect reported success but get-state failed; serial={target}",
                        None,
                    )
                return ActionResult(True, f"connected to {target}", None)
            if not target:
                # ``adb devices`` 路径:解析输出,选第一个 device 行
                first = self._parse_first_device(text)
                if first is not None:
                    self._serial = first
                    self._connected = self._ping()
                    if not self._connected:
                        return ActionResult(
                            False,
                            f"auto-detected {first} but get-state failed",
                            None,
                        )
                    return ActionResult(True, f"auto-detected device: {first}", None)
                return ActionResult(
                    False, f"no devices found by 'adb devices': {text!r}", None
                )
            return ActionResult(False, f"adb connect returned: {text!r}", None)
        except ADBError as exc:
            logger.bind(component="adb").error("ADB connect failed: {}", exc)
            return ActionResult(False, str(exc), None)

    def disconnect(self) -> ActionResult:
        """断开当前序列号。失败不抛错,只记录日志并返回 success=False。"""
        if not self._serial:
            return ActionResult(True, "no serial to disconnect", None)
        cmd = [self._adb_path, "disconnect", self._serial]
        try:
            out = self._run(cmd, timeout=self._timeout_sec, check=False)
            self._connected = False
            return ActionResult(
                True,
                (out.stdout or b"").decode("utf-8", errors="replace").strip() or "disconnected",
                None,
            )
        except ADBError as exc:
            logger.bind(component="adb").warning("ADB disconnect error (ignored): {}", exc)
            return ActionResult(False, str(exc), None)

    def screenshot(self) -> ActionResult:
        """截取设备屏幕,返回 ``ActionResult``。

        截图 ndarray 不放进 ``message``(会破坏 ``str`` 类型契约),改用 ``payload`` 字段承载。
        内部 ``arr.copy()`` 确保调用方修改返回值不会污染 ActionResult 内部状态。

        Returns:
            ``ActionResult``:
                - success=True:
                    - message 是 ``"screenshot ok (WxH)"`` 文本描述
                    - payload 是 ``np.ndarray`` (BGR uint8) 的 **拷贝**
                - success=False:
                    - message 是错误描述
                    - payload = None
        """
        cmd = self._build_device_cmd(["exec-out", "screencap", "-p"])
        for attempt in range(1, self._retry_count + 1):
            try:
                out = self._run(cmd, timeout=self._timeout_sec, check=True)
                arr = self._decode_png(out.stdout)
                if arr is None or arr.size == 0:
                    raise ADBCommandError("screencap returned empty PNG")
                logger.bind(component="adb").debug(
                    "screenshot ok: shape={}, attempt={}/{}", arr.shape, attempt, self._retry_count
                )
                # payload 放 ndarray 拷贝(防污染);message 保持 str 契约
                return ActionResult(
                    success=True,
                    message=f"screenshot ok ({arr.shape[1]}x{arr.shape[0]})",
                    next_state=None,
                    payload=arr.copy(),
                )
            except ADBError as exc:
                # 区分可重试/不可重试错误
                if not self._is_retryable_error(exc):
                    logger.bind(component="adb").error(
                        "screenshot aborted: non-retryable error: {}", exc
                    )
                    return ActionResult(False, str(exc), None, payload=None)
                logger.bind(component="adb").warning(
                    "screenshot attempt {}/{} failed: {}", attempt, self._retry_count, exc
                )
                if attempt >= self._retry_count:
                    return ActionResult(False, str(exc), None, payload=None)
                time.sleep(0.2)
        return ActionResult(False, "screenshot exhausted retries", None, payload=None)

    def tap(self, x: int, y: int) -> ActionResult:
        """在屏幕坐标 ``(x, y)`` 上单击。

        Args:
            x: 屏幕像素 x(0 = 最左)。
            y: 屏幕像素 y(0 = 最上)。
        """
        return self._shell_action(["input", "tap", str(int(x)), str(int(y))],
                                   description=f"tap({x},{y})")

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> ActionResult:
        """从 ``(x1, y1)`` 滑动到 ``(x2, y2)``。

        Args:
            x1, y1: 起点坐标。
            x2, y2: 终点坐标。
            duration_ms: 滑动持续时间,默认 300ms。
        """
        return self._shell_action(
            ["input", "swipe", str(int(x1)), str(int(y1)),
             str(int(x2)), str(int(y2)), str(int(duration_ms))],
            description=f"swipe({x1},{y1})->({x2},{y2})@{duration_ms}ms",
        )

    # 字符串名 → Android KeyCode 整数映射
    # 参考: https://developer.android.com/reference/android/view/KeyEvent
    _KEYCODE_NAME_TO_INT: dict[str, int] = {
        "HOME": 3,
        "KEYCODE_HOME": 3,
        "BACK": 4,
        "KEYCODE_BACK": 4,
        "POWER": 26,
        "KEYCODE_POWER": 26,
        "VOLUME_UP": 24,
        "KEYCODE_VOLUME_UP": 24,
        "VOLUME_DOWN": 25,
        "KEYCODE_VOLUME_DOWN": 25,
        "ENTER": 66,
        "KEYCODE_ENTER": 66,
        "TAB": 61,
        "KEYCODE_TAB": 61,
        "DEL": 67,
        "KEYCODE_DEL": 67,
        "KEYCODE_FORWARD_DEL": 67,
        "MENU": 82,
        "KEYCODE_MENU": 82,
        "DPAD_UP": 19,
        "KEYCODE_DPAD_UP": 19,
        "DPAD_DOWN": 20,
        "KEYCODE_DPAD_DOWN": 20,
        "DPAD_LEFT": 21,
        "KEYCODE_DPAD_LEFT": 21,
        "DPAD_RIGHT": 22,
        "KEYCODE_DPAD_RIGHT": 22,
        "DPAD_CENTER": 23,
        "KEYCODE_DPAD_CENTER": 23,
    }

    def keyevent(self, key_code: int | str) -> ActionResult:
        """发送 Android 按键事件。

        Args:
            key_code:
                - 整数:Android KeyCode 数字(如 3=HOME, 4=BACK, 26=POWER)
                - 字符串:可读名(如 "HOME" / "BACK" / "KEYCODE_HOME" / "home"),
                  大小写不敏感;优先查 ``_KEYCODE_NAME_TO_INT`` 表,未命中再尝试 ``int(...)`` 解析。

        Returns:
            ``ActionResult(success, message, next_state)``。
            失败:未知字符串名 / ADB 命令失败(可重试错误已被分类,见 ``_is_retryable_error``)。

        Examples:
            >>> adb.keyevent("BACK")       # 字符串 API,推荐
            >>> adb.keyevent("KEYCODE_HOME")
            >>> adb.keyevent(4)             # 兼容旧调用方
            >>> adb.keyevent("3")          # 也能解析为整数
        """
        if isinstance(key_code, str):
            upper = key_code.upper().strip()
            if upper in self._KEYCODE_NAME_TO_INT:
                key_code_int = self._KEYCODE_NAME_TO_INT[upper]
            else:
                try:
                    key_code_int = int(upper)
                except ValueError:
                    logger.bind(component="adb").warning(
                        "keyevent: unknown key name '{}'; expected like 'BACK'/'HOME'/3/4",
                        key_code,
                    )
                    return ActionResult(
                        success=False,
                        message=f"unknown key name '{key_code}'",
                        next_state=None,
                    )
        else:
            try:
                key_code_int = int(key_code)
            except (TypeError, ValueError):
                return ActionResult(
                    success=False,
                    message=f"invalid key_code type {type(key_code).__name__}",
                    next_state=None,
                )

        return self._shell_action(
            ["input", "keyevent", str(key_code_int)],
            description=f"keyevent({key_code})",
        )

    # ----- internals -----------------------------------------------------

    def _shell_action(self, shell_args: list[str], *, description: str) -> ActionResult:
        """通用 ``adb shell`` 动作:执行 + 区分可重试/不可重试错误 + 日志。"""
        cmd = self._build_device_cmd(["shell"] + shell_args)
        for attempt in range(1, self._retry_count + 1):
            try:
                self._run(cmd, timeout=self._timeout_sec, check=True)
                logger.bind(component="adb").debug(
                    "{} ok (attempt {}/{})", description, attempt, self._retry_count
                )
                return ActionResult(True, description, None)
            except ADBError as exc:
                if not self._is_retryable_error(exc):
                    logger.bind(component="adb").error(
                        "{} aborted: non-retryable error: {}", description, exc
                    )
                    return ActionResult(False, str(exc), None)
                logger.bind(component="adb").warning(
                    "{} attempt {}/{} failed: {}", description, attempt, self._retry_count, exc
                )
                if attempt >= self._retry_count:
                    return ActionResult(False, str(exc), None)
                time.sleep(0.2)
        return ActionResult(False, f"{description} exhausted retries", None)

    # ----- retryable error classification ---------------------------------

    #: 错误正则小写匹配;命中任一即视为「不可重试」(通常是设备/权限问题,
    #: 重试只会浪费时间,不会改变结果)。用正则而不是子串匹配,因为
    #: ADB 真实消息形如 ``device 'emulator-5554' not found``,中间会插入设备名。
    import re as _re
    _NON_RETRYABLE_REGEX: tuple["_re.Pattern[str]", ...] = (
        _re.compile(r"\bdevice\b.*\bnot found\b"),
        _re.compile(r"\bdevice\b.*\bunauthorized\b"),
        _re.compile(r"\bno devices?/emulators? found\b"),
        _re.compile(r"\bpermission denied\b"),
        _re.compile(r"\berror:\s*closed\b"),
        _re.compile(r"\berror:\s*killed\b"),
        _re.compile(r"\bmore than one device\b"),
    )

    @classmethod
    def _is_retryable_error(cls, exc: BaseException) -> bool:
        """根据 stderr / error 文本判断是否值得重试。

        Args:
            exc: ADBError 子类。

        Returns:
            True 表示可重试(超时/网络抖动等),False 表示不可重试(权限/设备不存在)。
        """
        msg = str(exc).lower()
        for pattern in cls._NON_RETRYABLE_REGEX:
            if pattern.search(msg):
                return False
        return True

    # ----- connection state ----------------------------------------------

    def _ping(self) -> bool:
        """用 ``adb -s <serial> get-state`` 真正 ping 一次 ADB 连接。

        Returns:
            True 表示设备真的响应且 state == "device"。
            False 表示设备不可达 / 未授权 / 超时。
        """
        if not self._serial:
            return False
        cmd = self._build_device_cmd(["get-state"])
        try:
            out = self._run(cmd, timeout=self._timeout_sec, check=False)
        except ADBError:
            return False
        if out.returncode != 0:
            return False
        text = (out.stdout or b"").decode("utf-8", errors="replace").strip().lower()
        return text == "device"

    def _build_device_cmd(self, args: list[str]) -> list[str]:
        """给一条命令加上 ``-s <serial>`` 前缀(若有)。"""
        cmd = [self._adb_path]
        if self._serial:
            cmd += ["-s", self._serial]
        cmd += args
        return cmd

    def _run(
        self,
        cmd: list[str],
        *,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        """调起子进程 + 统一异常包装。

        Args:
            cmd: 完整命令行(list 形式,不经过 shell)。
            timeout: 超时秒数。
            check: True 时非 0 返回码抛 ``ADBCommandError``。

        Raises:
            ADBTimeoutError: 超时。
            ADBCommandError: 返回码非 0(check=True)或启动失败。
        """
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ADBTimeoutError(
                f"adb command timed out after {timeout}s: {' '.join(cmd)}"
            ) from exc
        except FileNotFoundError as exc:
            # adb 二进制突然消失(理论上构造时已检测)
            raise ADBUnavailableError(f"adb binary not found: {exc}") from exc
        except OSError as exc:
            raise ADBCommandError(f"adb command OS error: {exc}") from exc

        if check and completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            raise ADBCommandError(
                f"adb command failed (rc={completed.returncode}): {' '.join(cmd)} | stderr={stderr!r}"
            )
        return completed

    @staticmethod
    def _decode_png(png_bytes: bytes) -> np.ndarray | None:
        """把 PNG 字节解码为 BGR uint8 ndarray。"""
        if not png_bytes:
            return None
        arr = np.frombuffer(png_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img

    @staticmethod
    def _parse_first_device(adb_devices_output: str) -> str | None:
        """从 ``adb devices`` 输出中找第一个 device(忽略 header/空行/offline)。"""
        for line in adb_devices_output.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].lower() == "device":
                return parts[0]
        return None

    # ----- config resolution --------------------------------------------

    @staticmethod
    def _extract_adb_config(
        config: "ConfigManager | AdbConfig | None",
    ) -> "AdbConfig | None":
        """从 ConfigManager 抽出 .app.adb,或者直接返回 AdbConfig / None。

        支持两种入参形式(向后兼容):
            - ConfigManager:  config.app.adb
            - AdbConfig:      直接返回
            - None:           返回 None(后续用默认值)
        """
        if config is None:
            return None
        # 直接传 AdbConfig 时它没有 .app 属性
        if hasattr(config, "app") and hasattr(config.app, "adb"):
            return config.app.adb
        # 已经是 AdbConfig(或 duck-type 类似对象):有 adb_path 字段
        if hasattr(config, "adb_path"):
            return config  # type: ignore[return-value]
        return None

    @staticmethod
    def _resolve_adb_path(
        adb_cfg: "AdbConfig | None",
        override: str | None,
    ) -> str:
        """决定最终 adb 可执行路径。优先级:override > adb_cfg.adb_path > shutil.which('adb')。"""
        if override:
            p = Path(override)
            if not p.exists():
                raise ADBUnavailableError(f"explicit adb_path does not exist: {override}")
            return str(p)
        cfg_path: str | None = None
        if adb_cfg is not None:
            cfg_path = getattr(adb_cfg, "adb_path", None)
        if cfg_path:
            p = Path(cfg_path)
            if not p.exists():
                raise ADBUnavailableError(f"config adb_path does not exist: {cfg_path}")
            return str(p)
        which = shutil.which("adb")
        if not which:
            raise ADBUnavailableError(
                "adb not found in PATH; set ConfigManager.app.adb.adb_path "
                "or pass adb_path= explicitly"
            )
        return which

    @staticmethod
    def _resolve_serial(
        adb_cfg: "AdbConfig | None",
        override: str | None,
    ) -> str | None:
        if override:
            return override
        if adb_cfg is not None:
            return getattr(adb_cfg, "default_serial", None)
        return None

    @staticmethod
    def _resolve_timeout(adb_cfg: "AdbConfig | None") -> float:
        if adb_cfg is not None:
            v = getattr(adb_cfg, "command_timeout_sec", 10)
            return float(v)
        return 10.0

    @staticmethod
    def _resolve_retry(adb_cfg: "AdbConfig | None") -> int:
        if adb_cfg is not None:
            v = getattr(adb_cfg, "retry_count", 2)
            return max(1, int(v))
        return 2