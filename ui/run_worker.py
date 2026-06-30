"""ui.run_worker — QThread 包 TaskEngine.run_all()。

职责(单一):
    在 QThread 里跑 ``TaskEngine.run_all()``,通过 Qt signal 报告进度。

设计要点:
    - 包装 ``TaskEngine.run_all()``,**不**实现任务 / 调度 / 恢复逻辑
    - 通过 Qt signal 报告:
        - ``progress(task_id, TaskResult)`` — 每完成一个任务
        - ``finished(RunReport)`` — 全部完成
        - ``error(str)`` — 异常
    - 停止:外部调 ``stop()`` 转发到 ``TaskEngine.stop()``(request_abort)
    - 不持有任何业务状态(只引用传入的 TaskEngine + task_ids)

公开 API:
    RunWorker(engine: TaskEngine, task_ids: list[str], parent=None)
        .start() -> None               # 启动 QThread
        .stop() -> None                # 转发到 engine.stop()
        .wait(timeout_ms=...) -> bool
        .progress = Signal(str, object)
        .finished = Signal(object)
        .error = Signal(str)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.run_worker requires PySide6",
    ) from _exc

if TYPE_CHECKING:
    from core.base_task import TaskResult
    from core.scheduler import RunReport
    from tasks.task_engine import TaskEngine


class RunWorker(QtCore.QObject):
    """QObject + moveToThread 模式,跑 ``TaskEngine.run_all()``。

    用法:
        thread = QtCore.QThread()
        worker = RunWorker(engine, task_ids)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.start()
    """

    progress = QtCore.Signal(str, object)  # (task_id, TaskResult)
    finished = QtCore.Signal(object)        # RunReport
    error = QtCore.Signal(str)               # error message

    def __init__(
        self,
        engine: "TaskEngine",
        task_ids: list[str],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._task_ids = list(task_ids)
        # 用于在 run() 内部区分每个 task 的 result
        self._seen_results = 0

    # ----- public ----------------------------------------------------

    def get_task_ids(self) -> list[str]:
        return list(self._task_ids)

    def stop(self) -> None:
        """请求中止(QThread 主线程调,转发到 TaskEngine.stop())。"""
        self._engine.stop()

    @QtCore.Slot()
    def run(self) -> None:
        """QThread 入口:跑 TaskEngine.run_all() 并 report。"""
        try:
            report = self._engine.run_all(self._task_ids)
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}")
            return
        # 每个 task 的 result 单独发 progress
        for r in report.task_results:
            self.progress.emit(r.task_id, r)
        self.finished.emit(report)
