"""tasks.secret_realm_task — 秘境探险(2026-06-30 抄自 narutomobile Secret_realm.json)。

narutomobile 流程:secret_realm_ac_entry → secret_realm_create_room → secret_realm_fight →
secret_realm_in_fight → 自动战斗 → 关卡结算 → 翻牌 → 出秘境。

Pipeline (8 节点):
    1. ensure_home                  Noop
    2. award_center_enter           → 奖励中心
    3. secret_realm_ac_undone       → 找秘境任务卡 → 点击
    4. secret_realm_create_room     "创建房间"
    5. secret_realm_fight           "出战"
    6. secret_realm_in_fight        检测自动战斗中
    7. secret_realm_win             "胜利" → 点击继续
    8. back_main_screen             main_green_masked.png → 回主页
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


def _build_secret_realm_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["award_center_enter"], focus="主页基线"))

    pipe.add(Node(
        name="award_center_enter",
        templates=tpls("shared/award_center_entry.png"),
        roi=(1174, 302, 99, 105), threshold=0.7,
        action=ClickAction(x_offset=3, y_offset=-51),
        next=["check_in_center"], on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=1500, focus="进奖励中心",
    ))

    pipe.add(Node(
        name="check_in_center",
        templates=tpls("shared/check_in_daily_award.png"),
        roi=(37, 172, 130, 47), threshold=0.6, action=NoopAction(),
        next=["secret_realm_ac_undone"], on_error=["back_main_screen"],
        max_hit=5, focus="确认奖励中心",
    ))

    pipe.add(Node(
        name="secret_realm_ac_undone",
        templates=tpls("Secret_realm/secret_realm_ac_undone.png"),
        roi=(180, 288, 1100, 225), threshold=0.8, green_mask=True,
        action=ClickAction(x_offset=12, y_offset=116),
        next=["secret_realm_create_room"], on_error=["back_main_screen"],
        max_hit=3, focus="找秘境任务卡",
    ))

    pipe.add(Node(
        name="secret_realm_create_room",
        templates=tpls("Secret_realm/fight.png"),
        roi=(1136, 572, 104, 86), threshold=0.7, action=ClickAction(),
        next=["secret_realm_in_fight"], on_error=["back_main_screen"],
        max_hit=2, post_delay_ms=300, focus="出战/创建房间",
    ))

    pipe.add(Node(
        name="secret_realm_in_fight",
        templates=tpls("SharedNode/dameeji_ratio.png"),
        roi=(0, 224, 113, 122), threshold=0.7, action=NoopAction(),
        next=["secret_realm_win"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=5000, focus="战斗中",
    ))

    pipe.add(Node(
        name="secret_realm_win",
        templates=tpls("Secret_realm/back_to_main_page.png"),
        roi=(0, 473, 462, 246), threshold=0.8, action=ClickAction(),
        next=["secret_realm_in_fight"], on_error=["back_main_screen"],
        max_hit=3, focus="胜利 → 继续",
    ))

    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="秘境完成"))
    return pipe


class SecretRealmTask(BaseTask):
    task_id = "secret_realm"
    name = "秘境探险"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="secret_realm done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="secret_realm retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"secret_realm failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_secret_realm_pipeline(nav), max_total_iterations=80, max_idle_iterations=10)


__all__ = ["SecretRealmTask"]
