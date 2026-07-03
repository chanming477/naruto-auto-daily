"""tasks.ninja_book_task — 忍者书(2026-06-30 抄自新版 MaaAutoNaruto v1.3.35 merged.json)。

narutomobile ninja_book.json 流程:
进忍者书 → 选左 tab (award_undone) → 领 9 类奖励 → 完成 → 回主页

Pipeline (8 节点):
    1. ensure_home                 Noop
    2. hit_to_enter_ninja_book                进进忍者书
    3. check_no_ninja_book_award_red_point                 找忍者书任务卡 → 点击
    4. get_ninja_book_award               领取忍者书奖励
    5. confirm_ninja_book_award                战斗中
    6. ninja_book_done                  胜利 → 点击继续
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


def _build_ninja_book_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["hit_to_enter_ninja_book"], focus="主页基线"))

    # 1. 进忍者书
    pipe.add(Node(
        name="hit_to_enter_ninja_book",
        templates=tpls("Ninja_book/has_award.png"),
        roi=(89, 98, 111, 108), threshold=0.85,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["check_no_ninja_book_award_red_point"], on_error=["back_main_screen"],
        max_hit=3, focus="进忍者书",
    ))

    # 2. 找忍者书任务卡
    pipe.add(Node(
        name="check_no_ninja_book_award_red_point",
        templates=tpls("Ninja_book/ninja_book_award_undone_v2.png"),
        roi=(116, 108, 56, 79), threshold=0.85,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["get_ninja_book_award"], on_error=["back_main_screen"],
        max_hit=3, focus="找忍者书卡",
    ))

    # 3. 领取忍者书奖励
    pipe.add(Node(
        name="get_ninja_book_award",
        templates=tpls("Ninja_book/copper_60_waiting.png", "Ninja_book/fame_waiting.png", "Ninja_book/gold_waiting.png"),
        roi=(98, 490, 1131, 148), threshold=0.85,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["confirm_ninja_book_award"], on_error=["back_main_screen"],
        max_hit=3, focus="领取忍者书奖励",
    ))

    # 4. 战斗中检测
    pipe.add(Node(
        name="confirm_ninja_book_award",
        templates=tpls("Ninja_book/get_award.png"),
        roi=(493, 562, 261, 143), threshold=0.85,
        action=NoopAction(),
        next=["ninja_book_done"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=3000, focus="战斗中",
    ))

    # 5. 胜利点击继续
    pipe.add(Node(
        name="ninja_book_done",
        templates=tpls("Ninja_book/ninja_book_done_masked.png"),
        roi=(1204, 412, 53, 39), threshold=0.85,
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

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="忍者书完成"))
    return pipe


class NinjaBookTask(BaseTask):
    task_id = "ninja_book"
    name = "忍者书"
    category = "daily"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="ninja_book done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="ninja_book retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"ninja_book failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_ninja_book_pipeline(nav), max_total_iterations=60, max_idle_iterations=10)


__all__ = ["NinjaBookTask"]
