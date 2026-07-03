"""core.config_manager — YAML 配置加载 + Pydantic v2 校验 + 默认生成。

设计要点：
- 三份配置文件：
    config/app_config.yaml     → AppConfig
    config/device_config.yaml  → DeviceConfig
    config/task_registry.yaml  → TaskRegistryConfig
- 第一次启动时如果 YAML 文件不存在，会自动生成默认值（--init-config）。
- 已有 YAML 加载时如果字段缺失，Pydantic 会用默认值补齐并在日志里记录。
- 加载失败时抛出明确的 ConfigurationError，不静默吞掉。

公开 API：
    ConfigManager(project_root: Path)
        .app      → AppConfig
        .device   → DeviceConfig
        .tasks    → TaskRegistryConfig
        .reload() → None
        .save_default_configs() -> list[Path]  # 仅当文件不存在时写入
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MatchMode = Literal["title_contains", "title_equals", "class_name", "pid", "any"]
ScreenshotBackend = Literal["win32_print_window", "mss_full_screen"]


# ============================================================
# Phase 2 增量: ADB / TemplateMatching / GameState / Phase2 配置
# ============================================================


class AdbConfig(BaseModel):
    """ADBClient 配置。

    Attributes:
        adb_path: ADB 可执行路径,空字符串 = 从 PATH 自动找。
        default_serial: 默认设备序列号(如 ``"127.0.0.1:7555"``),空 = 不指定。
        command_timeout_sec: 单条 adb 命令的超时。
        retry_count: 失败重试次数(>0)。
    """

    model_config = ConfigDict(extra="ignore")

    adb_path: str = ""
    default_serial: str = ""
    command_timeout_sec: float = Field(default=10.0, ge=0.5, le=120.0)
    retry_count: int = Field(default=2, ge=1, le=10)


class TemplateMatchingConfig(BaseModel):
    """TemplateMatcher 配置。

    Attributes:
        default_threshold: 默认匹配阈值 [0.0, 1.0]。
        multi_scale: 是否启用多尺度匹配(Phase 2 不实现,仅占位)。
        multi_scale_range: 多尺度缩放范围(占位)。
    """

    model_config = ConfigDict(extra="ignore")

    default_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    multi_scale: bool = False
    multi_scale_range: list[float] = Field(default_factory=lambda: [0.95, 1.0, 1.05])


class GameStateConfig(BaseModel):
    """GameStateMachine 配置。

    Attributes:
        initial_state: 启动时初始 GameState 字符串;由调用方在运行时用
            ``GameState(value)`` 校验并 fallback(避免 core.config_manager 反向依赖 state 模块)。
        templates_dir: 模板根目录(相对 project_root);默认 ``resources/templates``。
        recovery_probe_max: ``recover()`` 时最多调用 probe 多少次(留给调用方参考)。
    """

    model_config = ConfigDict(extra="ignore")

    initial_state: str = "UNKNOWN"
    templates_dir: str = "resources/templates"
    recovery_probe_max: int = Field(default=3, ge=1, le=20)


# ============================================================
# Phase 4 增量: Retry / Recovery / Logging 配置
# ============================================================


class RetryConfig(BaseModel):
    """``RetryManager`` 默认重试策略。

    Attributes:
        max_attempts: 最大尝试次数(含首次);<=1 表示不重试。
        delay_seconds: 第一次重试前等待秒数;后续按 ``exponential_backoff`` 翻倍。
        exponential_backoff: True 时 delay 按 2^(n-1) 翻倍(1→2→4→8),
            False 时固定 ``delay_seconds``。
        max_delay_seconds: 退避上限,避免 delay 无界增长。
        retryable_exceptions: 允许重试的异常类名字符串列表(空 = 全部重试)。
            用字符串避免 ``recovery`` 模块反向 import ``device.adb_client`` 内部的
            ADBTimeoutError / ADBError 等具体类型。
    """

    model_config = ConfigDict(extra="ignore")

    max_attempts: int = Field(default=3, ge=1, le=20)
    delay_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    exponential_backoff: bool = True
    max_delay_seconds: float = Field(default=30.0, ge=0.1, le=300.0)
    retryable_exceptions: list[str] = Field(default_factory=list)


class RecoveryConfig(BaseModel):
    """``RecoveryManager`` 4 个恢复方法的阈值。

    Attributes:
        max_unknown_retries: ``recover_unknown`` 最多截图重试次数。
        max_popup_retries: ``recover_popup`` 最多重试关闭次数。
        max_loading_seconds: ``recover_loading_timeout`` 最长等待 LOADING 结束的秒数。
        adb_reconnect_attempts: ``recover_adb_error`` 重连 ADB 次数。
    """

    model_config = ConfigDict(extra="ignore")

    max_unknown_retries: int = Field(default=3, ge=1, le=20)
    max_popup_retries: int = Field(default=3, ge=1, le=20)
    max_loading_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    adb_reconnect_attempts: int = Field(default=2, ge=1, le=10)


class LoggingConfig(BaseModel):
    """日志扩展配置(Phase 4 占位,本期无实际字段)。

    之前定义过 ``capture_transitions`` / ``log_state_changes`` 两个字段,
    但代码中无人读取(P1-OVER-01 死配置)。删掉,后续如需可再加。
    占位保留,等真实需求时再补具体字段。
    """

    model_config = ConfigDict(extra="ignore")


# ============================================================
# Pydantic models
# ============================================================


class LoggerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    console_level: str = "INFO"
    file_level: str = "DEBUG"
    log_dir: str = "logs"
    rotation_mb: int = Field(default=50, ge=1, le=2048)
    retention_days: int = Field(default=30, ge=1, le=365)
    compression: bool = True
    auto_screenshot_on_error: bool = True

    @field_validator("console_level", "file_level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        valid = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
        v_up = v.upper()
        if v_up not in valid:
            raise ValueError(f"invalid log level '{v}'; must be one of {sorted(valid)}")
        return v_up


class SchedulerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stop_on_failure: bool = False
    inter_task_delay_sec: float = Field(default=1.0, ge=0.0, le=60.0)
    startup_warmup_sec: float = Field(default=3.0, ge=0.0, le=60.0)
    task_timeout_sec: int = Field(default=300, ge=0, le=86400)
    heartbeat_interval_sec: int = Field(default=30, ge=1, le=3600)


class StateMachineConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    initial_state: str = "IDLE"
    failure_state: str = "FAILED"
    success_state: str = "COMPLETED"
    log_transitions: bool = True


class ScreenshotConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    output_dir: str = "screenshots"
    backend: ScreenshotBackend = "win32_print_window"
    to_grayscale: bool = False
    max_empty_retries: int = Field(default=3, ge=1, le=10)
    retry_delay_ms: int = Field(default=200, ge=0, le=5000)


class AppMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "naruto-auto-daily"
    version: str = "0.1.0"
    phase: int = 1
    debug: bool = False


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app: AppMeta = Field(default_factory=AppMeta)
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    state_machine: StateMachineConfig = Field(default_factory=StateMachineConfig)
    screenshot: ScreenshotConfig = Field(default_factory=ScreenshotConfig)
    # ---- Phase 2 增量字段(向后兼容,缺失则用默认值)----
    adb: AdbConfig = Field(default_factory=AdbConfig)
    template_matching: TemplateMatchingConfig = Field(default_factory=TemplateMatchingConfig)
    game_state: GameStateConfig = Field(default_factory=GameStateConfig)
    # ---- Phase 4 增量字段(向后兼容,缺失则用默认值)----
    retry: RetryConfig = Field(default_factory=RetryConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)
    logging_ext: LoggingConfig = Field(default_factory=LoggingConfig)
    # ---- Phase 8 增量 (2026-07-02) — MaaFramework 桥接配置 ----
    maafw: "MaaConfig" = Field(default_factory=lambda: MaaConfig())


class MaaConfig(BaseModel):
    """MaaFramework 桥接配置 (Phase 8)。

    Attributes:
        narutomobile_resource_path: narutomobile resource/base 路径。
            留空 = 用 ``{project_root}/resources/narutomobile/`` 默认值。
            填绝对路径覆盖(如指向外部 narutomobile 安装目录)。
        data_dir: maafw Toolkit 初始化目录(log + cache 落盘位置),
            相对 project_root。留空 = 默认 ``logs/maafw_data``。
    """
    model_config = ConfigDict(extra="ignore")

    narutomobile_resource_path: str = Field(default="")
    data_dir: str = Field(default="logs/maafw_data")


class WindowProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    match_mode: MatchMode = "title_contains"
    match_keywords: list[str] = Field(default_factory=list)
    process_whitelist: list[str] = Field(default_factory=list)
    process_blacklist: list[str] = Field(
        default_factory=lambda: [
            "explorer.exe",
            "dwm.exe",
            "ShellExperienceHost.exe",
            "SearchHost.exe",
            "TextInputHost.exe",
        ]
    )
    require_visible: bool = True
    require_not_minimized: bool = True
    expected_width: int = Field(default=0, ge=0, le=16384)
    expected_height: int = Field(default=0, ge=0, le=16384)


class DeviceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active_profile: str = "default"
    profiles: dict[str, WindowProfile] = Field(
        default_factory=lambda: {"default": WindowProfile()}
    )

    def active(self) -> WindowProfile:
        if self.active_profile not in self.profiles:
            raise ConfigurationError(
                f"active_profile '{self.active_profile}' not found in profiles "
                f"{list(self.profiles.keys())}"
            )
        return self.profiles[self.active_profile]


class TaskEntry(BaseModel):
    """Phase 2+ 才会填充；Phase 1 保留 schema 占位。"""

    model_config = ConfigDict(extra="ignore")

    task_class: str = ""
    enabled: bool = True
    display_order: int = 0
    category: str = "uncategorized"
    description: str = ""
    estimated_time_sec: int = 0
    retry_on_failure: bool = True
    max_retries: int = Field(default=2, ge=0, le=10)
    config_options: dict[str, Any] = Field(default_factory=dict)


class TaskRegistryConfig(BaseModel):
    """任务注册表配置。

    V2 修正: 删除 ``schedule_order`` 字段。
    Scheduler 只按 ``display_order`` 升序排列所有 ``enabled=True`` 的任务,
    避免两套排序规则造成配置冲突。
    """

    model_config = ConfigDict(extra="ignore")

    tasks: dict[str, TaskEntry] = Field(default_factory=dict)


# ============================================================
# Errors
# ============================================================


class ConfigurationError(RuntimeError):
    """配置加载 / 校验失败。"""


# ============================================================
# Defaults (raw YAML strings used by save_default_configs)
# ============================================================


_APP_DEFAULT = """# 全局应用配置
app:
  name: "naruto-auto-daily"
  version: "0.2.0"
  phase: 2
  debug: false

