"""core.config_manager — YAML 配置加载 + Pydantic v2 校验 + 默认生成 (V2 2026-07-19)。

V2 精简 (OPT-1+OPT-5 后):
    - 删 8 个死 Pydantic class: RetryConfig / RecoveryConfig / LoggingConfig /
      SchedulerConfig / StateMachineConfig / ScreenshotConfig / WindowProfile / DeviceConfig
    - 删 cfg.device (WindowManager OPT-1 删) + _DEVICE_DEFAULT
    - 删 config/device_config.yaml (commit ec6bfd4 之前)
    - 保留 cfg.app / cfg.tasks (task_registry.yaml 仍被 main.py:cmd_check 读)
    - 删 AppConfig 死字段: scheduler / state_machine / screenshot / retry / recovery / logging_ext

公开 API:
    ConfigManager(project_root: Path)
        .app      → AppConfig
        .tasks    → TaskRegistryConfig
        .reload() → None
        .save_default_configs() -> list[Path]  # 仅当文件不存在时写入
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


# ============================================================
# AppConfig 字段 (V2 删 RetryConfig/RecoveryConfig/LoggingConfig/SchedulerConfig/
# StateMachineConfig/ScreenshotConfig 8 个,2026-07-19)
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


class AppMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "naruto-auto-daily"
    version: str = "0.1.0"
    phase: int = 1
    debug: bool = False


class AppConfig(BaseModel):
    """应用全局配置 (V2 2026-07-19,OPT-1 删了 7 个死字段)。

    Attributes:
        app: 元数据 (name / version / phase / debug)
        logger: 日志配置
        adb: ADB 客户端配置 (cmd_check 用)
        template_matching: 模板匹配配置 (recognition.template_matcher 用)
        maafw: MaaFramework 桥接配置 (maafw_bridge.tasker 用)
    """

    model_config = ConfigDict(extra="ignore")

    app: AppMeta = Field(default_factory=AppMeta)
    logger: LoggerConfig = Field(default_factory=LoggerConfig)
    adb: AdbConfig = Field(default_factory=AdbConfig)
    template_matching: TemplateMatchingConfig = Field(default_factory=TemplateMatchingConfig)
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
    """任务注册表配置 (V3 2026-07-19,无 task_class 字段)。"""

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
  version: "0.7.0"
  phase: 8
  debug: false

logger:
  console_level: "INFO"
  file_level: "DEBUG"
  log_dir: "logs"
  rotation_mb: 50
  retention_days: 30
  compression: true
  auto_screenshot_on_error: true

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

# game_state 段: P2-2 (2026-07-18) 删 — GameStateConfig 无 consumer
# scheduler / state_machine / screenshot / retry / recovery / logging_ext 段
# OPT-1+OPT-5 (2026-07-19) 删 — 旧自研调度框架,统一走 MaaFramework
"""


_TASKS_DEFAULT = """# 任务注册表
# V2: 仅保留 tasks 字典 + 每个任务的 display_order 作为唯一排序来源。
# 每个 task_id 对应一个 TaskEntry,字段:
#   task_class         str    Python 类路径 (2026-07-19 V3 删,MaaFramework 走 entry 字符串)
#   enabled            bool   是否启用
#   display_order      int    排序键
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
    """加载 / 校验 / 缓存两份 YAML 配置 (app_config.yaml + task_registry.yaml)。"""

    APP_FILE = "app_config.yaml"
    TASKS_FILE = "task_registry.yaml"

    def __init__(self, project_root: Path, *, auto_load: bool = True) -> None:
        self.project_root = project_root.resolve()
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._app: AppConfig | None = None
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
    def tasks(self) -> TaskRegistryConfig:
        if self._tasks is None:
            self._tasks = self._load(self.TASKS_FILE, TaskRegistryConfig, _TASKS_DEFAULT)
        return self._tasks

    # ----- lifecycle ----------------------------------------------------

    def reload(self) -> None:
        """强制重新加载所有 YAML。"""
        self._app = self._load(self.APP_FILE, AppConfig, _APP_DEFAULT)
        self._tasks = self._load(self.TASKS_FILE, TaskRegistryConfig, _TASKS_DEFAULT)
        # 不在 reload 期间打印 logger，避免 build_context 顺序耦合；
        # 调用方负责在 logger 配置完成后报告状态。

    def save_default_configs(self) -> list[Path]:
        """对每个不存在的 YAML 文件写入默认值；返回新建的文件路径列表。"""
        created: list[Path] = []
        for fname, content in [
            (self.APP_FILE, _APP_DEFAULT),
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
