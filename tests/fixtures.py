"""tests.fixtures — 测试用任务 / context fixture。

不要在这里放任何产品代码；仅用于让 ``Scheduler.TaskFactory`` 能找到合法的
Python 类路径（``tests.fixtures.GreetTask``）。
"""

from __future__ import annotations

from core.base_task import BaseTask, ExecutionContext, TaskResult, TaskStatus


class GreetTask(BaseTask):
    """最简单的成功任务，用于 end-to-end 测试。"""

    def __init__(self) -> None:
        super().__init__()
        self.task_id = "greet"
        self.name = "Greet Task (test)"

    def run(self, ctx: ExecutionContext) -> TaskResult:
        log = ctx.bind_logger(self.task_id)
        log.info("GreetTask running")
        return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS,
                          message="hello from greet task")


class FailTask(BaseTask):
    """始终 FAIL 的任务，用于测试重试 + stop_on_failure 路径。"""

    def __init__(self) -> None:
        super().__init__()
        self.task_id = "always_fail"
        self.name = "Always Fail (test)"

    def run(self, ctx: ExecutionContext) -> TaskResult:
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL,
                          message="intentional test failure")


class SkipTask(BaseTask):
    """pre_check 返回 False 的任务。"""

    def __init__(self) -> None:
        super().__init__()
        self.task_id = "skip_me"
        self.name = "Skip Me (test)"

    def pre_check(self, ctx: ExecutionContext) -> bool:
        return False

    def run(self, ctx: ExecutionContext) -> TaskResult:
        raise AssertionError("run() should not be invoked after pre_check=False")