"""tasks.survival_challenge_task — 生存挑战(2026-06-30 抄自 narutomobile Practice_place_survival_challenge.json)。

narutomobile 流程:survival_challenge_ac_entry_undone → survival_challenge_above_kage 超影服务 →
confirm → survival_challenge_yesterday_award → survival_challenge_reset → survival_challenge_sweep
→ survival_challenge_sweep_ticket_confirm → wait_for_survival_challenge_sweep_complete → back_main_screen_and_stop

Pipeline 10 节点:简化版核心流程(进奖励中心 → 找卡片 → 重置 → 扫荡 → 回主页)
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
from tasks.navigator import (ClickAction, Navigator, Node, NoopAction, Pipeline, SwipeAction)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (DEFAULT_REF_HEIGHT, DEFAULT_REF_WIDTH, PipelineRunner)


def _build_survival_challenge_pipeline(nav: Navigator) -> Pipeline:
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
        next=["survival_challenge_ac_undone"], on_error=["back_main_screen"],
        max_hit=5, focus="确认奖励中心",
    ))

    pipe.add(Node(
        name="survival_challenge_ac_undone",
        templates=tpls("Practice_place/survival_challenge_ac_undone.png"),
        roi=(180, 288, 1100, 225), threshold=0.85, green_mask=True,
        action=ClickAction(x_offset=12, y_offset=116),
        next=["survival_challenge_reset"], on_error=["back_main_screen"],
        max_hit=3, focus="找生存挑战任务卡",
    ))

    pipe.add(Node(
        name="survival_challenge_reset",
        templates=tpls("Practice_place/survival_challenge_reset_undone.png"),
        roi=(560, 609, 51, 37), threshold=0.85, action=ClickAction(),
        next=["confirm_reset"], on_error=["start_sweep"],
        max_hit=2, focus="重置生存挑战",
    ))

    pipe.add(Node(
        name="confirm_reset",
        templates=tpls("Practice_place/confirm_survival_challenge_reset.png"),
        roi=(535, 415, 205, 74), threshold=0.7, action=ClickAction(),
        next=["start_sweep"], on_error=["start_sweep"],
        max_hit=2, focus="确认重置",
    ))

    pipe.add(Node(
        name="start_sweep",
        templates=tpls("Practice_place/survival_challenge_sweep.png"),
        roi=(706, 594, 129, 110), threshold=0.85, action=ClickAction(),
        next=["sweep_confirm"], on_error=["back_main_screen"],
        max_hit=10, focus="开始扫荡",
    ))

    pipe.add(Node(
        name="sweep_confirm",
        templates=tpls("SharedNode/confrim_small.png"),
        roi=(535, 415, 205, 74), threshold=0.7, action=ClickAction(),
        next=["sweep_wait"], on_error=["back_main_screen"],
        max_hit=2, focus="确认扫荡",
    ))

    pipe.add(Node(
        name="sweep_wait",
        templates=tpls("Practice_place/survival_no_ninja.png", "Practice_place/final_reward.png"),
        threshold=0.8, action=NoopAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=5000, focus="扫荡进行中",
    ))

    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="生存挑战完成"))
    return pipe


class SurvivalChallengeTask(BaseTask):
    task_id = "survival_challenge"
    name = "生存挑战"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="survival done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="survival retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"survival failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_survival_challenge_pipeline(nav), max_total_iterations=80, max_idle_iterations=10)


__all__ = ["SurvivalChallengeTask"]
