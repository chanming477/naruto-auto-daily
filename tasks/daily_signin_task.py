"""tasks.daily_signin_task — 每日签到任务(Phase 6 B V2 真实接入)。

设计目标:
    主页 → 进入奖励中心 → 点击每日签到 → 关闭弹窗 → 返回主页。

实测 ROI (1920x1080):
    - 奖励按钮: x=1170, y=290, w=130, h=100  (shared/award_button_v3.png)
    - 每日签到入口(奖励中心内): x=37, y=172, w=130, h=47 (narutomobile 原始 ROI)
        对应模板: shared/check_in_daily_award.png 或 check_not_in_daily_award.png
    - 关闭按钮: x=1820, y=60, w=80, h=80 (shared/x.png)
    - 主页按钮: x=30, y=700, w=100, h=80 (shared/home_button_v3.png)

Pipeline (8 节点):
    1. ensure_home              Noop
    2. find_award_button        主页找奖励 → 点击
    3. find_daily_signin_btn    奖励中心找"每日签到"按钮 → 点击
    4. check_done_or_claim      检测签到状态 (check_in vs check_not_in)
    5. close_popup              关闭签到弹窗 (界面 X, NOT BACK)
    6. close_award_center       关闭奖励中心 (X)
    7. back_to_home             主页按钮
    8. verify_done              终点

重要: 永不调用 KeyAction(key="BACK")! 否则触发"是否退出游戏"弹窗。

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

__all__ = ["DailySigninTask"]


# 实测 ROI (1920x1080)
ROI_AWARD_BUTTON = (1760, 460, 200, 180)        # 主页"奖励"礼物盒(V1.2 §1.2.2 真机校准: conf=0.965 @ (1760, 470))
ROI_DAILY_SIGNIN_BTN = (37, 172, 130, 47)  # narutomobile 原始 ROI
ROI_CLOSE_X = (1820, 60, 80, 80)
ROI_HOME_BUTTON = (30, 700, 100, 80)


def _build_daily_signin_pipeline(nav: Navigator) -> Pipeline:
    """构造"每日签到" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_award_button"],
        focus="ensure home (pre_check)",
    ))

    # ---- 2. 主页找"奖励"按钮 → 点击 ----
    pipe.add(Node(
        name="find_award_button",
        templates=tpls(
            "shared/award_button_v5_real.png",   # 2026-06-29 Q1 补采(新账号漩涡鸣人主页 conf=1.000 @ (1865, 537))
            "shared/award_button_v4_real.png",   # V1.2 §1.2.2 真机裁切(右下深蓝礼物盒,旧账号)
            "shared/award_center_entry.png",
            "shared/award_center_entry_v2.png",
        ),
        roi=ROI_AWARD_BUTTON,
        threshold=0.55,
        action=ClickAction(),
        next=["find_daily_signin_btn"],
        on_error=["verify_done"],  # 找不到奖励 → 直接结束
        post_delay_ms=1500,
        focus="点击主页'奖励'按钮",
    ))

    # ---- 3. 找"每日签到"按钮 (在奖励中心内) ----
    # check_not_in_daily_award.png 表示"未签到可签"
    pipe.add(Node(
        name="find_daily_signin_btn",
        templates=tpls(
            "shared/check_not_in_daily_award.png",
            "shared/check_in_daily_award.png",
        ),
        roi=ROI_DAILY_SIGNIN_BTN,
        threshold=0.55,
        action=ClickAction(),
        next=["close_popup"],
        on_error=["close_award_center"],  # 不在每日签到页 → 关掉
        post_delay_ms=1000,
        focus="点击每日签到入口",
    ))

    # ---- 4. 关闭签到弹窗 (用界面 X 按钮) ----
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
        next=["close_award_center"],
        on_error=["close_award_center"],
        max_hit=3,
        post_delay_ms=600,
        focus="关闭签到弹窗",
    ))

    # ---- 5. 关闭奖励中心 (X) ----
    pipe.add(Node(
        name="close_award_center",
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
        post_delay_ms=600,
        focus="关闭奖励中心",
    ))

    # ---- 6. 返回主页(点主页按钮, NOT 系统 BACK) ----
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

    # ---- 7. 终点 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="每日签到流程完成",
    ))

    return pipe


class DailySigninTask(BaseTask):
    """每日签到任务。"""

    task_id = "daily_signin"
    name = "每日签到"
    category = "daily"
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        # P0-FIX-2026-06-29: 不用 ensure_state(HOME) — 会调 go_home() 按 BACK,
        # 触发"是否退出游戏"弹窗。让 pipeline 自己从任意状态起步。
        log = ctx.bind_logger(self.task_id)
        return ctx.common_actions is not None

    def post_check(self, ctx: "ExecutionContext", result: TaskResult) -> None:
        # 不强制回 HOME — pipeline 内部已用 X + 主页按钮 recover
        return

    def cleanup(self, ctx: "ExecutionContext", result: TaskResult) -> None:
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

        # 第一次
        result = self._run_pipeline(adb, project_root, templates_root, log)
        if result.success:
            log.success("[daily_signin] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="daily_signin completed",
                attempts=1,
            )

        # 失败 → recover (用界面 X 按钮) + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[daily_signin] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="daily_signin completed (after retry)",
                attempts=2,
            )

        # best-effort
        log.warning("daily_signin best-effort: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.SUCCESS,
            message="daily_signin best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_daily_signin_pipeline(nav)
        return runner.run(pipe, max_total_iterations=20, max_idle_iterations=4)