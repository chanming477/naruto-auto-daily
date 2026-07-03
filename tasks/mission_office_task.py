"""tasks.mission_office_task — 任务集会所(2026-06-30 抄自 narutomobile Mission_office.json)。

narutomobile Mission_office.json 流程:mission_office_ac_entry_undone → check_in_mission_office →
接任务(单人/3人/羁绊) → 选忍者 → take_mission → 接任务成功 → back_main_screen
"""

# === Task 元数据 (2026-06-30 工程治理) ===
# 来源    : MaaAutoNaruto-win-x86_64-v1.3.35 (v1.3.35 merged.json)
# 生成器  : tools/gen_11_tasks.py (统一模板,不得手改)
# 维护    : 修改 ROI/流程请改 gen_11_tasks.py 重生成
# === End 元数据 ===

from __future__ import annotations
import time
from pathlib import Path

from core.base_task import BaseTask, TaskResult, TaskStatus
from state.game_state import GameState
from tasks.navigator import (ClickAction, Navigator, Node, NoopAction, Pipeline)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (DEFAULT_REF_HEIGHT, DEFAULT_REF_WIDTH, PipelineRunner)


def _build_mission_office_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["award_center_enter"], focus="主页基线"))

    pipe.add(Node(
        name="award_center_enter",
        templates=tpls("shared/award_center_entry.png"),
        roi=(1174, 302, 99, 105), threshold=0.7,
        action=ClickAction(x_offset=3, y_offset=-51),
        next=["check_in_center"], on_error=["back_main_screen"],
        max_hit=3, focus="进奖励中心",
    ))

    pipe.add(Node(
        name="check_in_center",
        templates=tpls("shared/check_in_daily_award.png"),
        roi=(37, 172, 130, 47), threshold=0.6, action=NoopAction(),
        next=["mission_office_ac_undone"], on_error=["back_main_screen"],
        max_hit=5, focus="确认奖励中心",
    ))

    pipe.add(Node(
        name="mission_office_ac_undone",
        templates=tpls("Mission_office/misson_ac_undone.png"),
        roi=(180, 288, 1100, 225), threshold=0.85, green_mask=True,
        action=ClickAction(x_offset=12, y_offset=116),
        next=["select_ninja"], on_error=["back_main_screen"],
        max_hit=3, focus="找任务集会所",
    ))

    pipe.add(Node(
        name="select_ninja",
        templates=tpls("Mission_office/solo_mission_undone_masked.png",
                       "Mission_office/relation_mission_undone_masked.png",
                       "Mission_office/kage_mission_undone_masked.png"),
        roi=(517, 197, 724, 363), threshold=0.85, green_mask=True,
        action=ClickAction(),
        next=["ninja_frame"], on_error=["back_main_screen"],
        max_hit=3, focus="选任务",
    ))

    pipe.add(Node(
        name="ninja_frame",
        templates=tpls("Mission_office/ninja_frame_masked.png"),
        roi=(824, 94, 431, 414), threshold=0.7, green_mask=True,
        action=ClickAction(),
        next=["take_mission"], on_error=["take_mission"],
        max_hit=3, focus="选忍者",
    ))

    pipe.add(Node(
        name="take_mission",
        templates=tpls("Mission_office/take_mission.png"),
        roi=(1141, 582, 66, 46), threshold=0.8, action=ClickAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=2, post_delay_ms=500, focus="接取任务",
    ))

    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="任务集会所完成"))
    return pipe


class MissionOfficeTask(BaseTask):
    task_id = "mission_office"
    name = "任务集会所"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message="no common_actions", attempts=0)
        adb = ctx.common_actions.adb
        project_root = Path(ctx.config.project_root)
        templates_root = project_root / "resources" / "templates" / "actions"
        r = self._run_pipeline(adb, project_root, templates_root, log)
        if r.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="mission_office done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="mission_office retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"mission_office failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_mission_office_pipeline(nav), max_total_iterations=40, max_idle_iterations=8)


__all__ = ["MissionOfficeTask"]
