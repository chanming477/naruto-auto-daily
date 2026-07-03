"""tasks.give_energy_task — 赠送体力(2026-06-30 抄自新版 MaaAutoNaruto v1.3.35 merged.json)。

narutomobile give_energy.json 流程:
right_sendS_v3(右上角送S忍图标) → 进好友列表 → 给体力 → done → 回主页

Pipeline (8 节点):
    1. ensure_home                 Noop
    2. energy_entry                进送体力入口(主页右侧菜单)
    3. give_energy_account_friend                 找赠送体力任务卡 → 点击
    4. give_energy_in_account_friend               送体力给好友
    5. give_energy_verify                战斗中
    6. give_energy_done                  胜利 → 点击继续
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


def _build_give_energy_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["energy_entry"], focus="主页基线"))

    # 1. 送体力入口(主页右侧菜单)
    pipe.add(Node(
        name="energy_entry",
        templates=tpls("shared/right_sendS_v3.png"),
        roi=(1700, 396, 200, 100), threshold=0.8,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["give_energy_account_friend"], on_error=["back_main_screen"],
        max_hit=3, focus="点送体力图标",
    ))

    # 2. 找赠送体力任务卡
    pipe.add(Node(
        name="give_energy_account_friend",
        templates=tpls("Leaderboard/leaderboard_the_first.png"),
        roi=(143, 169, 197, 143), threshold=0.8,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["give_energy_in_account_friend"], on_error=["back_main_screen"],
        max_hit=3, focus="找赠送体力卡",
    ))

    # 3. 送体力给好友
    pipe.add(Node(
        name="give_energy_in_account_friend",
        templates=tpls("Leaderboard/leaderboard_the_first.png"),
        roi=(259, 83, 298, 439), threshold=0.8,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["give_energy_verify"], on_error=["back_main_screen"],
        max_hit=3, focus="送体力给好友",
    ))

    # 4. 战斗中检测
    pipe.add(Node(
        name="give_energy_verify",
        templates=tpls("Give_energy/give_energy_done_masked.png"),
        roi=(27, 181, 63, 61), threshold=0.8,
        action=NoopAction(),
        next=["give_energy_done"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=3000, focus="战斗中",
    ))

    # 5. 胜利点击继续
    pipe.add(Node(
        name="give_energy_done",
        templates=tpls("Give_energy/give_energy_done_masked.png"),
        roi=(27, 181, 63, 61), threshold=0.85,
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

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="赠送体力完成"))
    return pipe


class GiveEnergyTask(BaseTask):
    task_id = "give_energy"
    name = "赠送体力"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="give_energy done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="give_energy retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"give_energy failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_give_energy_pipeline(nav), max_total_iterations=60, max_idle_iterations=10)


__all__ = ["GiveEnergyTask"]
