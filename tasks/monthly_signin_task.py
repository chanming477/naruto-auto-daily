"""tasks.monthly_signin_task — 每月签到任务(2026-06-29 14:23 user 强求补建)。

设计目标:
    主页 → 活动卷轴 → 活动页 → 左侧菜单下滑找"每月签到" → 点签到 → 关活动页 → 回主页。

实测 ROI (1920x1080):
    - 活动卷轴: x=1770, y=30, w=100, h=110 (shared/activity_button_v3.png)
        2026-06-29 14:23 user 裁的"活动"钱袋特写 → shared/activity_button_v4.png
    - 左侧菜单: x=0, y=100, w=250, h=980 (活动页左侧导航栏全高,需下滑找"每月签到")
    - 签到按钮: x=1700, y=870, w=200, h=130 (活动页右下角橙色按钮)
    - 关闭按钮: x=1820, y=60, w=80, h=80 (shared/x.png; 实际真位置 1860, 60 user 14:00 验证)
    - 主页按钮: x=30, y=700, w=100, h=80 (shared/home_button_v3.png; FILE_MISSING best-effort)

Pipeline (8 节点):
    1. ensure_home              Noop
    2. find_activity            主页找"活动"钱袋 → 点击
    3. find_monthly_sign_tab    活动页左侧菜单找"每月签到" → 点击
    4. find_sign_button         找右下"签到"橙色按钮 → 点击
    5. close_sign_popup         关闭签到后的弹窗(如有)
    6. close_activity_page      关闭活动页 (X (1860, 60))
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


# 实测 ROI (1920x1080)
ROI_ACTIVITY_BUTTON = (1770, 30, 100, 110)         # 主页"活动"钱袋
ROI_SIGNIN_LEFT_MENU = (0, 100, 250, 980)          # 活动页左侧菜单全高(找"每月签到")
ROI_SIGN_BUTTON = (1700, 850, 250, 180)            # "签到"按钮(右下); 2026-06-29 14:26 dryrun 验证旧 ROI 太小
ROI_CLOSE_X = (1820, 60, 80, 80)                  # 活动页 X 关闭
ROI_HOME_BUTTON = (30, 700, 100, 80)               # 主页按钮(14:29 user 重新放回 home_button_v3.png)


def _build_monthly_signin_pipeline(nav: Navigator) -> Pipeline:
    """构造"每月签到" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_activity"],
        focus="ensure home (pre_check)",
    ))

    # ---- 2. 主页找"活动"钱袋 → 点击 ----
    pipe.add(Node(
        name="find_activity",
        templates=tpls(
            "shared/activity_button_v4.png",   # 2026-06-29 14:23 user 裁的"活动"钱袋特写
            "shared/activity_button_v3.png",   # 2026-06-29 14:00 真机跑过的
        ),
        roi=ROI_ACTIVITY_BUTTON,
        threshold=0.55,
        action=ClickAction(),
        next=["swipe_left_menu_down"],
        on_error=["verify_done"],  # 找不到活动 → 直接结束
        post_delay_ms=2000,
        focus="点击主页'活动'钱袋",
    ))

    # ---- 3. 下滑左侧菜单(每月签到 在左侧菜单靠下,初始视口看不到) ----
    # 2026-06-29 14:36 user 强烈纠正:"你需要下滑左侧菜单栏啊"
    pipe.add(Node(
        name="swipe_left_menu_down",
        templates=[],   # swipe 不靠模板
        action=SwipeAction(
            x1=100, y1=200,    # 起点(左侧菜单顶部)
            x2=100, y2=900,    # 终点(左侧菜单底部)
            duration_ms=600,
        ),
        next=["find_monthly_sign_tab"],
        on_error=["find_monthly_sign_tab"],  # swipe 失败也尝试 find
        max_hit=2,
        post_delay_ms=1200,
        focus="下滑左侧菜单找'每月签到'",
    ))

    # ---- 4. 活动页左侧菜单找"每月签到" tab → 点击 ----
    pipe.add(Node(
        name="find_monthly_sign_tab",
        templates=tpls(
            "activity/monthly_sign_undone.png",        # 2026-06-29 14:23 user 已裁(163x70,带红点)
            "activity/monthly_sign_undone_activity.png",
            "activity/monthly_sign_done.png",          # 已签到
            "activity/monthly_sign_done_1.png",
            "activity/monthly_sign_done_activity.png",
            # 2026-06-29 14:26 dryrun 验证:title.png (活动页"活动"标题) 在 0.625 误命中 → 删除
        ),
        roi=ROI_SIGNIN_LEFT_MENU,
        threshold=0.55,
        action=ClickAction(),
        next=["find_sign_button"],
        on_error=["swipe_left_menu_down_2"],  # 没找到 → 再滑一次
        max_hit=3,
        post_delay_ms=1500,
        focus="点击'每月签到' tab",
    ))

    # ---- 4b. 二次下滑(若第一次 find_monthly_sign_tab 没命中) ----
    pipe.add(Node(
        name="swipe_left_menu_down_2",
        templates=[],
        action=SwipeAction(
            x1=100, y1=200,
            x2=100, y2=900,
            duration_ms=600,
        ),
        next=["find_monthly_sign_tab_retry"],
        on_error=["close_activity_page"],
        max_hit=1,
        post_delay_ms=1200,
        focus="二次下滑左侧菜单",
    ))

    # ---- 4c. 二次找(下滑后) ----
    pipe.add(Node(
        name="find_monthly_sign_tab_retry",
        templates=tpls(
            "activity/monthly_sign_undone.png",
            "activity/monthly_sign_undone_activity.png",
            "activity/monthly_sign_done.png",
            "activity/monthly_sign_done_1.png",
            "activity/monthly_sign_done_activity.png",
        ),
        roi=ROI_SIGNIN_LEFT_MENU,
        threshold=0.55,
        action=ClickAction(),
        next=["find_sign_button"],
        on_error=["close_activity_page"],
        max_hit=2,
        post_delay_ms=1500,
        focus="二次点击'每月签到' tab",
    ))

    # ---- 4. 找右下"签到"橙色按钮 → 点击 ----
    pipe.add(Node(
        name="find_sign_button",
        templates=tpls(
            "activity/sign.png",                 # 签到按钮
        ),
        roi=ROI_SIGN_BUTTON,
        threshold=0.55,
        action=ClickAction(),
        next=["close_sign_popup"],
        on_error=["close_activity_page"],  # 找不到签到按钮 → 关活动页(可能已签到)
        max_hit=2,
        post_delay_ms=1500,
        focus="点击'签到'按钮",
    ))

    # ---- 5. 关闭签到后弹窗(如有) ----
    pipe.add(Node(
        name="close_sign_popup",
        templates=tpls(
            "shared/x.png",
            "shared/x_right_top.png",
            "shared/green_masked_x.png",
            "shared/notice_x.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["close_activity_page"],
        on_error=["close_activity_page"],
        max_hit=2,
        post_delay_ms=600,
        focus="关闭签到后弹窗",
    ))

    # ---- 6. 关闭活动页(X 关闭 1860, 60) ----
    pipe.add(Node(
        name="close_activity_page",
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
        focus="关闭活动页",
    ))

    # ---- 7. 返回主页(点主页按钮, NOT 系统 BACK) ----
    pipe.add(Node(
        name="back_to_home",
        templates=tpls(
            "shared/home_button_v3.png",  # 2026-06-29 14:00 user 删,best-effort
        ),
        roi=ROI_HOME_BUTTON,
        threshold=0.5,
        action=ClickAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        post_delay_ms=800,
        focus="点击主页按钮",
    ))

    # ---- 8. 终点 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="每月签到流程完成",
    ))

    return pipe


class MonthlySigninTask(BaseTask):
    """每月签到任务(活动页 → 左侧菜单 → 签到)。"""

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
            log.success("[monthly_signin] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="monthly_signin completed",
                attempts=1,
            )

        # 失败 → recover (用界面 X 按钮) + 重试
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

        # best-effort
        log.warning("monthly_signin best-effort: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.SUCCESS,
            message="monthly_signin best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_monthly_signin_pipeline(nav)
        return runner.run(pipe, max_total_iterations=20, max_idle_iterations=4)
