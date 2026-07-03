"""tasks.point_race_task — 积分赛(2026-06-30 抄自新版 MaaAutoNaruto v1.3.35 merged.json)。

narutomobile point_race.json 流程:
award_center_enter → point_race_ac_undone(任务卡) → challenge_rhombus 挑战 → 自动战斗 → challenge_finished → 回主页

Pipeline (8 节点):
    1. ensure_home                 Noop
    2. award_center_enter                进奖励中心入口(积分赛通过 ninja_guide)
    3. point_race_ac_entry_undone                 找积分赛任务卡 → 点击
    4. point_race_challenge               挑战积分赛
    5. point_race_in_fight                战斗中
    6. point_race_challenge_finished                  胜利 → 点击继续
    7. back_main_screen            main_green_masked.png → 回主页
    8. verify_done                 Noop
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


def _build_point_race_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["award_center_enter"], focus="主页基线"))

    # 1. 奖励中心入口(积分赛通过 ninja_guide)
    pipe.add(Node(
        name="award_center_enter",
        templates=tpls("shared/award_center_entry.png", "shared/award_button_v5_real.png"),
        roi=(1174, 302, 99, 105), threshold=0.7,
        action=ClickAction(x_offset=3, y_offset=-51),
        next=["point_race_ac_entry_undone"], on_error=["back_main_screen"],
        max_hit=3, focus="点奖励中心",
    ))

    # 2. 找积分赛任务卡
    pipe.add(Node(
        name="point_race_ac_entry_undone",
        templates=tpls("Point_race/point_race_ac_undone.png"),
        roi=(180, 288, 1100, 225), threshold=0.8,
        green_mask=True,
        action=ClickAction(x_offset=12, y_offset=116),
        next=["point_race_challenge"], on_error=["back_main_screen"],
        max_hit=3, focus="找积分赛卡",
    ))

    # 3. 挑战积分赛
    pipe.add(Node(
        name="point_race_challenge",
        templates=tpls("SharedNode/challenge_rhombus.png"),
        roi=(1084, 380, 195, 229), threshold=0.85,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["point_race_in_fight"], on_error=["back_main_screen"],
        max_hit=3, focus="挑战积分赛",
    ))

    # 4. 战斗中检测
    pipe.add(Node(
        name="point_race_in_fight",
        templates=tpls("auto_battle/challenge.png"),
        roi=(560, 0, 156, 89), threshold=0.7,
        action=NoopAction(),
        next=["point_race_challenge_finished"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=3000, focus="战斗中",
    ))

    # 5. 胜利点击继续
    pipe.add(Node(
        name="point_race_challenge_finished",
        templates=tpls("SharedNode/win.png"),
        roi=(298, 469, 691, 251), threshold=0.8,
        action=ClickAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=3, focus="胜利 → 继续",
    ))

    # 6. 回主页
    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="积分赛完成"))
    return pipe


class PointRaceTask(BaseTask):
    task_id = "point_race"
    name = "积分赛"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="point_race done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="point_race retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"point_race failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_point_race_pipeline(nav), max_total_iterations=60, max_idle_iterations=10)


__all__ = ["PointRaceTask"]
