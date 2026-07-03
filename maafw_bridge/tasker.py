"""maafw_bridge.tasker — MaaFramework Tasker 单例。

设计(v2.0 方案 §5.1):
    - **线程安全单例**(双检锁),整个进程一份
    - **延迟初始化** — 调 ``init(cfg)`` 时才连 ADB / 加载 resource,
      让 import / 单元测试 / smoke 不依赖模拟器
    - **配置驱动** — 从 ``cfg.app.maafw.narutomobile_resource_path`` + ``cfg.project_root``
      解析路径;从 ``cfg.app.maafw.data_dir`` 解析 maafw log 落盘目录

用法::

    from core.config_manager import ConfigManager
    from maafw_bridge import get_tasker, resolve_entry

    cfg = ConfigManager(project_root, auto_load=True)
    singleton = get_tasker()
    singleton.init(cfg)                          # 触发初始化

    job = singleton.run_task(resolve_entry("mail"))
    detail = job.wait().get()
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from maa.toolkit import Toolkit  # type: ignore
    from maa.controller import AdbController  # type: ignore
    from maa.tasker import Tasker  # type: ignore
    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    Toolkit = None  # type: ignore
    AdbController = None  # type: ignore
    Tasker = None  # type: ignore
    _MAAFW_AVAILABLE = False

from loguru import logger

from .resource import load_narutomobile_resource
from .custom_actions import register_default_custom_actions

if TYPE_CHECKING:
    from core.config_manager import ConfigManager


_LOG = logger.bind(component="maafw.tasker")


# maafw Toolkit 默认 log 落盘目录(相对 project_root)
_DEFAULT_MAAFW_DATA_DIR = "logs/maafw_data"


class MaaFrameworkUnavailable(RuntimeError):
    """maafw Python 包没装 / DLL 缺失。"""


class ResourcePathInvalid(RuntimeError):
    """resource 路径不存在或缺少 merged.json / image/。"""


class AdbDeviceNotFound(RuntimeError):
    """Toolkit.find_adb_devices() 找不到任何设备。"""


class MaaTaskerSingleton:
    """MaaFramework Tasker 单例。

    不要直接 new,调 ``get_tasker()`` / ``reset_tasker()``,然后 ``.init(cfg)``。
    """

    _instance: "MaaTaskerSingleton | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "MaaTaskerSingleton":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    # ----- public API ---------------------------------------------------------

    def init(self, cfg: "ConfigManager") -> None:
        """延迟初始化:接 ConfigManager 后才连 ADB + 加载资源。

        Args:
            cfg: 已加载的 ``ConfigManager`` 实例。读两个字段:
                - ``cfg.app.maafw.narutomobile_resource_path``: resource 路径,
                  留空时用 ``{project_root}/resources/narutomobile/`` 默认值
                - ``cfg.app.maafw.data_dir``: maafw log 落盘目录,
                  相对 project_root。留空时用 ``{project_root}/logs/maafw_data/``

        Raises:
            MaaFrameworkUnavailable: maafw Python 包未安装。
            ResourcePathInvalid: resource 路径不存在 / 缺 merged.json / 缺 image/。
            AdbDeviceNotFound: ADB 没找到任何设备。
            FileNotFoundError: resource 路径解析后不存在。
        """
        if self._initialized:
            return
        with _init_lock:
            if self._initialized:
                return
            self._do_init(cfg)
            self._initialized = True

    def run_task(
        self,
        entry: str,
        override: dict[str, Any] | None = None,
    ) -> Any:
        """启动一个任务,返回 job。

        Args:
            entry: narutomobile pipeline entry 名(如 ``mail`` / ``headhunt`` / ``activity``)。
            override: 可选 pipeline 覆盖,格式跟 maafw pipeline_override 一致。

        Returns:
            maafw ``TaskJob`` 实例。未初始化时访问会触发 init 抛异常。
        """
        if not self._initialized:
            raise RuntimeError(
                "MaaTaskerSingleton not initialized. Call .init(cfg) first."
            )
        log = _LOG.bind(entry=entry)
        log.info("post_task entry={} override_keys={}",
                 entry, list((override or {}).keys()))
        return self._tasker.post_task(entry, override or {})

    # ----- internals ----------------------------------------------------------

    def _do_init(self, cfg: "ConfigManager") -> None:
        """实际初始化流程。失败抛清晰异常。"""
        if not _MAAFW_AVAILABLE:
            raise MaaFrameworkUnavailable(
                "maafw Python 包未安装,先跑: pip install maafw==5.10.4"
            )

        log = _LOG
        project_root = Path(cfg.project_root)

        # 1. 解析 resource 路径
        raw_resource = getattr(
            cfg.app.maafw, "narutomobile_resource_path", ""
        ) or "resources/narutomobile"
        resource_path = Path(raw_resource)
        if not resource_path.is_absolute():
            resource_path = project_root / resource_path
        resource_path = resource_path.resolve()
        log.info("resource path resolved: {}", resource_path)

        # 2. 解析 maafw log 落盘目录
        raw_data = getattr(cfg.app.maafw, "data_dir", "") or _DEFAULT_MAAFW_DATA_DIR
        data_path = Path(raw_data)
        if not data_path.is_absolute():
            data_path = project_root / data_path
        data_path = data_path.resolve()
        data_path.mkdir(parents=True, exist_ok=True)
        log.info("maafw data dir: {}", data_path)

        # 3. Toolkit 初始化
        Toolkit.init_option(str(data_path))
        log.info("Toolkit.init_option done")

        # 4. ADB 设备发现 + Controller 连接
        devices = Toolkit.find_adb_devices()
        if not devices:
            raise AdbDeviceNotFound(
                "Toolkit.find_adb_devices() 返空列表。"
                "确认模拟器已启动,且 adb server 能识别(adb devices)。"
            )
        device = _pick_device(devices)
        log.info("adb device selected: address={} adb_path={}",
                 device.address, device.adb_path)
        self._controller = AdbController(
            adb_path=device.adb_path,
            address=device.address,
            screencap_methods=device.screencap_methods,
            input_methods=device.input_methods,
            config=device.config,
        )
        conn_job = self._controller.post_connection()
        conn_job.wait()
        # maafw 5.10.4 AdbController 没 inited 属性,用 hasattr 检查
        log.info(
            "controller connected: inited={}",
            getattr(self._controller, "inited", "<no-attr>"),
        )

        # 5. 加载 resource(走 load_narutomobile_resource,做 verify)
        self._resource = load_narutomobile_resource(str(resource_path))

        # 5.5 注册 Python 自定义 action(替代 narutomobile 缺失的 C++ plugin)
        # - NonlinearSwipe: 非线性曲线 swipe
        # - GoIntoEntryByGuide: 占位(返回 False → [JumpBack] fallback)
        register_default_custom_actions(self._resource)

        # 6. Tasker bind
        self._tasker = Tasker()
        self._tasker.bind(self._resource, self._controller)
        # maafw 5.10.4 只有 Tasker 有 inited,Resource/Controller 没
        log.info("tasker bound: inited={}", self._tasker.inited)
        if not self._tasker.inited:
            raise RuntimeError(
                "Tasker.bind() 失败:inited=False。"
                "可能 ADB 连接成功但 resource/controller 状态异常。"
            )

    # ----- attributes (post-init) ---------------------------------------------

    @property
    def tasker(self) -> Any:
        if not self._initialized:
            raise RuntimeError(
                "MaaTaskerSingleton not initialized. Call .init(cfg) first."
            )
        return self._tasker

    @property
    def resource(self) -> Any:
        if not self._initialized:
            raise RuntimeError(
                "MaaTaskerSingleton not initialized. Call .init(cfg) first."
            )
        return self._resource

    @property
    def controller(self) -> Any:
        if not self._initialized:
            raise RuntimeError(
                "MaaTaskerSingleton not initialized. Call .init(cfg) first."
            )
        return self._controller

    @property
    def is_ready(self) -> bool:
        return self._initialized


# 模块级独立锁(避免和 _instance 双检锁耦合)
_init_lock = threading.Lock()


def get_tasker() -> MaaTaskerSingleton:
    """获取单例(不自动初始化,需要 caller 显式调 ``.init(cfg)``)。

    为什么不再自动 init:接 cfg 是必要参数,延迟 init 让 caller 决定何时给 cfg,
    避免在 import 阶段或单元测试里误触发 ADB 连接。
    """
    return MaaTaskerSingleton()


def reset_tasker() -> None:
    """重置单例(测试用,会让下次 get_tasker() 重新初始化)。"""
    with MaaTaskerSingleton._lock:
        MaaTaskerSingleton._instance = None


# ----- helpers ---------------------------------------------------------------


def _pick_device(devices: list[Any], preferred_addr: str | None = None) -> Any:
    """从 find_adb_devices() 返回列表里挑一个设备。

    优先匹配 preferred_addr(如 ``127.0.0.1:5555``),找不到就用第一个。
    """
    if preferred_addr:
        for d in devices:
            if getattr(d, "address", None) == preferred_addr:
                return d
    return devices[0]