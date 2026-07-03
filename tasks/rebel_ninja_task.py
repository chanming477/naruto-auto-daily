"""tasks.rebel_ninja_task — 叛忍(2026-06-30 抄自新版 MaaAutoNaruto v1.3.35 merged.json)。

narutomobile rebel_ninja.json 流程:
ninja_guide → rebel_ninja_entry(切到叛忍 tab) → gameplay → 自动战斗 → finish → 回主页

Pipeline (8 节点):
    1. ensure_home                 Noop
    2. ninja_guide_entry                进忍界指引卷轴(主页右下)
    3. rebel_ninja_group_to_rebel_ninja                 找叛忍任务卡 → 点击
    4. rebel_ninja_go_fight               出战
    5. rebel_ninja_in_fight                战斗中
    6. rebel_ninja_finish                  胜利 → 点击继续
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


def _build_rebel_ninja_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["ninja_guide_entry"], focus="主页基线"))

    # 1. 忍界指引卷轴(主页右下)
    pipe.add(Node(
        name="ninja_guide_entry",
        templates=tpls("shared/guide.png"),
        roi=(934, 597, 178, 123), threshold=0.8,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["rebel_ninja_group_to_rebel_ninja"], on_error=["back_main_screen"],
        max_hit=3, focus="点忍界指引",
    ))

    # 2. 找叛忍任务卡
    pipe.add(Node(
        name="rebel_ninja_group_to_rebel_ninja",
        templates=tpls("Rebel_ninja/entry.png"),
        roi=(503, 155, 276, 291), threshold=0.85,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["rebel_ninja_go_fight"], on_error=["back_main_screen"],
        max_hit=3, focus="找叛忍卡",
    ))

    # 3. 出战
    pipe.add(Node(
        name="rebel_ninja_go_fight",
        templates=tpls("Sky_ground/gameplay.png"),
        roi=(44, 382, 177, 118), threshold=0.85,
        action=ClickAction(x_offset=0, y_offset=0),
        next=["rebel_ninja_in_fight"], on_error=["back_main_screen"],
        max_hit=3, focus="出战",
    ))

    # 4. 战斗中检测
    pipe.add(Node(
        name="rebel_ninja_in_fight",
        templates=tpls("auto_battle/challenge.png"),
        roi=(560, 0, 156, 89), threshold=0.7,
        action=NoopAction(),
        next=["rebel_ninja_finish"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=3000, focus="战斗中",
    ))

    # 5. 胜利点击继续
    pipe.add(Node(
        name="rebel_ninja_finish",
        templates=tpls("Rebel_ninja/entry.png"),
        roi=(503, 155, 276, 291), threshold=0.85,
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

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="叛忍完成"))
    return pipe


class RebelNinjaTask(BaseTask):
    task_id = "rebel_ninja"
    name = "叛忍"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="rebel_ninja done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="rebel_ninja retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"rebel_ninja failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_rebel_ninja_pipeline(nav), max_total_iterations=60, max_idle_iterations=10)


__all__ = ["RebelNinjaTask"]
