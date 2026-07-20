"""agent.custom.reco — CustomRecognition 注册 (Agent 模式)。

注册 3 个 CustomRecognition,全部来自 MaaAutoNaruto v1.3.41:
    - IsInNinjaGuide: 检测是否在忍者指引界面
    - IsCounterOverflow: 计数器溢出检测 (积分赛/秘境/周胜重复次数限制)
    - MissionOfficeStrategy: 集会所贪心策略 (是否刷新任务)

来源: MaaAutoNaruto v1.3.41 ``agent/custom/reco.py``。
"""

from __future__ import annotations

import json
import re
from typing import Any

try:
    from maa.agent.agent_server import AgentServer  # type: ignore
    from maa.custom_recognition import CustomRecognition  # type: ignore

    _MAAFW_AVAILABLE = True
except ImportError:  # pragma: no cover
    AgentServer = None  # type: ignore
    CustomRecognition = None  # type: ignore
    _MAAFW_AVAILABLE = False

from agent.utils.logger import get_agent_logger

_log = get_agent_logger()


# ============================================================
# 工具函数 — OCR 数字读取 (参考项目移植)
# ============================================================
def _get_number_from_roi(
    context: Any, image: Any, roi: list[int], text_modifier=None
) -> int | None:
    """从指定 ROI OCR 读取纯数字。

    Args:
        context: maa context。
        image: 截屏 numpy array。
        roi: [x, y, w, h]。
        text_modifier: 可选,对 OCR 原始文本做预处理 (lambda x: x)。

    Returns:
        解析后的 int,失败返回 None。
    """
    if text_modifier is None:
        text_modifier = lambda x: x

    reco_detail = context.run_recognition(
        "custom_ocr", image, {"custom_ocr": {"roi": roi}}
    )
    if reco_detail is None or not reco_detail.hit:
        _log.debug(f"ROI{roi}: 未识别到文本")
        return None

    source_text = str(reco_detail.best_result.text).strip()  # type: ignore
    modified = text_modifier(source_text)

    num_match = re.search(r"\d+", modified)
    if not num_match:
        _log.debug(f"ROI{roi}: 未提取到数字, 文本={modified}")
        return None

    try:
        return int(num_match.group())
    except ValueError:
        _log.warning(f"ROI{roi}: 数字转换失败, 文本={modified}")
        return None


