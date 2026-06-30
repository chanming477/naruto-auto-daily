"""tasks.weekly_signin_task — 每周签到任务(Phase 7 新增)。

设计目标:
    主页 → 点击"每周签到"按钮 → 确认签到 → 关闭弹窗 → 返回主页。

实测 ROI (1920x1080):
    - 每周签到按钮: x=510, y=540, w=250, h=110
        原模板 shared/weekly_sign.png(实为"領"字)/ weekly_sign_v3.png(实为"特劇"字)
        已移入 templates/deprecated/,2026-06-29 P0-1 步骤 4
        当前任务"每周签到"未确认有对应入口 — pipeline 会 best-effort 跳过
    - 关闭按钮: x=1820, y=60, w=80, h=80 (shared/x.png)
    - 主页按钮: x=30, y=700, w=100, h=80 (shared/home_button_v3.png)

Pipeline (6 节点):
    1. ensure_home              Noop
    2. find_weekly_sign         主页找每周签到 → 点击(无模板 → on_error → verify_done)
    3. confirm_weekly_sign      处理签到确认 (可能在弹窗内)
    4. close_popup              关闭弹窗 (NOT 系统 BACK)
    5. back_to_home             主页按钮
    6. verify_done              终点

重要: 永不调用 KeyAction(key="BACK")!

依赖: tasks.navigator, tasks.pipeline_runner
"""

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

__all__ = ["WeeklySigninTask"]


# 实测 ROI (1920x1080)
ROI_WEEKLY_SIGN = (510, 540, 250, 110)
ROI_CONFIRM_BTN = (860, 560, 200, 80)  # 弹窗中央确认
ROI_CLOSE_X = (1820, 60, 80, 80)
ROI_HOME_BUTTON = (30, 700, 100, 80)


def _build_weekly_signin_pipeline(nav: Navigator) -> Pipeline:
    """构造"每周签到" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_weekly_sign"],
        focus="ensure home (pre_check)",
    ))

    # ---- 2. 主页找"每周签到"按钮 → 点击 ----
    # P0-1 2026-06-29: 原 weekly_sign.png/weekly_sign_v3.png 已被误裁为"特劇"/"領"字,
    # 移入 deprecated/。当前无有效模板,fallback chain 空 → best-effort 跳过。
    pipe.add(Node(
        name="find_weekly_sign",
        templates=tpls(
            # 待采集: 进活动页截真正的"每周签到"按钮
            # 参考 activity_task.py 的 monthly_sign_undone.png 模式
        ),
        roi=ROI_WEEKLY_SIGN,
        threshold=0.55,
        action=ClickAction(),
        next=["confirm_weekly_sign"],
        on_error=["verify_done"],
        post_delay_ms=1500,
        focus="点击每周签到按钮(待补采)",
    ))

    # ---- 3. 确认签到(若出现弹窗) ----
    pipe.add(Node(
        name="confirm_weekly_sign",
        templates=tpls(
            "shared/confrim.png",
            "shared/confrim_small.png",
            "shared/get.png",
        ),
        roi=ROI_CONFIRM_BTN,
        threshold=0.55,
        action=ClickAction(),
        next=["close_popup"],
        on_error=["close_popup"],
        max_hit=2,
        post_delay_ms=800,
        focus="确认签到",
    ))

    # ---- 4. 关闭弹窗 ----
    pipe.add(Node(
        name="close_popup",
        templates=tpls(
            "shared/x.png",
            "shared/x_right_top.png",
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
        focus="关闭签到弹窗",
    ))

    # ---- 5. 返回主页 ----
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

    # ---- 6. 终点 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="每周签到流程完成",
    ))

    return pipe


class WeeklySigninTask(BaseTask):
    """每周签到任务。"""

    task_id = "weekly_signin"
    name = "每周签到"
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
            log.success("[weekly_signin] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="weekly_signin completed",
                attempts=1,
            )

        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[weekly_signin] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="weekly_signin completed (after retry)",
                attempts=2,
            )

        log.warning("weekly_signin best-effort: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.SUCCESS,
            message="weekly_signin best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_weekly_signin_pipeline(nav)
        return runner.run(pipe, max_total_iterations=20, max_idle_iterations=4)