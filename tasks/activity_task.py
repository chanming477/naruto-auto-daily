"""tasks.activity_task — 活动任务(一乐外卖/体力追回) (Phase 7 新增)。

设计目标:
    主页 → 进入"活动"页 → 找一乐外卖 → 领体力追回 → 返回主页。

实测 ROI (1920x1080):
    - 活动按钮 (右上): x=1770, y=30, w=100, h=110 (shared/activity_button_v3.png)
    - 关闭按钮: x=1820, y=60, w=80, h=80 (shared/x.png)
    - 主页按钮: x=30, y=700, w=100, h=80 (shared/home_button_v3.png)

Pipeline (6 节点):
    1. ensure_home              Noop
    2. find_activity            主页找活动按钮 → 点击
    3. find_ramen_or_award      活动页找一乐外卖或体力追回 → 点击
    4. close_popup              关闭弹窗
    5. back_to_home             主页按钮
    6. verify_done              终点

重要: 永不调用 KeyAction(key="BACK")!
"""

# === Task 元数据 (2026-06-30 工程治理) ===
# 来源    : MaaAutoNaruto-win-x86_64-v1.3.35 (v1.3.35 merged.json)
# 生成器  : tools/gen_11_tasks.py (统一模板,不得手改)
# 维护    : 修改 ROI/流程请改 gen_11_tasks.py 重生成
# === End 元数据 ===

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from core.base_task import BaseTask, TaskResult, TaskStatus
from state.game_state import GameState
from tasks.navigator import (
    ClickAction,
    Navigator,
    Node,
    NoopAction,
    Pipeline,
)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
    PipelineRunner,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext

__all__ = ["ActivityTask"]


ROI_ACTIVITY_BUTTON = (1770, 30, 100, 110)
ROI_RAMEN_AREA = (190, 108, 1077, 395)        # narutomobile 原始
ROI_BOXES_AREA = (0, 100, 1920, 800)
ROI_CLOSE_X = (1820, 60, 80, 80)
ROI_HOME_BUTTON = (30, 700, 100, 80)


def _build_activity_pipeline(nav: Navigator) -> Pipeline:
    """构造"活动(一乐外卖)" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_activity"],
        focus="ensure home (pre_check)",
    ))

    pipe.add(Node(
        name="find_activity",
        templates=tpls(
            "shared/activity_button_v3.png",
            "shared/recruit_button_v3.png",  # 活动按钮和招募相邻,有时共用
        ),
        roi=ROI_ACTIVITY_BUTTON,
        threshold=0.55,
        action=ClickAction(),
        next=["find_ramen"],
        on_error=["verify_done"],
        post_delay_ms=2000,
        focus="点击主页活动按钮",
    ))

    pipe.add(Node(
        name="find_ramen",
        templates=tpls(
            "activity/ramen.png",
            "activity/headhunt.png",
        ),
        roi=ROI_RAMEN_AREA,
        threshold=0.55,
        action=ClickAction(),
        next=["claim_award"],
        on_error=["close_popup"],
        max_hit=3,
        post_delay_ms=1500,
        focus="在一乐外卖区域点击领取",
    ))

    pipe.add(Node(
        name="claim_award",
        templates=tpls(
            "shared/get.png",
            "shared/confrim.png",
            "shared/confrim_small.png",
        ),
        roi=ROI_BOXES_AREA,
        threshold=0.55,
        action=ClickAction(),
        next=["close_popup"],
        on_error=["close_popup"],
        max_hit=3,
        post_delay_ms=800,
        focus="点击领取/确认按钮",
    ))

    pipe.add(Node(
        name="close_popup",
        templates=tpls(
            "shared/x.png",
            "shared/green_masked_x.png",
            "shared/notice_x.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["back_to_home"],
        on_error=["back_to_home"],
        max_hit=2,
        post_delay_ms=500,
        focus="关闭活动弹窗",
    ))

    pipe.add(Node(
        name="back_to_home",
        templates=tpls(
            "shared/home_button_v3.png",
        ),
        roi=ROI_HOME_BUTTON,
        threshold=0.5,
        action=ClickAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        post_delay_ms=800,
        focus="点击主页按钮",
    ))

    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="活动流程完成",
    ))

    return pipe


class ActivityTask(BaseTask):
    """活动任务(一乐外卖/体力追回)。"""

    task_id = "activity"
    name = "活动(一乐外卖)"
    category = "weekly"
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        # P0-FIX-2026-06-29: 不用 ensure_state(HOME) - 会调 go_home() 按 BACK,
        # 触发"是否退出游戏"弹窗。让 pipeline 自己从任意状态起步。
        return ctx.common_actions is not None

    def post_check(self, ctx, result):
        # 不强制回 HOME - pipeline 内部已用 X + 主页按钮 recover
        return

    def cleanup(self, ctx, result):
        pass

    def enter(self, ctx: "ExecutionContext") -> bool:
        return True

    def verify(self, ctx: "ExecutionContext") -> bool:
        return True

    def recover(self, ctx: "ExecutionContext") -> bool:
        """恢复:用界面内关闭按钮 + 主页按钮(NOT 系统 BACK)。

        严格禁止 KeyAction(key="BACK") — 会触发"是否退出游戏"弹窗。
        v1.2 P1 #3: 委托给 tasks.common_actions.make_recovery_chain(double_x=False)。
        """
        if ctx.common_actions is None:
            return False
        return make_recovery_chain(
            ctx.common_actions,
            double_x=False,
            log=ctx.bind_logger(self.task_id),
        )

    def run(self, ctx: "ExecutionContext") -> TaskResult:
        log = ctx.bind_logger(self.task_id)

        if ctx.common_actions is None:
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.FAIL,
                message="ctx.common_actions is None",
                attempts=0,
            )

        adb = ctx.common_actions.adb
        project_root = Path(ctx.config.project_root)
        templates_root = project_root / "resources" / "templates" / "actions"

        result = self._run_pipeline(adb, project_root, templates_root, log)
        if result.success:
            log.success("[activity] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="activity completed",
                attempts=1,
            )

        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[activity] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="activity completed (after retry)",
                attempts=2,
            )

        log.warning("activity best-effort: {}", result2.error)
        # P0 修复(2026-07-02): 用 BEST_EFFORT 而非 SUCCESS 避免掩盖故障
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.BEST_EFFORT,
            message="activity best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_activity_pipeline(nav)
        return runner.run(pipe, max_total_iterations=20, max_idle_iterations=4)