logger:
  console_level: "INFO"
  file_level: "DEBUG"
  log_dir: "logs"
  rotation_mb: 50
  retention_days: 30
  compression: true
  auto_screenshot_on_error: true

scheduler:
  stop_on_failure: false
  inter_task_delay_sec: 1.0
  startup_warmup_sec: 3.0
  task_timeout_sec: 300
  heartbeat_interval_sec: 30

state_machine:
  initial_state: "IDLE"
  failure_state: "FAILED"
  success_state: "COMPLETED"
  log_transitions: true

screenshot:
  output_dir: "screenshots"
  backend: "win32_print_window"
  to_grayscale: false
  max_empty_retries: 3
  retry_delay_ms: 200

# ============ Phase 2 ============
adb:
  adb_path: ""               # 空 = 从 PATH 自动找 adb
  default_serial: ""         # 空 = 不指定序列号,adb devices 自动选
  command_timeout_sec: 10
  retry_count: 2

template_matching:
  default_threshold: 0.85
  multi_scale: false
  multi_scale_range: [0.95, 1.0, 1.05]

game_state:
  initial_state: "UNKNOWN"   # HOME / POPUP / LOADING / UNKNOWN
  templates_dir: "resources/templates"
  recovery_probe_max: 3

# ============ Phase 4: 稳定性体系 ============
retry:
  max_attempts: 3
  delay_seconds: 1.0
  exponential_backoff: true
  max_delay_seconds: 30.0
  retryable_exceptions: []  # 空 = 全部异常都重试;非空 = 只重试列出的异常类名