# ============================================================
# CustomRecognition 注册
# ============================================================
if _MAAFW_AVAILABLE and AgentServer is not None:

    @AgentServer.custom_recognition("IsInNinjaGuide")
    class IsInNinjaGuide(CustomRecognition):
        """是否在忍界指引界面。

        模板匹配 ``in_ninja_guide`` 节点 (SharedNode/in_ninja_guide.png)。
        命中返回 dummy box,未命中返回空 box。

        来源: MaaAutoNaruto v1.3.41。
        """

        def analyze(
            self,
            context: Any,
            argv: CustomRecognition.AnalyzeArg,  # type: ignore[valid-type]
        ) -> CustomRecognition.AnalyzeResult:  # type: ignore[valid-type]
            reco_detail = context.run_recognition(
                "in_ninja_guide", argv.image, {}
            )
            if reco_detail and reco_detail.hit:
                return CustomRecognition.AnalyzeResult(
                    box=(0, 0, 1, 1), detail={}
                )
            _log.debug("IsInNinjaGuide: 未在忍者指引界面")
            return CustomRecognition.AnalyzeResult(box=None, detail={})

    @AgentServer.custom_recognition("IsCounterOverflow")
    class IsCounterOverflow(CustomRecognition):
        """计数器溢出检测。

        custom_recognition_param: ``{"max_hit": <int>}``

        每次执行计数器 +1,超过 max_hit 时返回未命中 (阻止继续)。
        用于积分赛挑战次数 / 秘境重复挑战 / 周胜再打一把 等场景。

        来源: MaaAutoNaruto v1.3.41。
        """

        def analyze(
            self,
            context: Any,
            argv: CustomRecognition.AnalyzeArg,  # type: ignore[valid-type]
        ) -> CustomRecognition.AnalyzeResult:  # type: ignore[valid-type]
            param = json.loads(argv.custom_recognition_param)
            max_hit = int(param.get("max_hit", "0"))

            if max_hit <= 0:
                _log.error("IsCounterOverflow: max_hit 参数 <= 0, 停止任务")
                context.tasker.post_stop()
                return CustomRecognition.AnalyzeResult(box=None, detail={})

            task_id = argv.task_detail.task_id
            now_count = _get_counter_count(task_id)
            if now_count >= max_hit:
                _log.info(
                    f"IsCounterOverflow: 达到上限 task={task_id} "
                    f"count={now_count} max={max_hit}"
                )
                return CustomRecognition.AnalyzeResult(box=None, detail={})

            _log.debug(
                f"IsCounterOverflow: task={task_id} "
                f"count={now_count}/{max_hit}"
            )
            return CustomRecognition.AnalyzeResult(
                box=(0, 0, 1, 1), detail={}
            )

    @AgentServer.custom_recognition("MissionOfficeStrategy")
    class MissionOfficeStrategy(CustomRecognition):
        """集会所贪心策略: 判断是否刷新任务。

        读取两个数字:
          - 刷新上限 ROI: [1004, 614, 27, 27]
          - 可接取数 ROI: [1003, 648, 22, 28]

        公式: (刷新上限 - 9) * 1.5 >= 可接取数 → 继续刷新
        否则 → 停止刷新 (安全策略)

        来源: MaaAutoNaruto v1.3.41。
        """

        MAX_RESOURCE_ROI = [1004, 614, 27, 27]
        CURRENT_RESOURCE_ROI = [1003, 648, 22, 28]

        def analyze(
            self,
            context: Any,
            argv: CustomRecognition.AnalyzeArg,  # type: ignore[valid-type]
        ) -> CustomRecognition.AnalyzeResult:  # type: ignore[valid-type]
            _log.info("MissionOfficeStrategy: 执行集会所策略判断")

            max_resource = _get_number_from_roi(
                context, argv.image, self.MAX_RESOURCE_ROI
            )
            current_resource = _get_number_from_roi(
                context, argv.image, self.CURRENT_RESOURCE_ROI
            )

            if max_resource is None or current_resource is None:
                _log.warning(
                    "MissionOfficeStrategy: 数字识别失败, 安全停止刷新"
                )
                return CustomRecognition.AnalyzeResult(box=None, detail={})

            _log.info(
                f"MissionOfficeStrategy: 刷新上限={max_resource}, "
                f"可接取={current_resource}"
            )

            # 贪心公式: 期望每次刷新出 1.5 个神秘箱子任务
            if (max_resource - 9) * 1.5 >= current_resource:
                _log.info("MissionOfficeStrategy: 继续刷新 (贪心)")
                return CustomRecognition.AnalyzeResult(
                    box=(0, 0, 1, 1), detail={}
                )
            else:
                _log.info("MissionOfficeStrategy: 停止刷新 (安全)")
                return CustomRecognition.AnalyzeResult(box=None, detail={})

    _log.info(
        "Agent 模式 custom recognition 已注册: "
        "IsInNinjaGuide, IsCounterOverflow, MissionOfficeStrategy"
    )


# ============================================================
# 计数器辅助函数 (供 IsCounterOverflow 使用)
# ============================================================
_counter_cache: dict[str, int] = {}


def _get_counter_count(task_id: str) -> int:
    """获取 task 当前计数器值 (内存缓存,每次 session 重置)。"""
    return _counter_cache.get(task_id, 0)


def increment_counter(task_id: str) -> int:
    """计数器 +1 (供 CounterIncrement custom action 调用)。"""
    _counter_cache[task_id] = _counter_cache.get(task_id, 0) + 1
    return _counter_cache[task_id]
