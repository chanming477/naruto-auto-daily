"""agent.custom.action — Agent 模式下的 CustomAction 注册。

跟 ``maafw_bridge.custom_actions`` 是平行的入口:
    - ``maafw_bridge.custom_actions`` — Direct API 模式 (Python 自己管 Resource)
        用 ``class NonlinearSwipeAction(CustomAction if CustomAction else object)`` 继承
    - ``agent.custom.action``     — Agent 模式 (MFAAvalonia 管 Resource,Python 是子进程)
        用 ``@AgentServer.custom_action`` 装饰器

两套入口的 ``run()`` 都调 ``maafw_bridge._actions_core`` 同一份核心逻辑。

**重要**: 装饰器 ``@AgentServer.custom_action`` 内部会 ``action()`` 实例化并访问
``action.c_handle`` (从 ``CustomAction`` 基类继承)。如果子类不继承,会抛
``AttributeError: 'XxxAction' object has no attribute 'c_handle'``。

子类 ``run()`` 签名是 ``(self, context, argv: Any)`` (跟基类 abstract ``run`` 不同) —
Python 不检查签名,只看方法名。
"""

from __future__ import annotations

from typing import Any

try:
    from maa.agent.agent_server import AgentServer  # type: ignore
    from maa.custom_action import CustomAction  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    AgentServer = None  # type: ignore
    CustomAction = None  # type: ignore
    _MAAFW_AVAILABLE = False

from maafw_bridge import _actions_core

from agent.utils.logger import get_agent_logger
from agent.custom.reco import increment_counter

_log = get_agent_logger()


# ============================================================
# Agent 模式包装 — 装饰器 + 继承 CustomAction (c_handle 必需)
# ============================================================
if _MAAFW_AVAILABLE and CustomAction is not None and AgentServer is not None:

    @AgentServer.custom_action("NonlinearSwipe")
    class NonlinearSwipeAction(CustomAction):
        """NonlinearSwipe (Agent 模式) — 注册到 MFAAvalonia 的 AgentServer。

        核心逻辑在 ``maafw_bridge._actions_core.nonlinear_swipe_run``。
        """

        def run(  # type: ignore[override]
            self,
            context: Any,
            argv: Any,
        ) -> bool:
            return _actions_core.nonlinear_swipe_run(context, argv)

    @AgentServer.custom_action("GoIntoEntryByGuide")
    class GoIntoEntryByGuideAction(CustomAction):
        """GoIntoEntryByGuide (Agent 模式) — 注册到 MFAAvalonia 的 AgentServer。

        核心逻辑在 ``maafw_bridge._actions_core.go_into_entry_by_guide_run``。
        """

        def run(  # type: ignore[override]
            self,
            context: Any,
            argv: Any,
        ) -> bool:
            return _actions_core.go_into_entry_by_guide_run(context, argv)

    @AgentServer.custom_action("CleanLogs")
    class CleanLogsAction(CustomAction):
        """CleanLogs (Agent 模式) — 注册到 MFAAvalonia 的 AgentServer。

        核心逻辑在 ``maafw_bridge._actions_core.clean_logs_run``。
        维护性 task,清理 logs/ 旧 session debug + MFAAvalonia/debug/ 备份。
        """

        def run(  # type: ignore[override]
            self,
            context: Any,
            argv: Any,
        ) -> bool:
            return _actions_core.clean_logs_run(context, argv)

    @AgentServer.custom_action("CounterIncrement")
    class CounterIncrementAction(CustomAction):
        """CounterIncrement (Agent 模式) — 计数器 +1。

        给当前 task_id 在内存中的计数器 +1,用于 IsCounterOverflow
        检测是否超过 max_hit 限制。
        来源: MaaAutoNaruto v1.3.41。
        """

        def run(  # type: ignore[override]
            self,
            context: Any,
            argv: Any,
        ) -> bool:
            task_id = getattr(argv, "task_detail", None)
            if task_id is not None:
                tid = getattr(task_id, "task_id", "unknown")
            else:
                tid = "unknown"
            count = increment_counter(tid)
            _log.debug("CounterIncrement: task={} count={}", tid, count)
            return True

    @AgentServer.custom_action("StopTaskList")
    class StopTaskListAction(CustomAction):
        """StopTaskList (Agent 模式) — 停止当前及后续任务。

        调用 tasker.post_stop() 终止整个任务队列。
        来源: MaaAutoNaruto v1.3.41。
        """

        def run(  # type: ignore[override]
            self,
            context: Any,
            argv: Any,
        ) -> bool:
            _log.warning("StopTaskList: 请求停止任务队列")
            try:
                context.tasker.post_stop()
            except Exception as exc:
                _log.error("StopTaskList: post_stop 失败: {}", exc)
            return False  # 返 False 让 pipeline 走错误分支

    @AgentServer.custom_action("RetryFailed")
    class RetryFailedAction(CustomAction):
        """RetryFailed (Agent 模式) — 失败重试占位。

        在重试前截屏 + 记录状态,方便调试。实际重试逻辑由
        merged.json 的 [JumpBack] 机制处理。
        来源: MaaAutoNaruto v1.3.41。
        """

        def run(  # type: ignore[override]
            self,
            context: Any,
            argv: Any,
        ) -> bool:
            _log.info("RetryFailed: 触发失败重试")
            try:
                # 截屏保存现场
                ctrl = context.tasker.controller
                ctrl.post_screencap().wait()
            except Exception as exc:
                _log.warning("RetryFailed: 截屏失败: {}", exc)
            return True

    _log.info(
        "Agent 模式 custom action 已注册: "
        "NonlinearSwipe, GoIntoEntryByGuide, CleanLogs, "
        "CounterIncrement, StopTaskList, RetryFailed"
    )
else:
    _log.warning(
        "maa.agent.agent_server / maa.custom_action 不可用,Agent 模式 custom action 注册跳过"
    )
