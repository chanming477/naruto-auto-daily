"""tasks.shugyou_no_michi_task — 修行之路(2026-06-30 抄自 narutomobile Practice_place_shugyou_no_michi.json)。

narutomobile 流程:go_into_shugyou_no_michi_by_guide → train_road_entry →
train_road_unsweep/trian_road_award → confirm_train_road_sweep/reset →
自动战斗 → win → 继续

Pipeline 8 节点:GoIntoEntryByGuide → train_road_unsweep → confirm → 重置 → 战斗 → win
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


def _build_shugyou_pipeline(nav: Navigator) -> Pipeline:
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
        next=["train_road_ac_undone"], on_error=["back_main_screen"],
        max_hit=5, focus="确认奖励中心",
    ))

    pipe.add(Node(
        name="train_road_ac_undone",
        templates=tpls("Practice_place/train_road_ac_undone.png"),
        roi=(180, 288, 1100, 225), threshold=0.85, green_mask=True,
        action=ClickAction(x_offset=12, y_offset=116),
        next=["train_road_entry"], on_error=["back_main_screen"],
        max_hit=3, focus="找修行之路任务卡",
    ))

    pipe.add(Node(
        name="train_road_entry",
        templates=tpls("Practice_place/train_road_unsweep.png"),
        roi=(807, 570, 155, 149), threshold=0.85, action=ClickAction(),
        next=["train_road_unsweep_confirm"], on_error=["train_road_award"],
        max_hit=2, focus="进入修行之路",
    ))

    pipe.add(Node(
        name="train_road_unsweep_confirm",
        templates=tpls("SharedNode/confrim.png"),
        roi=(532, 409, 205, 83), threshold=0.7, action=ClickAction(),
        next=["win_in_fight"], on_error=["back_main_screen"],
        max_hit=3, focus="确认扫荡",
    ))

    pipe.add(Node(
        name="train_road_award",
        templates=tpls("Practice_place/train_road_win.png"),
        roi=(404, 113, 491, 328), threshold=0.9, action=ClickAction(),
        next=["win_in_fight"], on_error=["back_main_screen"],
        max_hit=3, focus="领取修行之路奖励",
    ))

    pipe.add(Node(
        name="win_in_fight",
        templates=tpls("Practice_place/train_road_win.png"),
        roi=(404, 113, 491, 328), threshold=0.9, action=ClickAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=3, focus="战斗胜利",
    ))

    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="修行之路完成"))
    return pipe


class ShugyouNoMichiTask(BaseTask):
    task_id = "shugyou_no_michi"
    name = "修行之路"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="shugyou done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="shugyou retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"shugyou failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_shugyou_pipeline(nav), max_total_iterations=60, max_idle_iterations=10)


__all__ = ["ShugyouNoMichiTask"]
