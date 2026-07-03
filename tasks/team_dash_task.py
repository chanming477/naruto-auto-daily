"""tasks.team_dash_task — 小队突袭任务(2026-06-30 抄自 narutomobile Team_dash.json)。

narutomobile Team_dash.json 流程:
    team_dash_ac_entry  → team_dash_in_center_enter  → team_dash_ac_entry_undone
    → team_dash_group_help_undone  → team_dash_invite_page  → team_dash_invite_ninja
    → dash_or_exit  → team_dash_auto_fight  → team_dash_above_kage_sweep
    → close_team_dash  → close_team_dash_out_team_sign  → back_main_screen_and_stop

ROI 完全照抄:
    - 进奖励中心 + 任务卡:award_center_entry + team_dash_ac_undone
    - 邀请:invite button at (351, 150, 106, 486)
    - 自动战斗:auto_fight / auto_match at (1138, 572, 107, 107)
    - 超影扫荡:above_kage_sweep at (1074, 505, 204, 207)

Pipeline (10 节点):
    1. ensure_home                  Noop
    2. award_center_enter           award_center_entry.png → 进奖励中心
    3. team_dash_in_center_enter    check_in_daily_award.png → 验证
    4. team_dash_ac_entry_undone    team_dash_ac_undone.png → 找小队卡片 → 点击
    5. team_dash_group_help_undone  team_dash_group_help_undone.png → 进组织助战
    6. team_dash_invite_ninja       team_dash_invite.png → 邀请忍者
    7. team_dash_auto_fight         auto_fight.png / auto_match.png → 触发自动战斗
    8. team_dash_above_kage_sweep   above_kage_sweep.png → 超影扫荡
    9. close_team_dash              Team_dash/x.png → 关闭
    10. back_main_screen            main_green_masked.png → 回主页
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
    ClickAction, Navigator, Node, NoopAction, Pipeline, SwipeAction,
)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT, DEFAULT_REF_WIDTH, PipelineRunner,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext

__all__ = ["TeamDashTask"]


ROI_AWARD_CENTER_ENTRY = (1174, 302, 99, 105)
AWARD_TAP_X_OFFSET = 3
AWARD_TAP_Y_OFFSET = -51

ROI_CHECK_IN_CENTER = (37, 172, 130, 47)
ROI_TEAM_DASH_AC_UNDONE = (180, 288, 1100, 225)
TEAM_DASH_TAP_X_OFFSET = 12
TEAM_DASH_TAP_Y_OFFSET = 116

ROI_GROUP_HELP_UNDONE = (990, 602, 72, 64)        # 选组织助战
ROI_INVITE = (351, 150, 106, 486)                # 邀请忍者
ROI_AUTO_FIGHT = (1138, 572, 107, 107)           # 自动战斗 / 自动匹配
ROI_DO_NOT_REMIND = (548, 468, 45, 44)           # 本周不再提醒
ROI_ABOVE_KAGE_SWEEP = (1074, 505, 204, 207)     # 超影扫荡
ROI_TEAM_DASH_X = (1177, 0, 96, 85)              # 关闭小队突袭
ROI_DASH_LOGO = (44, 0, 474, 199)                # 小队 logo 检测
ROI_HOME_MAIN = (0, 0, 1920, 1080)


def _build_team_dash_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["award_center_enter"], focus="主页基线"))

    pipe.add(Node(
        name="award_center_enter",
        templates=tpls("shared/award_center_entry.png", "shared/award_button_v5_real.png"),
        roi=ROI_AWARD_CENTER_ENTRY, threshold=0.7,
        action=ClickAction(x_offset=AWARD_TAP_X_OFFSET, y_offset=AWARD_TAP_Y_OFFSET),
        next=["check_in_center"], on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=1500, focus="进奖励中心",
    ))

    pipe.add(Node(
        name="check_in_center",
        templates=tpls("shared/check_in_daily_award.png"),
        roi=ROI_CHECK_IN_CENTER, threshold=0.6, action=NoopAction(),
        next=["team_dash_ac_entry_undone"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=500, focus="确认在奖励中心",
    ))

    pipe.add(Node(
        name="team_dash_ac_entry_undone",
        templates=tpls("Team_dash/team_dash_ac_undone.png"),
        roi=ROI_TEAM_DASH_AC_UNDONE, threshold=0.8, green_mask=True,
        action=ClickAction(x_offset=TEAM_DASH_TAP_X_OFFSET, y_offset=TEAM_DASH_TAP_Y_OFFSET),
        next=["team_dash_group_help_undone"], on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=600, focus="找小队突袭任务卡",
    ))

    pipe.add(Node(
        name="team_dash_group_help_undone",
        templates=tpls("Team_dash/team_dash_group_help_undone.png"),
        roi=ROI_GROUP_HELP_UNDONE, threshold=0.7, action=ClickAction(),
        next=["team_dash_invite"], on_error=["team_dash_above_kage_sweep"],
        max_hit=2, post_delay_ms=400, focus="选组织助战",
    ))

    pipe.add(Node(
        name="team_dash_invite",
        templates=tpls("Team_dash/team_dash_invite.png"),
        roi=ROI_INVITE, threshold=0.7, action=ClickAction(),
        next=["team_dash_auto_fight"], on_error=["team_dash_above_kage_sweep"],
        max_hit=2, post_delay_ms=200, focus="邀请忍者",
    ))

    pipe.add(Node(
        name="team_dash_auto_fight",
        templates=tpls("Team_dash/auto_fight.png", "Team_dash/auto_match.png"),
        roi=ROI_AUTO_FIGHT, threshold=0.7, action=ClickAction(),
        next=["team_dash_do_not_remind"], on_error=["team_dash_above_kage_sweep"],
        max_hit=10, post_delay_ms=300, focus="自动战斗 / 自动匹配",
    ))

    pipe.add(Node(
        name="team_dash_do_not_remind",
        templates=tpls("Team_dash/do_not_remind_gold.png"),
        roi=ROI_DO_NOT_REMIND, threshold=0.6, action=ClickAction(),
        next=["team_dash_above_kage_sweep"], on_error=["team_dash_above_kage_sweep"],
        max_hit=2, post_delay_ms=200, focus="本周不再提醒",
    ))

    pipe.add(Node(
        name="team_dash_above_kage_sweep",
        templates=tpls("Team_dash/above_kage_sweep.png"),
        roi=ROI_ABOVE_KAGE_SWEEP, threshold=0.7,
        action=SwipeAction(x1=1176, y1=608, x2=1176, y2=608, duration_ms=50),
        next=["close_team_dash"], on_error=["close_team_dash"],
        max_hit=3, post_delay_ms=400, focus="超影扫荡",
    ))

    pipe.add(Node(
        name="close_team_dash",
        templates=tpls("Team_dash/x.png"),
        roi=ROI_TEAM_DASH_X, threshold=0.7, action=ClickAction(),
        next=["close_team_dash_sign"], on_error=["back_main_screen"],
        max_hit=2, post_delay_ms=1000, focus="关闭小队突袭",
    ))

    pipe.add(Node(
        name="close_team_dash_sign",
        templates=tpls("SharedNode/confrim_small.png"),
        roi=(535, 418, 205, 74), threshold=0.7, action=ClickAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=2, post_delay_ms=300, focus="确认退队",
    ))

    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=ROI_HOME_MAIN, threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, post_delay_ms=1000, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="小队突袭完成"))
    return pipe


class TeamDashTask(BaseTask):
    task_id = "team_dash"
    name = "小队突袭"
    category = "combat"
    max_retries: int = 0

    def pre_check(self, ctx): return bool(ctx.common_actions and ctx.common_actions.ensure_state(GameState.HOME))
    def post_check(self, ctx, result):
        if ctx.common_actions: ctx.common_actions.ensure_state(GameState.HOME)
    def cleanup(self, ctx, result): pass
    def enter(self, ctx): return True
    def verify(self, ctx): return True
    def recover(self, ctx):
        if not ctx.common_actions: return False
        return make_recovery_chain(ctx.common_actions, double_x=False, log=ctx.bind_logger(self.task_id))

    def run(self, ctx):
        log = ctx.bind_logger(self.task_id)
        if not ctx.common_actions:
            return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message="ctx.common_actions is None", attempts=0)
        adb = ctx.common_actions.adb
        project_root = Path(ctx.config.project_root)
        templates_root = project_root / "resources" / "templates" / "actions"
        r = self._run_pipeline(adb, project_root, templates_root, log)
        if r.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="team_dash completed", attempts=1)
        log.warning("first failed: {}", r.error)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="team_dash retry ok", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"team_dash failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        pipe = _build_team_dash_pipeline(nav)
        return runner.run(pipe, max_total_iterations=50, max_idle_iterations=8)
