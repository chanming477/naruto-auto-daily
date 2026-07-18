"""maafw_bridge.custom_actions — Direct API 模式 (Python 当 Tasker 主人) 的 CustomAction 包装。

**方案 A (2026-07-15) 改动**:
    核心逻辑提取到 ``maafw_bridge._actions_core`` (NonlinearSwipe / GoIntoEntryByGuide),
    本文件只剩:
        - Direct API 模式专用的 ``CustomAction`` 继承包装 (Python 自己管 Tasker)
        - ``register_default_custom_actions()`` 入口 (Direct API 模式从 Python 端注册)

    Agent 模式 (MFAAvalonia 当主人, Python 跑子进程) 用 ``agent.custom.action``
    装饰器注册,核心逻辑也调 ``_actions_core`` — 两模式共用一份核心代码。

**调用来源**: ``maafw_bridge.MaaTaskerSingleton.init()`` 完成后,自动调
``register_default_custom_actions(resource)`` 把 2 个 action 注册到 Resource。
"""

from __future__ import annotations

from typing import Any

try:
    from maa.context import Context  # type: ignore
    from maa.custom_action import CustomAction  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    CustomAction = None  # type: ignore
    Context = None  # type: ignore
    _MAAFW_AVAILABLE = False

from loguru import logger

from . import _actions_core

_LOG = logger.bind(component="maafw.custom_action")


# ============================================================
# Direct API 模式包装 — 继承 CustomAction,内部调 _actions_core 核心逻辑
# ============================================================
class NonlinearSwipeAction(CustomAction if CustomAction else object):
    """NonlinearSwipe (Direct API 模式) — 继承 CustomAction 注册到 Python 自己的 Resource。

    核心逻辑在 ``_actions_core.nonlinear_swipe_run``。
    """

    def run(  # type: ignore[override]
        self,
        context: "Context",
        argv: Any,
    ) -> bool:
        return _actions_core.nonlinear_swipe_run(context, argv)


class GoIntoEntryByGuideAction(CustomAction if CustomAction else object):
    """GoIntoEntryByGuide (Direct API 模式) — 继承 CustomAction 注册到 Python 自己的 Resource。

    核心逻辑在 ``_actions_core.go_into_entry_by_guide_run``。
    """

    def run(  # type: ignore[override]
        self,
        context: "Context",
        argv: Any,
    ) -> bool:
        return _actions_core.go_into_entry_by_guide_run(context, argv)


class CleanLogsAction(CustomAction if CustomAction else object):
    """CleanLogs (Direct API 模式) — 继承 CustomAction 注册到 Python 自己的 Resource。

    核心逻辑在 ``_actions_core.clean_logs_run``。
    """

    def run(  # type: ignore[override]
        self,
        context: "Context",
        argv: Any,
    ) -> bool:
        return _actions_core.clean_logs_run(context, argv)


# ============================================================
# 注册入口 — Direct API 模式专用
# ============================================================
def register_default_custom_actions(resource: Any) -> dict[str, bool]:
    """注册自定义 action 到 resource (Direct API 模式,Python 自己管 Resource)。

    Args:
        resource: maa.resource.Resource 实例(已 post_bundle 完成)。

    Returns:
        ``{action_name: registered}`` 字典,True 表示注册成功。
    """
    if not _MAAFW_AVAILABLE or resource is None:
        return {}

    results: dict[str, bool] = {}
    for name, cls in (
        ("NonlinearSwipe", NonlinearSwipeAction),
        ("GoIntoEntryByGuide", GoIntoEntryByGuideAction),
        ("CleanLogs", CleanLogsAction),
    ):
        try:
            instance = cls()
            resource.register_custom_action(name, instance)
            results[name] = True
            _LOG.info("registered custom action: {}", name)
        except Exception as exc:  # noqa: BLE001
            results[name] = False
            _LOG.warning("failed to register custom action {}: {}", name, exc)
    return results


# ============================================================
# 公开符号 — re-export param 解析 helper,让 Direct API 模式下其他模块能用
parse_custom_action_param = _actions_core.parse_custom_action_param
