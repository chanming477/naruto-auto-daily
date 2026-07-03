"""tasks.rich_room_task — 丰饶之间任务(2026-06-30 抄自 narutomobile Rich_room.json)。

narutomobile Rich_room.json 流程:
    rich_room_ac_entry  → rich_room_in_center_enter  → rich_room_ac_entry_undone
    → rich_room_in_rich_room  → rich_room_above_kage  → rich_room_above_kage_sweep
    → rich_room_confirm_above_kage_sweep  → rich_room_without_confirm_above_kage_sweep
    → challenge_rich_room  → rich_room_in_fight  → rich_room_combo / rich_room_peace
    → back_main_screen_and_stop

ROI 完全照抄:
    - 奖励中心:award_center_entry.png ROI (1174, 302, 99, 105) → 点 (1222, 354)
    - 丰饶之间未完成卡片:rich_room_ac_undone.png ROI (180, 288, 1100, 225) green_mask target_offset (12, 116, -40, -114)
    - 超影扫荡:one_key.png ROI (632, 587, 224, 113)
    - 出战:fight.png ROI (447, 568, 171, 144)
    - 已重置/可扫荡检测:gold_coin.png / above_kage.png

Pipeline (8 节点):
    1. ensure_home                 Noop
    2. rich_room_ac_entry          award_center_entry.png → 进奖励中心
    3. rich_room_in_center_enter   check_in_daily_award.png → 确认在奖励中心
    4. rich_room_ac_entry_undone   rich_room_ac_undone.png → 找丰饶之间卡片 → 点击
    5. rich_room_above_kage        above_kage.png → 检测超影模式
    6. rich_room_above_kage_sweep  one_key.png → 触发扫荡
    7. challenge_rich_room         fight.png → 触发战斗
    8. back_main_screen            main_green_masked.png → 回主页
    9. verify_done
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
    ClickAction,
    Navigator,
    Node,
    NoopAction,
    Pipeline,
    SwipeAction,
)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
    PipelineRunner,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext

__all__ = ["RichRoomTask"]


# narutomobile Rich_room.json ROI
ROI_AWARD_CENTER_ENTRY = (1174, 302, 99, 105)
AWARD_TAP_X_OFFSET = 3
AWARD_TAP_Y_OFFSET = -51

ROI_CHECK_IN_CENTER = (37, 172, 130, 47)             # daily_award 标题
ROI_RICH_ROOM_AC_UNDONE = (180, 288, 1100, 225)      # 丰饶卡片 ROI;点击时 offset (12, 116, -40, -114)
RICH_ROOM_TAP_X_OFFSET = 12
RICH_ROOM_TAP_Y_OFFSET = 116

ROI_RICH_ROOM_ABOVE_KAGE = (751, 546, 395, 173)      # 超影标识
ROI_ONE_KEY = (632, 587, 224, 113)                   # 一键扫荡
ROI_ABOVE_KAGE_CONFIRM = (380, 362, 528, 219)        # 确认免费扫荡
ROI_FIGHT = (447, 568, 171, 144)                     # 出战按钮
ROI_AUTO_BATTLE_TOP = (560, 0, 156, 89)              # 自动战斗图标
ROI_GOLD_COIN = (532, 426, 219, 88)                  # 金币不足提示
ROI_TIP_X = (828, 165, 108, 103)                     # tip_x 关闭
ROI_CLICK_ANYWHERE = (465, 646, 355, 61)             # "点击"OCR 关闭结算
ROI_HOME_MAIN = (0, 0, 1920, 1080)


def _build_rich_room_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(
        name="ensure_home",
        action=NoopAction(),
        next=["rich_room_ac_entry"],
        focus="主页基线",
    ))

    # 1. 进奖励中心
    pipe.add(Node(
        name="rich_room_ac_entry",
        templates=tpls(
            "shared/award_center_entry.png",
            "shared/award_button_v5_real.png",
        ),
        roi=ROI_AWARD_CENTER_ENTRY,
        threshold=0.7,
        action=ClickAction(x_offset=AWARD_TAP_X_OFFSET, y_offset=AWARD_TAP_Y_OFFSET),
        next=["check_in_center"],
        on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=1500,
        focus="点奖励中心",
    ))

    # 2. 确认已在奖励中心
    pipe.add(Node(
        name="check_in_center",
        templates=tpls("shared/check_in_daily_award.png"),
        roi=ROI_CHECK_IN_CENTER,
        threshold=0.6,
        action=NoopAction(),
        next=["rich_room_ac_entry_undone"],
        on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=500,
        focus="确认在奖励中心",
    ))

    # 3. 找丰饶之间任务卡
    pipe.add(Node(
        name="rich_room_ac_entry_undone",
        templates=tpls("Rich_room/rich_room_ac_undone.png"),
        roi=ROI_RICH_ROOM_AC_UNDONE,
        threshold=0.8,
        green_mask=True,
        action=ClickAction(x_offset=RICH_ROOM_TAP_X_OFFSET, y_offset=RICH_ROOM_TAP_Y_OFFSET),
        next=["rich_room_in_rich_room"],
        on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=1000,
        focus="找丰饶之间任务卡",
    ))

    # 4. 验证已进丰饶之间页(ocr 可视文字 / above_kage 检测)
    pipe.add(Node(
        name="rich_room_in_rich_room",
        templates=tpls("Rich_room/above_kage.png"),
        roi=ROI_RICH_ROOM_ABOVE_KAGE,
        threshold=0.8,
        action=NoopAction(),
        next=["rich_room_above_kage_sweep"],
        on_error=["rich_room_challenge"],
        max_hit=3, post_delay_ms=1000,
        focus="进入丰饶之间",
    ))

    # 5. 超影模式 → 一键扫荡
    pipe.add(Node(
        name="rich_room_above_kage_sweep",
        templates=tpls("Rich_room/one_key.png"),
        roi=ROI_ONE_KEY,
        threshold=0.85,
        action=ClickAction(),
        next=["confirm_sweep"],
        on_error=["rich_room_challenge"],
        max_hit=2, post_delay_ms=500,
        focus="一键扫荡",
    ))

    # 6. 确认扫荡(above_kage_free)
    pipe.add(Node(
        name="confirm_sweep",
        templates=tpls("Rich_room/above_kage_free.png"),
        roi=ROI_ABOVE_KAGE_CONFIRM,
        threshold=0.7,
        action=ClickAction(),
        next=["back_main_screen"],
        on_error=["rich_room_challenge"],
        max_hit=2, post_delay_ms=1500,
        focus="确认免费扫荡",
    ))

    # 7. 非超影模式 → 出战 / 自动战斗(rich_room_combo)
    pipe.add(Node(
        name="rich_room_challenge",
        templates=tpls("Rich_room/fight.png"),
        roi=ROI_FIGHT,
        threshold=0.85,
        action=ClickAction(),
        next=["rich_room_in_fight"],
        on_error=["back_main_screen"],
        max_hit=2, post_delay_ms=2000,
        focus="出战",
    ))

    # 8. 进入战斗检测(自动战斗中)
    pipe.add(Node(
        name="rich_room_in_fight",
        templates=tpls("auto_battle/challenge.png"),
        roi=ROI_AUTO_BATTLE_TOP,
        threshold=0.7,
        green_mask=True,
        action=NoopAction(),
        next=["back_main_screen"],
        on_error=["back_main_screen"],
        max_hit=3, post_delay_ms=2000,
        focus="战斗进行中",
    ))

    # 9. 回主页
    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=ROI_HOME_MAIN,
        threshold=0.7,
        green_mask=True,
        action=NoopAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        max_hit=5, post_delay_ms=1000,
        focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="丰饶之间完成"))

    return pipe


class RichRoomTask(BaseTask):
    task_id = "rich_room"
    name = "丰饶之间"
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
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="rich_room completed", attempts=1)
        log.warning("first failed: {}", r.error)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="rich_room retry ok", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"rich_room failed: {r2.error}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        pipe = _build_rich_room_pipeline(nav)
        return runner.run(pipe, max_total_iterations=40, max_idle_iterations=8)
