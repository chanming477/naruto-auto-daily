"""tasks.monthly_signin_task — 每月签到任务(2026-06-29 14:23 user 强求补建)。

设计目标:
    主页 → 活动页(activity_button_v4.png,右上角"活动"钱袋)→ 下滑左侧菜单找"每月签到" → 点签到 → 回主页。

ROI 2026-07-01 修正:
    - 活动入口: activity_button_v4.png ROI (1760, 30, 160, 130), tap = ROI 中心 (1840, 95)。
      narutomobile 原文 ROI (1194, 132, 50, 42) + tap (1222, 54) 在当前主页 (1920x1080)
      对应的位置完全是天空背景,从没匹配过 — 旧版本 best-effort SUCCESS 掩盖。
      headhunt.png 名字误导(实际是招募按钮残留),已移至 deprecated/。
    - 下滑左侧菜单: begin (80, 600, 50, 50) → end (80, 300, 50, 50), duration 200, max_hit=10
    - 每月签到 tab: template monthly_sign_undone.png @ ROI (19, 130, 143, 572) → 扩到 (0, 100, 220, 700)
    - 签到按钮: sign.png @ ROI (1107, 547, 164, 61) 中心 (1189, 577)
    - 验证签到: monthly_sign_done.png @ ROI (1104, 532, 158, 98)

Pipeline (8 节点,严格按 narutomobile + 2026-07-01 ROI 修正):
    1. ensure_home                 Noop
    2. find_activity               activity_button_v4.png → 点 (1840, 95) 进活动页
    3. swipes_for_monthly_sign     下滑左侧菜单 max_hit=10(找每月签到 tab)
    4. find_monthly_sign_tab       template 匹配 → 点击
    5. find_sign_button            sign.png → 点签到
    6. verify_signed               monthly_sign_done.png → 已签到验证
    7. back_main_screen            main_green_masked.png → 验证回主页
    8. verify_done                 Noop

依赖: tasks.navigator, tasks.pipeline_runner
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
    SwipeAction,
)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
    PipelineRunner,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext

__all__ = ["MonthlySigninTask"]


# 活动入口 ROI(2026-07-01 修正):右上角"活动"钱袋
#   x: 1760-1920 (160), y: 30-160 (130)
#   中心 (1840, 95) — ClickAction 无 offset 直接用 ROI 中心
ROI_ACTIVITY_BUTTON = (1760, 30, 160, 130)

# 左侧菜单下滑 ROI(narutomobile begin/end)
SWIPE_BEGIN = (80, 600, 50, 50)
SWIPE_END = (80, 300, 50, 50)
SWIPE_DURATION_MS = 200

# 每月签到 tab ROI(2026-07-01 扩:y 下边界 700→800,因左侧菜单靠下)
ROI_MONTHLY_SIGN_TAB = (0, 100, 220, 800)

# 签到按钮 ROI(narutomobile 直接给)
ROI_SIGN_BTN = (1107, 547, 164, 61)                # 中心 (1189, 577)

# 验证签到 ROI(narutomobile OCR 1104,532,158,98)
ROI_SIGN_DONE = (1104, 532, 158, 98)                # 中心 (1183, 581)

# 回主页 ROI(main_green_masked 全屏匹配,绿通道)
ROI_HOME_MAIN = (0, 0, 1920, 1080)


def _build_monthly_signin_pipeline(nav: Navigator) -> Pipeline:
    """构造"每月签到" pipeline (narutomobile ROI)。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        action=NoopAction(),
        next=["find_activity"],
        focus="主页基线",
    ))

    # ---- 2. 找活动入口(activity_button_v4.png)→ tap = ROI 中心 (1840, 95) ----
    pipe.add(Node(
        name="find_activity",
        templates=tpls(
            "shared/activity_button_v4.png",       # "活动"钱袋 (主模板,2026-06-29 user 裁)
            "shared/activity_button_v3.png",       # 旧 DPI fallback
        ),
        roi=ROI_ACTIVITY_BUTTON,
        threshold=0.6,
        action=ClickAction(),                      # 2026-07-01 修正:无 offset,直接用 ROI 中心
        next=["swipes_for_monthly_sign"],
        on_error=["back_main_screen"],
        max_hit=3,
        post_delay_ms=2000,
        focus="点活动入口 (1840, 95)",
    ))

    # ---- 3. 下滑左侧菜单(max_hit=10 找每月签到 tab) ----
    pipe.add(Node(
        name="swipes_for_monthly_sign",
        templates=[],
        action=SwipeAction(
            x1=SWIPE_BEGIN[0], y1=SWIPE_BEGIN[1],
            x2=SWIPE_END[0], y2=SWIPE_END[1],
            duration_ms=SWIPE_DURATION_MS,
        ),
        next=["find_monthly_sign_tab"],
        on_error=["find_monthly_sign_tab"],
        max_hit=10,
        post_delay_ms=900,
        focus="下滑左侧菜单 (80,600)→(80,300)",
    ))

    # ---- 4. 找每月签到 tab(template match)-------
    pipe.add(Node(
        name="find_monthly_sign_tab",
        templates=tpls(
            "activity/monthly_sign_undone.png",            # 带红点未签
            "activity/monthly_sign_undone_activity.png",
            "activity/monthly_sign_done.png",              # 已签到
            "activity/monthly_sign_done_1.png",
            "activity/monthly_sign_done_activity.png",
        ),
        roi=ROI_MONTHLY_SIGN_TAB,
        threshold=0.6,
        action=ClickAction(),
        next=["find_sign_button"],
        on_error=["swipes_for_monthly_sign"],
        max_hit=3,
        post_delay_ms=1500,
        focus="找'每月签到' tab 并点",
    ))

    # ---- 5. 找签到按钮(sign.png @ narutomobile ROI)----
    pipe.add(Node(
        name="find_sign_button",
        templates=tpls(
            "activity/sign.png",
        ),
        roi=ROI_SIGN_BTN,
        threshold=0.6,
        action=ClickAction(),
        next=["verify_signed"],
        on_error=["back_main_screen"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点签到按钮 (1189, 577)",
    ))

    # ---- 6. 验证签到完成(monthly_sign_done.png @ 签到按钮附近)----
    pipe.add(Node(
        name="verify_signed",
        templates=tpls(
            "activity/monthly_sign_done.png",              # 已签到 = 带"已签到"标记
            "activity/monthly_sign_done_1.png",
            "activity/monthly_sign_done_activity.png",
        ),
        roi=ROI_SIGN_DONE,
        threshold=0.6,
        action=NoopAction(),
        next=["back_main_screen"],
        on_error=["back_main_screen"],
        max_hit=2,
        post_delay_ms=1500,
        focus="验证签到完成",
    ))

    # ---- 7. 回主页(main_green_masked.png)----
    pipe.add(Node(
        name="back_main_screen",
        templates=tpls(
            "state/main_green_masked.png",
        ),
        roi=ROI_HOME_MAIN,
        threshold=0.7,
        green_mask=True,
        action=NoopAction(),
        next=["verify_done"],
        on_error=["verify_done"],                       # narutomobile: 找不到也停
        max_hit=5,
        post_delay_ms=1000,
        focus="回主页验证",
    ))

    # ---- 8. 终点 ----
    pipe.add(Node(
        name="verify_done",
        action=NoopAction(),
        next=[],
        focus="每月签到流程完成",
    ))

    return pipe


class MonthlySigninTask(BaseTask):
    """每月签到任务(活动页 → 左侧菜单下滑 → 签到)。"""

    task_id = "monthly_signin"
    name = "每月签到"
    category = "monthly"
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        log = ctx.bind_logger(self.task_id)
        if ctx.common_actions is None:
            return False
        return bool(ctx.common_actions.ensure_state(GameState.HOME))

    def post_check(self, ctx: "ExecutionContext", result: TaskResult) -> None:
        log = ctx.bind_logger(self.task_id)
        if ctx.common_actions is not None:
            ctx.common_actions.ensure_state(GameState.HOME)

    def cleanup(self, ctx: "ExecutionContext", result: TaskResult) -> None:
        pass

    def enter(self, ctx: "ExecutionContext") -> bool:
        return True

    def verify(self, ctx: "ExecutionContext") -> bool:
        return True

    def recover(self, ctx: "ExecutionContext") -> bool:
        """恢复:用界面内关闭按钮 + 主页按钮(NOT 系统 BACK)。"""
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
            log.success("[monthly_signin] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="monthly_signin completed",
                attempts=1,
            )

        # 失败 → recover + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[monthly_signin] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="monthly_signin completed (after retry)",
                attempts=2,
            )

        # 真失败(2026-06-30:不再 best-effort SUCCESS 掩盖)
        log.error("monthly_signin 真失败: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.FAIL,
            message="monthly_signin failed: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_monthly_signin_pipeline(nav)
        return runner.run(pipe, max_total_iterations=40, max_idle_iterations=8)
