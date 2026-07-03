"""tasks.stronghold_task — 要塞(2026-06-30 抄自 narutomobile Stronghold.json)。

narutomobile Stronghold.json 流程(组织玩法 → 切到要塞 tab → 选火要塞 → 进入战斗 → 战斗 → 自动战斗 → 出要塞)

Pipeline 8 节点:简化版核心流程
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


def _build_stronghold_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["award_center_enter"], focus="主页基线"))

    # 1. 进奖励中心 → 找要塞任务卡
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
        next=["stronghold_entry"], on_error=["back_main_screen"],
        max_hit=5, focus="确认奖励中心",
    ))

    # 2. 强要塞入口(narutomobile stronghold_entry 用 GoIntoEntryByGuide 跳到"组织")
    pipe.add(Node(
        name="stronghold_entry",
        templates=tpls("Group/group_gameplay_undone.png"),
        roi=(44, 382, 177, 118), threshold=0.7,
        action=ClickAction(x_offset=12, y_offset=116),
        next=["stronghold_mode"], on_error=["back_main_screen"],
        max_hit=3, focus="进组织玩法 → 要塞入口",
    ))

    # 3. 选中要塞 icon → 进入火要塞
    pipe.add(Node(
        name="stronghold_mode",
        templates=tpls("Stronghold/stronghold_icon.png"),
        roi=(190, 150, 913, 224), threshold=0.85, action=ClickAction(),
        next=["stronghold_in_map"], on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=500, focus="选中要塞 icon",
    ))

    pipe.add(Node(
        name="stronghold_in_map",
        templates=tpls("Stronghold/map.png"),
        roi=(427, 0, 419, 123), threshold=0.8, action=NoopAction(),
        next=["fire_stronghold"], on_error=["back_main_screen"],
        max_hit=3, focus="在要塞地图",
    ))

    pipe.add(Node(
        name="fire_stronghold",
        templates=tpls("Stronghold/fire_stronghold.png"),
        roi=(432, 108, 560, 424), threshold=0.85, action=ClickAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=2, post_delay_ms=1000, focus="点击火要塞",
    ))

    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="要塞完成"))
    return pipe


class StrongholdTask(BaseTask):
    task_id = "stronghold"
    name = "要塞"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="stronghold done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="stronghold retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"stronghold failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_stronghold_pipeline(nav), max_total_iterations=80, max_idle_iterations=10)


__all__ = ["StrongholdTask"]
