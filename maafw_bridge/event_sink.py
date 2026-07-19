"""maafw_bridge.event_sink — MaaFramework 事件回调 → Python logger + TaskResult。

设计:
    - ``MaaEventSink`` 继承 ``maa.context.ContextEventSink`` —
      ContextEventSink 接收每个节点的细粒度事件(recognition/action/wait_freezes)
    - 收集每节点结果到 ``self.nodes: list[dict]``
    - ``to_task_result(success, error)`` 产 ``core.task_result.TaskResult`` —
      让上层 TaskEngine 直接复用现有 RunReport / 调度链路
    - 可选 Qt Signal — GUI 监听进度时挂 signal hook

maafw 5.10.4 ContextEventSink hooks:
    - on_node_next_list       节点跳转列表
    - on_node_recognition     识别结果
    - on_node_action          动作执行
    - on_node_wait_freezes    冻结检测

detail 字段(运行时由 C 回调填充,静态 enum 不可靠 — 用 getattr 取值,失败 None):
    - NodeRecognitionDetail: task_id / reco_id / name / focus / anchor / status / hit / algo / ...
    - NodeActionDetail:      task_id / action_id / name / focus / status / ...
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from maa.context import ContextEventSink  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    ContextEventSink = None  # type: ignore
    _MAAFW_AVAILABLE = False

# 用 TYPE_CHECKING 避免循环依赖:core 不知道 maafw_bridge
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.task_result import TaskResult


_LOG = logger.bind(component="maafw.sink")


# ----- detail attribute helpers ---------------------------------------------


def _safe_get(obj: Any, *attrs: str, default: Any = None) -> Any:
    """安全地从 maafw detail 对象取字段(失败返 default)。"""
    for a in attrs:
        try:
            v = getattr(obj, a, None)
            if v is not None:
                return v
        except Exception:  # noqa: BLE001
            continue
    return default


def _status_name(status: Any) -> str:
    """maafw 5.10.4 Status 类没暴露 .name,用 __class__.__name__ 代替。"""
    if status is None:
        return "None"
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name
    return type(status).__name__


# ----- sink class ------------------------------------------------------------


class MaaEventSink(ContextEventSink if ContextEventSink else object):
    """收集 MaaFramework 节点执行进度,产出 ``core.task_result.TaskResult``。

    用法::

        from maafw_bridge.event_sink import MaaEventSink

        sink = MaaEventSink(task_id="mail")
        # 注册到 Tasker(tasker.add_context_sink)或 TaskJob(job.add_context_sink)
        ...

        # 任务跑完后:
        result = sink.to_task_result(success=True)
    """

    def __init__(
        self,
        task_id: str,
        qt_signal: Any = None,  # 可选:QtCore.Signal(str, dict) 用于 GUI 进度
    ) -> None:
        if not _MAAFW_AVAILABLE:
            raise RuntimeError("maafw 未安装,无法创建 MaaEventSink。先 pip install maafw==5.10.4")
        self.task_id = task_id
        self.started_at = datetime.now()
        self.nodes: list[dict[str, Any]] = []
        self.recognition_count = 0
        self.action_count = 0
        self.wait_freezes_count = 0
        self.next_list_count = 0
        self._qt_signal = qt_signal
        self._last_error: str | None = None

    # ----- ContextEventSink override -----------------------------------------

    def on_node_recognition(  # type: ignore[override]
        self,
        context: Any,
        noti_type: Any,
        detail: Any,
    ) -> None:
        self.recognition_count += 1
        entry = {
            "kind": "recognition",
            "name": _safe_get(detail, "name"),
            "hit": _safe_get(detail, "hit"),
            "algo": _safe_get(detail, "algo"),
            "status": _status_name(_safe_get(detail, "status")),
            "task_id": _safe_get(detail, "task_id"),
            "reco_id": _safe_get(detail, "reco_id"),
            "timestamp": datetime.now().isoformat(),
        }
        self.nodes.append(entry)
        _LOG.debug(
            "[{}] recognition node={} algo={} hit={} status={}",
            self.task_id,
            entry["name"],
            entry["algo"],
            entry["hit"],
            entry["status"],
        )
        self._emit_qt(entry)

    def on_node_action(  # type: ignore[override]
        self,
        context: Any,
        noti_type: Any,
        detail: Any,
    ) -> None:
        self.action_count += 1
        entry = {
            "kind": "action",
            "name": _safe_get(detail, "name"),
            "status": _status_name(_safe_get(detail, "status")),
            "task_id": _safe_get(detail, "task_id"),
            "action_id": _safe_get(detail, "action_id"),
            "timestamp": datetime.now().isoformat(),
        }
        self.nodes.append(entry)
        _LOG.debug(
            "[{}] action node={} status={}",
            self.task_id,
            entry["name"],
            entry["status"],
        )
        self._emit_qt(entry)

    def on_node_wait_freezes(  # type: ignore[override]
        self,
        context: Any,
        noti_type: Any,
        detail: Any,
    ) -> None:
        self.wait_freezes_count += 1
        entry = {
            "kind": "wait_freezes",
            "name": _safe_get(detail, "name"),
            "status": _status_name(_safe_get(detail, "status")),
            "timestamp": datetime.now().isoformat(),
        }
        self.nodes.append(entry)
        _LOG.trace("[{}] wait_freezes node={}", self.task_id, entry["name"])

    def on_node_next_list(  # type: ignore[override]
        self,
        context: Any,
        noti_type: Any,
        detail: Any,
    ) -> None:
        self.next_list_count += 1
        # next_list 通常很长,只 debug 时打印
        _LOG.trace(
            "[{}] next_list node={} next={}",
            self.task_id,
            _safe_get(detail, "name"),
            _safe_get(detail, "next_list"),
        )

    # ----- Qt signal emit ----------------------------------------------------

    def _emit_qt(self, entry: dict[str, Any]) -> None:
        """如果传了 qt_signal,emit 给 GUI。"""
        sig = self._qt_signal
        if sig is None:
            return
        try:
            sig.emit(self.task_id, entry)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("qt signal emit failed: {}", exc)

    # ----- public API ---------------------------------------------------------

    def to_task_result(self, success: bool, error: str = "") -> "TaskResult":
        """产 ``core.task_result.TaskResult``。

        Args:
            success: 任务整体是否成功(True/False/"stopped")。
                     "stopped" 表示 pipeline 跑完但 .failed=True(matched Timeout /
                     max_hit,典型的 "没找到入口就 StopTask 兜底" — narutomobile 常见)。
            error: 失败时的错误消息(成功时为空)。

        Returns:
            ``TaskResult`` 实例,``extra`` 字段含 nodes 列表 + 各计数器。

        决策表:
            | success 入参          | Status     | 说明                              |
            |-----------------------|------------|-----------------------------------|
            | True                  | SUCCESS    | pipeline 真成功                   |
            | "stopped"             | SUCCESS    | pipeline 跑完,best-effort 接受   |
            | False                 | FAIL       | 真失败(异常 / Status.failed)     |
        """
        # 延迟 import 避免模块顶层拉 core
        from core.task_result import TaskResult, TaskStatus

        finished_at = datetime.now()
        duration = (finished_at - self.started_at).total_seconds()
        if success in (True, "stopped"):
            message = f"{self.recognition_count} rec + {self.action_count} act " f"in {duration:.2f}s" + (
                " [stopped/best-effort]" if success == "stopped" else ""
            )
            task_status = TaskStatus.SUCCESS
        else:
            message = error or f"task failed after {duration:.2f}s"
            task_status = TaskStatus.FAIL

        return TaskResult(
            task_id=self.task_id,
            status=task_status,
            message=message,
            started_at=self.started_at,
            finished_at=finished_at,
            duration_sec=duration,
            attempts=1,
            extra={
                "engine": "maafw",
                "nodes": list(self.nodes),
                "recognition_count": self.recognition_count,
                "action_count": self.action_count,
                "wait_freezes_count": self.wait_freezes_count,
                "next_list_count": self.next_list_count,
                "error": error or None,
                "best_effort": success == "stopped",
            },
        )

    # ----- helpers ------------------------------------------------------------

    def mark_error(self, error: str) -> None:
        """外部捕获到异常时,记录 error(供 to_task_result 用)。"""
        self._last_error = error


# ----- 旧 API 兼容(原 MaaLogEventSink,simple loguru forward)-----------------
# v2.0 方案 §5.2 只要求 MaaEventSink(ContextEventSink)。这里不保留 MaaLogEventSink
# 兼容类 — 那是 v2.0 外的额外代码,按 Simplicity First 砍掉。如果以后需要纯日志版,
# 单独加 logger-sink 子类即可,不要污染主 sink。
