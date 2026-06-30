"""ui.scheme_manager — 方案 JSON 持久化(Phase 5)。

职责(单一):
    管理 ``schemes/<name>.json``:增删改查。

设计要点:
    - 方案文件**只**含 ``task_ids`` 列表(不存配置 / 状态 / 日志 / 实现)。
    - JSON 格式:
        {
            "task_ids": ["daily_signin", "..."]
        }
    - 默认提供 3 个 seed: ``daily.json`` / ``weekly.json`` / ``event.json``。
    - 不调任何业务模块(任务代码 / TaskEngine / 状态机 都不碰)。
    - 容错:坏 JSON / 缺字段 → 抛 ``SchemeError`` 让上层决定。

公开 API:
    SchemeManager(schemes_dir: Path)
        .list_schemes() -> list[str]
        .load(name) -> list[str] | None
        .save(name, task_ids) -> None
        .delete(name) -> bool
        .exists(name) -> bool
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["SchemeManager", "SchemeError"]


class SchemeError(RuntimeError):
    """方案文件错误(坏 JSON / 缺字段 / IO 失败)。"""


# 方案文件合法的 JSON schema
_DEFAULT_TASK_IDS: list[str] = []  # 空列表,seed 时也用空


class SchemeManager:
    """方案 JSON 持久化管理器。

    Args:
        schemes_dir: 方案目录路径(不存在会自动创建)。
    """

    #: seed 默认提供的方案(3 个)
    DEFAULT_SCHEMES: dict[str, list[str]] = {
        "daily": ["daily_signin"],
        "weekly": [],
        "event": [],
    }

    def __init__(self, schemes_dir: Path) -> None:
        self._dir = Path(schemes_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        # 启动时 seed(只 seed 不存在的,不覆盖用户改过的)
        self._seed_defaults()

    # ----- public ----------------------------------------------------

    @property
    def schemes_dir(self) -> Path:
        return self._dir

    def list_schemes(self) -> list[str]:
        """列出所有方案文件名(不含后缀)。按字母序。"""
        return sorted(
            p.stem for p in self._dir.glob("*.json") if p.is_file()
        )

    def exists(self, name: str) -> bool:
        return (self._dir / f"{name}.json").is_file()

    def load(self, name: str) -> list[str] | None:
        """加载方案;文件不存在返 None(不抛)。

        Returns:
            ``list[str]`` — task_ids 列表;空列表也是合法值。
            ``None`` — 文件不存在。

        Raises:
            SchemeError: 文件存在但 JSON 解析失败或缺 task_ids 字段。
        """
        path = self._dir / f"{name}.json"
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SchemeError(
                f"scheme '{name}' has invalid JSON: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise SchemeError(
                f"scheme '{name}' top-level must be dict, got {type(data).__name__}",
            )
        if "task_ids" not in data:
            raise SchemeError(
                f"scheme '{name}' missing required 'task_ids' field",
            )
        task_ids = data["task_ids"]
        if not isinstance(task_ids, list) or not all(
            isinstance(t, str) for t in task_ids
        ):
            raise SchemeError(
                f"scheme '{name}' task_ids must be list[str], got {type(task_ids).__name__}",
            )
        return list(task_ids)

    def save(self, name: str, task_ids: list[str]) -> None:
        """保存方案(覆盖)。空列表合法。

        Args:
            name: 方案名(不含后缀)。
            task_ids: 任务 ID 列表。

        Raises:
            SchemeError: IO 失败或 task_ids 类型不合法。
            ValueError: name 不合法(空 / 含路径分隔符)。
        """
        self._validate_name(name)
        if not isinstance(task_ids, list) or not all(
            isinstance(t, str) for t in task_ids
        ):
            raise SchemeError(
                f"task_ids must be list[str], got {type(task_ids).__name__}",
            )
        payload = {"task_ids": list(task_ids)}
        path = self._dir / f"{name}.json"
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise SchemeError(f"failed to save scheme '{name}': {exc}") from exc

    def delete(self, name: str) -> bool:
        """删除方案。返 True 表示成功删除,False 表示文件本来就不存在。

        Args:
            name: 方案名。

        Returns:
            True = 删了,False = 原本不存在。
        """
        path = self._dir / f"{name}.json"
        if not path.is_file():
            return False
        try:
            path.unlink()
        except OSError as exc:
            raise SchemeError(f"failed to delete scheme '{name}': {exc}") from exc
        return True

    # ----- internals -------------------------------------------------

    def _seed_defaults(self) -> None:
        """启动时 seed 默认方案(只 seed 不存在的)。"""
        for name, task_ids in self.DEFAULT_SCHEMES.items():
            path = self._dir / f"{name}.json"
            if not path.is_file():
                try:
                    path.write_text(
                        json.dumps(
                            {"task_ids": list(task_ids)},
                            ensure_ascii=False,
                            indent=2,
                        ) + "\n",
                        encoding="utf-8",
                    )
                except OSError:
                    # seed 失败不致命(只读环境也能跑)
                    pass

    @staticmethod
    def _validate_name(name: str) -> None:
        """方案名合法性检查:非空、不含路径分隔符、只允许 [a-zA-Z0-9_-]。"""
        if not isinstance(name, str) or not name:
            raise ValueError("scheme name must be non-empty string")
        if any(c in name for c in ("/", "\\", "..", "\0")):
            raise ValueError(
                f"scheme name '{name}' contains illegal characters",
            )
        if not all(c.isalnum() or c in "-_" for c in name):
            raise ValueError(
                f"scheme name '{name}' must be alphanumeric with - or _ only",
            )
