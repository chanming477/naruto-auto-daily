"""ui.run_worker_maafw — QThread 包 MaaTaskEngine.run_daily()(2026-07-02)。

跟 ``ui.run_worker.RunWorker`` 并行,Qt signal 接口对齐 — 两者可互换使用:

    | Signal             | RunWorker    | MaaRunWorker         |
    |--------------------|--------------|----------------------|
    | progress(task_id,  | ✅ 每 task   | ✅ 每 task(粗粒度) |
    |   TaskResult)      |              |                      |
    | finished(report)   | ✅ RunReport | ✅ _SimpleRunReport  |
    | error(message)     | ✅ 异常      | ✅ 异常              |
    | node_progress(     | ❌           | ✅ 每节点(细粒度)    |
    |   task_id,         |              |   可选,需要 engine  |
    |   node_name,       |              |   在 init 时传 signal|
    |   detail)          |              |                      |

设计:
    - ``MaaRunWorker(engine, task_ids)``: engine 是 ``MaaTaskEngine`` 实例
    - 复用 ``tasks.task_engine_maafw._SimpleRunReport``(字段对齐 core.scheduler.RunReport)
    - ``stop()``: 设 flag,下一个 task 跑前 break(maafw 本身没有 stop API,
      单个 task.run_task() 是同步阻塞的,只能等它跑完)
    - ``run()``: 串行调 ``engine.run_task(tid)``,每完成一个 emit progress,
      最后 emit finished
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.run_worker_maafw requires PySide6",
    ) from _exc

if TYPE_CHECKING:
    from core.base_task import TaskResult
    from tasks.task_engine_maafw import MaaTaskEngine


class MaaRunWorker(QtCore.QObject):
    """QObject + moveToThread 模式,跑 ``MaaTaskEngine.run_daily()``。

    用法::
        thread = QtCore.QThread()
        worker = MaaRunWorker(engine, task_ids)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.start()
    """

    # 粗粒度:每完成一个 task 发一次
    progress = QtCore.Signal(str, object)  # (task_id, TaskResult)
    # 细粒度:每个 maafw 节点执行时发(可选 — 需要 engine 在 init 时挂 signal)
    node_progress = QtCore.Signal(str, str, dict)  # (task_id, node_name, detail_dict)
    # 完成 / 异常
    finished = QtCore.Signal(object)  # _SimpleRunReport
    error = QtCore.Signal(str)

    def __init__(
        self,
        engine: "MaaTaskEngine",
        task_ids: list[str],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._task_ids = list(task_ids)
        self._stopped = False

        # 把 node_progress signal 传给 engine(细粒度进度)
        # 注意:engine 必须是新创建的 MaaTaskEngine(不能在 init 时已经传过别的 signal)
        if engine._qt_signal is None:
            engine._qt_signal = self.node_progress

    # ----- public API ---------------------------------------------------------

    def get_task_ids(self) -> list[str]:
        return list(self._task_ids)

    def stop(self) -> None:
        """请求中止。下一 task 开始前检查并 break。

        maafw 的 ``Tasker.post_task().wait()`` 是同步阻塞 — 不能中途打断。
        当前 task 跑完后下一个 task 才会响应 stop。
        """
        self._stopped = True

    @QtCore.Slot()
    def run(self) -> None:
        """QThread 入口:跑 task_ids 串行,emit progress + finished/error。"""
        from tasks.task_engine_maafw import _SimpleRunReport

        report = _SimpleRunReport()
        log = self._engine._singleton  # noqa: SLF001 — 借用 logger 不优雅但够用
        try:
            for tid in self._task_ids:
                if self._stopped:
                    report.aborted = True
                    report.abort_reason = "stop flag set before task"
                    break

                result = self._engine.run_task(tid)
                if result is None:
                    # task_id 不在 TASK_MAPPING 里,跳过
                    continue
                report.task_results.append(result)
                # 粗粒度 progress
                self.progress.emit(tid, result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"{type(exc).__name__}: {exc}")
            return

        report.finished_at = datetime.now()
        self.finished.emit(report)
