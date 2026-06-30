"""test_adb_client.py — ADBClient 关键行为。

不依赖真 ADB / 真设备:用 unittest.mock 替换 subprocess.run,
并对 ADB 可用性检测构造路径覆盖。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from device.adb_client import (
    ADBClient,
    ADBCommandError,
    ADBError,
    ADBTimeoutError,
    ADBUnavailableError,
)
from device.types import ActionResult


# ============================================================
# 构造 / 可用性检测
# ============================================================


def test_construct_with_explicit_adb_path(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("@echo fake adb\n", encoding="utf-8")
    client = ADBClient(adb_path=str(fake_adb))
    assert client.adb_path == str(fake_adb)


def test_construct_with_missing_explicit_adb_path_raises(tmp_path):
    with pytest.raises(ADBUnavailableError):
        ADBClient(adb_path=str(tmp_path / "nonexistent_adb"))


def test_construct_when_adb_missing_raises():
    """模拟 PATH 里没有 adb → 抛 ADBUnavailableError。"""
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(ADBUnavailableError):
            ADBClient()


def test_construct_with_config_overrides(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(fake_adb), default_serial="127.0.0.1:7555",
                     command_timeout_sec=5.0, retry_count=3)
    client = ADBClient(cfg)
    assert client.adb_path == str(fake_adb)
    assert client.serial == "127.0.0.1:7555"
    assert client._timeout_sec == 5.0
    assert client._retry_count == 3


# ============================================================
# P6-REAL-01: ADB 路径/序列号优先级契约
# ============================================================


def test_adb_path_priority_override_beats_config(tmp_path):
    """P6 真实接入: 显式 adb_path > config.adb_path > shutil.which('adb')。"""
    explicit = tmp_path / "explicit_adb"
    explicit.write_text("", encoding="utf-8")
    cfg_path = tmp_path / "cfg_adb"
    cfg_path.write_text("", encoding="utf-8")
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(cfg_path))
    # 即使 config 指向 cfg_path,显式 override 应该胜出
    client = ADBClient(cfg, adb_path=str(explicit))
    assert client.adb_path == str(explicit)


def test_adb_path_priority_config_beats_path(tmp_path):
    """P6 真实接入: config.adb_path > shutil.which('adb')。"""
    cfg_path = tmp_path / "cfg_adb"
    cfg_path.write_text("", encoding="utf-8")
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(cfg_path))
    # 即使 PATH 中能找到 adb,config 应该胜出
    with mock.patch("shutil.which", return_value="/usr/bin/adb"):
        client = ADBClient(cfg)
    assert client.adb_path == str(cfg_path)


def test_adb_path_priority_falls_back_to_which(tmp_path):
    """P6 真实接入: 无 override + 无 config → 用 shutil.which('adb')。"""
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path="")  # 留空
    with mock.patch("shutil.which", return_value="/usr/bin/adb"):
        client = ADBClient(cfg)
    assert client.adb_path == "/usr/bin/adb"


def test_adb_path_priority_raises_when_all_missing():
    """P6 真实接入: 三层都没有 → 抛 ADBUnavailableError(可被 graceful fallback 接住)。"""
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(ADBUnavailableError):
            ADBClient()


def test_serial_priority_override_beats_config(tmp_path):
    """P6 真实接入: 显式 serial > config.default_serial。"""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(fake_adb), default_serial="127.0.0.1:7555")
    client = ADBClient(cfg, serial="emulator-5554")
    assert client.serial == "emulator-5554"


def test_serial_from_config_mumu_port(tmp_path):
    """P6 真实接入: 模拟 MuMu 模拟器配置 default_serial='127.0.0.1:7555'。"""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(fake_adb), default_serial="127.0.0.1:7555")
    client = ADBClient(cfg)
    assert client.serial == "127.0.0.1:7555"


# ============================================================
# connect
# ============================================================


def _make_completed(stdout: bytes = b"", stderr: bytes = b"", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def test_connect_success_with_explicit_serial(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run") as mrun:
        # 第一次 = adb connect,第二次 = get-state (P1-STABLE-02 _ping 二次校验)
        mrun.side_effect = [
            _make_completed(b"connected to 127.0.0.1:7555\n"),
            _make_completed(b"device\n", b"", rc=0),
        ]
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.connect()
    assert result.success is True
    assert "127.0.0.1:7555" in result.message
    assert client.is_connected is True


def test_connect_already_connected(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run") as mrun:
        mrun.side_effect = [
            _make_completed(b"already connected to 127.0.0.1:7555\n"),
            _make_completed(b"device\n", b"", rc=0),
        ]
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.connect()
    assert result.success is True
    assert client.is_connected is True


def test_connect_no_serial_auto_detect_first_device(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    devices_output = b"List of devices attached\nemulator-5554\tdevice\n127.0.0.1:7555\tdevice\n"
    with mock.patch("subprocess.run") as mrun:
        mrun.side_effect = [
            _make_completed(devices_output),  # adb devices
            _make_completed(b"device\n", b"", rc=0),  # get-state (ping)
        ]
        client = ADBClient(adb_path=str(fake_adb))
        result = client.connect()
    assert result.success is True
    assert client.serial == "emulator-5554"
    assert client.is_connected is True


def test_connect_no_device_found(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run",
                    return_value=_make_completed(b"List of devices attached\n\n")):
        client = ADBClient(adb_path=str(fake_adb))
        result = client.connect()
    assert result.success is False


def test_connect_timeout_returns_failure(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 5)):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.connect()
    assert result.success is False
    assert "timed out" in result.message.lower() or "timeout" in result.message.lower()


# ============================================================
# disconnect
# ============================================================


def test_disconnect_no_serial_returns_success_unchanged(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    client = ADBClient(adb_path=str(fake_adb))
    res = client.disconnect()
    assert res.success is True
    assert "no serial" in res.message


def test_disconnect_calls_adb(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", return_value=_make_completed(b"disconnected 127.0.0.1:7555\n")):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        client._connected = True
        res = client.disconnect()
    assert res.success is True
    assert client.is_connected is False


def test_disconnect_timeout_returns_failure(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 5)):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        res = client.disconnect()
    assert res.success is False


# ============================================================
# screenshot
# ============================================================


def _make_png_bytes(width: int = 720, height: int = 1280) -> bytes:
    import cv2
    arr = np.full((height, width, 3), 30, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return bytes(buf)


def test_screenshot_returns_ndarray_in_payload(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    png = _make_png_bytes()
    with mock.patch("subprocess.run", return_value=_make_completed(png)):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.screenshot()
    assert result.success is True
    # P0-BUG-03: ndarray 必须放在 payload 字段,不能放在 message (str)
    assert isinstance(result.message, str)
    assert "ok" in result.message.lower()
    assert isinstance(result.payload, np.ndarray)
    assert result.payload.shape == (1280, 720, 3)


def test_screenshot_payload_is_a_copy(tmp_path):
    """P0-STABLE-01: 调用方修改返回值 ndarray 不应影响内部状态。"""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    png = _make_png_bytes()
    with mock.patch("subprocess.run", return_value=_make_completed(png)):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.screenshot()
    assert result.success is True
    arr = result.payload
    original_sum = int(arr.sum())
    # 调用方修改 ndarray
    arr[0, 0, 0] = 255
    arr[100, 100, 1] = 200
    # 再次调用应当拿到全新 ndarray,而不是被污染的副本
    with mock.patch("subprocess.run", return_value=_make_completed(png)):
        result2 = client.screenshot()
    assert result2.success is True
    assert int(result2.payload.sum()) == original_sum, (
        "payload must be a fresh copy; caller mutation leaked"
    )


def test_screenshot_retries_on_failure(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    png = _make_png_bytes()
    # 第一次失败(返回非 0),第二次成功
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(fake_adb), default_serial="127.0.0.1:7555",
                     command_timeout_sec=5.0, retry_count=3)
    fail = _make_completed(b"", b"some error", rc=1)
    ok = _make_completed(png)
    with mock.patch("subprocess.run", side_effect=[fail, ok]):
        client = ADBClient(cfg)
        result = client.screenshot()
    assert result.success is True
    assert isinstance(result.payload, np.ndarray)


def test_screenshot_exhausted_returns_failure(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    from core.config_manager import AdbConfig
    cfg = AdbConfig(adb_path=str(fake_adb), default_serial="127.0.0.1:7555",
                     command_timeout_sec=5.0, retry_count=2)
    fail = _make_completed(b"", b"err", rc=1)
    with mock.patch("subprocess.run", return_value=fail):
        client = ADBClient(cfg)
        result = client.screenshot()
    assert result.success is False


def test_screenshot_empty_png_returns_failure(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", return_value=_make_completed(b"")):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.screenshot()
    assert result.success is False


# ============================================================
# tap / swipe
# ============================================================


def test_tap_invokes_input_tap(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", return_value=_make_completed(b"")) as mrun:
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.tap(100, 200)
    assert result.success is True
    # 验证调用的命令包含 input tap 100 200
    cmd = mrun.call_args[0][0]
    assert "input" in cmd
    assert "tap" in cmd
    assert "100" in cmd
    assert "200" in cmd


def test_swipe_invokes_input_swipe(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", return_value=_make_completed(b"")) as mrun:
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.swipe(10, 20, 30, 40, duration_ms=500)
    assert result.success is True
    cmd = mrun.call_args[0][0]
    assert "swipe" in cmd
    assert "10" in cmd
    assert "500" in cmd


def test_tap_timeout_returns_failure(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 5)):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.tap(1, 2)
    assert result.success is False


# ============================================================
# ActionResult
# ============================================================


def test_action_result_to_dict():
    r = ActionResult(success=True, message="ok", next_state=None)
    d = r.to_dict()
    assert d["success"] is True
    assert d["message"] == "ok"
    assert d["next_state"] is None
    assert d["has_payload"] is False


def test_action_result_payload_field():
    """P0-BUG-03: ActionResult 必须有 payload 字段,不能把 ndarray 塞进 message。"""
    import numpy as np
    arr = np.zeros((10, 10, 3), dtype=np.uint8)
    r = ActionResult(success=True, message="captured", payload=arr)
    assert r.message == "captured"
    assert isinstance(r.message, str)
    assert r.payload is arr
    d = r.to_dict()
    assert d["has_payload"] is True


# ============================================================
# P1-BUG-02: 错误分类
# ============================================================


def test_is_retryable_error_for_non_retryable_patterns():
    """_is_retryable_error 应该识别 device unauthorized / device not found 为不可重试。"""
    from device.adb_client import ADBCommandError
    cases_non_retryable = [
        "adb: error: device 'emulator-5554' not found",
        "adb: error: device unauthorized. Please check the confirmation dialog.",
        "adb: error: no devices/emulators found",
        "error: closed",
        "error: killed",
        "permission denied",
        "more than one device/emulator",
    ]
    for msg in cases_non_retryable:
        exc = ADBCommandError(msg)
        assert ADBClient._is_retryable_error(exc) is False, f"expected non-retryable: {msg}"


def test_is_retryable_error_for_retryable_patterns():
    """未知错误或网络抖动应该是可重试的。"""
    from device.adb_client import ADBCommandError, ADBTimeoutError
    cases_retryable = [
        ADBCommandError("adb: some random transient error"),
        ADBTimeoutError("adb command timed out after 5s"),
    ]
    for exc in cases_retryable:
        assert ADBClient._is_retryable_error(exc) is True


def test_tap_aborted_on_non_retryable(tmp_path):
    """P1-BUG-02: 不可重试错误应该立即返回,不再重试。"""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    # mock subprocess.run 每次都返回 device not found (non-retryable)
    err = _make_completed(b"", b"error: device not found", rc=1)
    with mock.patch("subprocess.run", return_value=err) as mrun:
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.tap(100, 200)
    assert result.success is False
    # 只调用了 1 次(没有重试)
    assert mrun.call_count == 1


# ============================================================
# P1-STABLE-02: _ping() 真正测试连接
# ============================================================


def test_ping_returns_true_when_device_alive(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    ok = _make_completed(b"device\n", b"", rc=0)
    with mock.patch("subprocess.run", return_value=ok):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        assert client._ping() is True


def test_ping_returns_false_when_unauthorized(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    err = _make_completed(b"", b"error: device unauthorized", rc=1)
    with mock.patch("subprocess.run", return_value=err):
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        assert client._ping() is False


def test_ping_returns_false_when_no_serial(tmp_path):
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    client = ADBClient(adb_path=str(fake_adb))  # no serial
    assert client._ping() is False


def test_connect_validates_via_ping(tmp_path):
    """connect 成功应该调用 _ping 二次校验,失败时不设置 _connected=True。"""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text("", encoding="utf-8")
    with mock.patch("subprocess.run") as mrun:
        # 第一次调用 = adb connect,返回 "connected to ..."
        # 第二次调用 = adb get-state (ping),返回 unauthorized
        mrun.side_effect = [
            _make_completed(b"connected to 127.0.0.1:7555\n"),
            _make_completed(b"", b"error: device unauthorized", rc=1),
        ]
        client = ADBClient(adb_path=str(fake_adb), serial="127.0.0.1:7555")
        result = client.connect()
    assert result.success is False
    assert client.is_connected is False