recovery:
  max_unknown_retries: 3
  max_popup_retries: 3
  max_loading_seconds: 60.0
  adb_reconnect_attempts: 2

# logging_ext: 暂无字段(P1-OVER-01 删了 capture_transitions / log_state_changes 死配置)
logging_ext: {}
"""

_DEVICE_DEFAULT = """# 窗口 / 设备配置
active_profile: "default"

profiles:
  default:
    match_mode: "title_contains"
    match_keywords:
      - "模拟器"
      - "MuMu"
      - "雷电"
      - "Nox"
      - "NARUTO"
      - "火影"
    process_whitelist: []
    process_blacklist:
      - "explorer.exe"
      - "dwm.exe"
      - "ShellExperienceHost.exe"
      - "SearchHost.exe"
      - "TextInputHost.exe"
    require_visible: true
    require_not_minimized: true
    expected_width: 0
    expected_height: 0
"""

_TASKS_DEFAULT = """# 任务注册表
# V2: 仅保留 tasks 字典 + 每个任务的 display_order 作为唯一排序来源。
# 每个 task_id 对应一个 TaskEntry,字段:
#   task_class         str    Python 类路径
#   enabled            bool   是否启用
#   display_order      int    排序键(Scheduler 按此升序)
#   category           str    分类
#   description        str
#   estimated_time_sec int
#   retry_on_failure   bool
#   max_retries        int
#   config_options     dict   任务级配置
tasks: {}
"""


# ============================================================
# Manager
# ============================================================


class ConfigManager:
    """加载 / 校验 / 缓存三份 YAML 配置。"""

    APP_FILE = "app_config.yaml"
    DEVICE_FILE = "device_config.yaml"
    TASKS_FILE = "task_registry.yaml"

    def __init__(self, project_root: Path, *, auto_load: bool = True) -> None:
        self.project_root = project_root.resolve()
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._app: AppConfig | None = None
        self._device: DeviceConfig | None = None
        self._tasks: TaskRegistryConfig | None = None

        if auto_load:
            self.reload()

    # ----- accessors ----------------------------------------------------

    @property
    def app(self) -> AppConfig:
        if self._app is None:
            self._app = self._load(self.APP_FILE, AppConfig, _APP_DEFAULT)
        return self._app

    @property
    def device(self) -> DeviceConfig:
        if self._device is None:
            self._device = self._load(self.DEVICE_FILE, DeviceConfig, _DEVICE_DEFAULT)
        return self._device

    @property
    def tasks(self) -> TaskRegistryConfig:
        if self._tasks is None:
            self._tasks = self._load(self.TASKS_FILE, TaskRegistryConfig, _TASKS_DEFAULT)
        return self._tasks

    # ----- lifecycle ----------------------------------------------------

    def reload(self) -> None:
        """强制重新加载所有 YAML。"""
        self._app = self._load(self.APP_FILE, AppConfig, _APP_DEFAULT)
        self._device = self._load(self.DEVICE_FILE, DeviceConfig, _DEVICE_DEFAULT)
        self._tasks = self._load(self.TASKS_FILE, TaskRegistryConfig, _TASKS_DEFAULT)
        # 不在 reload 期间打印 logger，避免 build_context 顺序耦合；
        # 调用方负责在 logger 配置完成后报告状态。

    def save_default_configs(self) -> list[Path]:
        """对每个不存在的 YAML 文件写入默认值；返回新建的文件路径列表。"""
        created: list[Path] = []
        for fname, content in [
            (self.APP_FILE, _APP_DEFAULT),
            (self.DEVICE_FILE, _DEVICE_DEFAULT),
            (self.TASKS_FILE, _TASKS_DEFAULT),
        ]:
            target = self.config_dir / fname
            if target.exists():
                logger.debug("config file already exists, skip: {}", target)
                continue
            target.write_text(content, encoding="utf-8")
            created.append(target)
            logger.info("created default config: {}", target)
        return created

    # ----- backup helpers ----------------------------------------------

    def backup(self, source_yaml: Path) -> Path | None:
        """备份一个 YAML 文件，返回新备份路径；源文件不存在则返回 None。"""
        if not source_yaml.exists():
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = source_yaml.with_suffix(f".{ts}.bak")
        shutil.copy2(source_yaml, backup_path)
        return backup_path

    # ----- internals ----------------------------------------------------

    def _load(self, filename: str, model: type[BaseModel], default: str) -> BaseModel:
        path = self.config_dir / filename
        if not path.exists():
            # 自动生成默认值文件，再加载。
            path.write_text(default, encoding="utf-8")
            logger.warning("config missing, auto-generated default: {}", path)

        # 加载 + 校验。失败时 backup 原文件 + 重写默认值，避免启动阻塞。
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            backup_path = self.backup(path)
            logger.error(
                "invalid YAML in {}: {}; backed up to {} and rewriting defaults",
                path, exc, backup_path,
            )
            path.write_text(default, encoding="utf-8")
            raw = yaml.safe_load(default) or {}

        if not isinstance(raw, dict):
            backup_path = self.backup(path)
            logger.error(
                "top-level of {} must be a mapping (got {}); backed up to {} and rewriting defaults",
                path, type(raw).__name__, backup_path,
            )
            path.write_text(default, encoding="utf-8")
            raw = yaml.safe_load(default) or {}

        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            backup_path = self.backup(path)
            logger.error(
                "validation failed for {}:\n{}\nbacked up to {} and rewriting defaults",
                path, exc, backup_path,
            )
            path.write_text(default, encoding="utf-8")
            # 用纯默认值构建一个新实例，缺失字段由 Pydantic 自动补齐
            return model.model_validate({})