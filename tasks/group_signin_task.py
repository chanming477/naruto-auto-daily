"""tasks.group_signin_task — 组织签到(组织祈福)任务(2026-06-29 14:23 user 强求补建)。

设计目标:
    主页 → 奖励中心(award_center_entry)→ "组织玩法/祈福"任务卡 → 前往 → 焚香祈福 → 回主页。

ROI 直接照抄 narutomobile-main Group.json(权威源):
    - 奖励中心入口: award_center_entry.png ROI (1174, 302, 99, 105) → 点 (1222, 354)
        我之前 ROI_AWARD_BUTTON (1760, 460, 200, 180) tap (1842, 536) 是错的。
    - 奖励中心 → 组织玩法任务卡: group_gameplay_undone.png ROI (44, 382, 177, 118)
        narutomobile 做法:点卡片 tab 进入(卡片 ROI 是 (12, 116, -40, -114) offset)
    - 组织玩法页 → "前往": OCR ROI (239, 533, 178, 144) → 进祈福界面
    - 焚香祈福: copper_pray.png ROI (476, 542, 200, 80) 中心 (576, 582)
        user 14:23 裁的 burn_incense_pray_btn.png = "6000 焚香祈福" 同义
    - 确认: confirm_group_pray.png / confirm_copper_pray_done.png

Pipeline (8 节点,严格按 narutomobile):
    1. ensure_home                 Noop
    2. award_center_enter          进奖励中心 → 点 (1222, 354)
    3. swipe_for_award_center_find 横向滑动找"组织祈福"卡片(可选)
    4. group_gameplay_undone       找到 → 选中(DoNothing 验证)
    5. goto_group_pray             OCR "前往" → 点击进祈福界面
    6. copper_group_pray           copper_pray.png / burn_incense_pray_btn → 点 (576, 582)
    7. confirm_copper_group_pray   确认对话框 → 点击
    8. back_main_screen            main_green_masked.png → 验证回主页
    9. verify_done                 Noop

依赖: tasks.navigator, tasks.pipeline_runner
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

__all__ = ["GroupSigninTask"]


# narutomobile ROI(奖励中心 / 组织玩法 / 前往 / 焚香祈福)
ROI_AWARD_CENTER_ENTRY = (1174, 302, 99, 105)       # narutomobile SharedNode.json award_center_enter
# tap (1222, 354)(narutomobile 直接 action Click 默认 tap match 中心,实际试 (1222, 354))
AWARD_TAP_X_OFFSET = 3                              # match_x ≈ 1219 → 1222
AWARD_TAP_Y_OFFSET = -51                            # match_y ≈ 354→ 304(narutomobile center is y=354 but real button top is 302)

# 奖励中心内"组织玩法"卡片(左侧任务卡列表)
ROI_GROUP_GAMEPLAY_UNDONE = (44, 382, 177, 118)     # narutomobile group_gameplay_undone

# 横向滑动找组织祈福卡片(narutomobile swipe_for_award_center_find)
SWIPE_AWARD_BEGIN = (1133, 169, 56, 61)
SWIPE_AWARD_END = (542, 169, 56, 61)

# "前往"按钮 OCR ROI
ROI_GOTO_GROUP_PRAY = (239, 533, 178, 144)

# 焚香祈福按钮 ROI
ROI_COPPER_PRAY = (476, 542, 200, 80)               # 中心 (576, 582)

# 主页验证 ROI(全屏绿通道)
ROI_HOME_MAIN = (0, 0, 1920, 1080)


def _build_group_signin_pipeline(nav: Navigator) -> Pipeline:
    """构造"组织签到(组织祈福)" pipeline (narutomobile ROI)。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        action=NoopAction(),
        next=["award_center_enter"],
        focus="主页基线",
    ))

    # ---- 2. 找奖励中心入口(award_center_entry.png)→ 点 (1222, 354) ----
    pipe.add(Node(
        name="award_center_enter",
        templates=tpls(
            "shared/award_center_entry.png",           # narutomobile 模板
            "shared/award_button_v5_real.png",         # 2026-06-29 v5_real 真机 conf=0.997
            "shared/award_button_v4_real.png",
            "shared/award_center_entry_v2.png",
        ),
        roi=ROI_AWARD_CENTER_ENTRY,
        threshold=0.6,
        action=ClickAction(x_offset=AWARD_TAP_X_OFFSET, y_offset=AWARD_TAP_Y_OFFSET),
        next=["check_in_award_center"],
        on_error=["back_main_screen"],
        max_hit=3,
        post_delay_ms=1500,
        focus="点奖励中心 (1222, 354)",
    ))

    # ---- 3. 验证已在奖励中心(检测 check_in_daily_award)----
    pipe.add(Node(
        name="check_in_award_center",
        templates=tpls(
            "shared/check_in_daily_award.png",         # narutomobile 已签到/未签到 状态标志
            "shared/check_not_in_daily_award.png",
        ),
        roi=(37, 172, 130, 47),                        # narutomobile 直接给
        threshold=0.6,
        action=NoopAction(),
        next=["find_group_gameplay_undone"],
        on_error=["back_main_screen"],
        max_hit=5,
        post_delay_ms=500,
        focus="确认在奖励中心",
    ))

    # ---- 4. 找"组织祈福/组织玩法"任务卡(group_gameplay_undone)----
    # narutomobile:在 ROI (44, 382, 177, 118) 找 → target_offset (12, 116, -40, -114)
    pipe.add(Node(
        name="find_group_gameplay_undone",
        templates=tpls(
            "group/group_gameplay_undone.png",         # narutomobile "组织玩法"(可能叫"组织祈福"在新版 UI)
            "group/group_pray_card_undone.png",        # user 14:23 裁的"组织祈福"任务卡
            "group/group_pray_undone.png",
            "group/group_ac_undone.png",
        ),
        roi=ROI_GROUP_GAMEPLAY_UNDONE,
        threshold=0.7,
        action=ClickAction(),                          # 点击 match 中心 → 卡片本体
        next=["check_selected_group_gameplay"],
        on_error=["swipe_for_award_center_find"],
        max_hit=3,
        post_delay_ms=1000,
        focus="找组织玩法任务卡",
    ))

    # ---- 4b. 横向滑动找组织祈福卡片(若左侧列表不可见)----
    pipe.add(Node(
        name="swipe_for_award_center_find",
        templates=[],
        action=SwipeAction(
            x1=SWIPE_AWARD_BEGIN[0], y1=SWIPE_AWARD_BEGIN[1],
            x2=SWIPE_AWARD_END[0], y2=SWIPE_AWARD_END[1],
            duration_ms=200,
        ),
        next=["find_group_gameplay_undone_retry"],
        on_error=["back_main_screen"],
        max_hit=3,
        post_delay_ms=500,
        focus="横向滑动奖励中心找组织祈福",
    ))

    pipe.add(Node(
        name="find_group_gameplay_undone_retry",
        templates=tpls(
            "group/group_gameplay_undone.png",
            "group/group_pray_card_undone.png",
            "group/group_pray_undone.png",
            "group/group_ac_undone.png",
        ),
        roi=ROI_GROUP_GAMEPLAY_UNDONE,
        threshold=0.7,
        action=ClickAction(),
        next=["check_selected_group_gameplay"],
        on_error=["back_main_screen"],
        max_hit=2,
        post_delay_ms=1000,
        focus="滑动后找组织玩法任务卡",
    ))

    # ---- 5. 验证选中(DoNothing)----
    pipe.add(Node(
        name="check_selected_group_gameplay",
        templates=tpls(
            "group/selected_group_gameplay.png",
        ),
        roi=ROI_GROUP_GAMEPLAY_UNDONE,
        threshold=0.7,
        action=NoopAction(),
        next=["goto_group_pray"],
        on_error=["back_main_screen"],
        max_hit=3,
        post_delay_ms=500,
        focus="确认选中组织玩法",
    ))

    # ---- 6. 点"前往"按钮(OCR)----
    # narutomobile:goto_group_pray OCR "前往" ROI (239, 533, 178, 144) → 点击
    # 我用 template group_pray_go_btn.png (user 14:23 裁的 "立刻前往"按钮)
    pipe.add(Node(
        name="goto_group_pray",
        templates=tpls(
            "group/group_pray_go_btn.png",             # user 14:23 裁的"立刻前往"
        ),
        roi=ROI_GOTO_GROUP_PRAY,
        threshold=0.6,
        action=ClickAction(),
        next=["copper_group_pray"],
        on_error=["back_main_screen"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点'前往'进祈福界面",
    ))

    # ---- 7. 点焚香祈福 / 铜币签到 ----
    pipe.add(Node(
        name="copper_group_pray",
        templates=tpls(
            "group/burn_incense_pray_btn.png",         # 2026-06-29 14:23 user 裁的 "6000 焚香祈福"
            "group/copper_pray.png",                   # narutomobile 模板(190x70)
        ),
        roi=ROI_COPPER_PRAY,
        threshold=0.6,
        action=ClickAction(),
        next=["confirm_copper_group_pray"],
        on_error=["back_main_screen"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点焚香祈福按钮 (576, 582)",
    ))

    # ---- 8. 确认对话框 ----
    pipe.add(Node(
        name="confirm_copper_group_pray",
        templates=tpls(
            "group/confirm_group_pray.png",
            "group/confirm_copper_pray_done.png",
        ),
        threshold=0.6,
        action=ClickAction(),
        next=["back_main_screen"],
        on_error=["back_main_screen"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点击确认",
    ))

    # ---- 9. 回主页(main_green_masked.png)----
    pipe.add(Node(
        name="back_main_screen",
        templates=tpls(
            "state/main_green_masked.png",
        ),
        roi=ROI_HOME_MAIN,
        threshold=0.7,
        green_mask=True,
        action=NoopAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        max_hit=5,
        post_delay_ms=1000,
        focus="回主页验证",
    ))

    # ---- 10. 终点 ----
    pipe.add(Node(
        name="verify_done",
        action=NoopAction(),
        next=[],
        focus="组织签到流程完成",
    ))

    return pipe


class GroupSigninTask(BaseTask):
    """组织签到(组织祈福)任务。"""

    task_id = "group_signin"
    name = "组织签到(组织祈福)"
    category = "weekly"
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        log = ctx.bind_logger(self.task_id)
        if ctx.common_actions is None:
            return False
        return bool(ctx.common_actions.ensure_state(GameState.HOME))

    def post_check(self, ctx: "ExecutionContext", result: TaskResult) -> None:
        log = ctx.bind_logger(self.task_id)
        if ctx.common_actions is not None:
            ctx.common_actions.ensure_state(GameState.HOME)

    def cleanup(self, ctx: "ExecutionContext", result: TaskResult) -> None:
        pass

    def enter(self, ctx: "ExecutionContext") -> bool:
        return True

    def verify(self, ctx: "ExecutionContext") -> bool:
        return True

    def recover(self, ctx: "ExecutionContext") -> bool:
        """恢复:用界面内关闭按钮 + 主页按钮(NOT 系统 BACK)。"""
        if ctx.common_actions is None:
            return False
        return make_recovery_chain(
            ctx.common_actions,
            double_x=False,
            log=ctx.bind_logger(self.task_id),
        )

    def run(self, ctx: "ExecutionContext") -> TaskResult:
        log = ctx.bind_logger(self.task_id)

        if ctx.common_actions is None:
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.FAIL,
                message="ctx.common_actions is None",
                attempts=0,
            )

        adb = ctx.common_actions.adb
        project_root = Path(ctx.config.project_root)
        templates_root = project_root / "resources" / "templates" / "actions"

        # 第一次
        result = self._run_pipeline(adb, project_root, templates_root, log)
        if result.success:
            log.success("[group_signin] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="group_signin completed",
                attempts=1,
            )

        # 失败 → recover + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[group_signin] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="group_signin completed (after retry)",
                attempts=2,
            )

        # 真失败(2026-06-30:不再 best-effort SUCCESS 掩盖)
        log.error("group_signin 真失败: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.FAIL,
            message="group_signin failed: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_group_signin_pipeline(nav)
        return runner.run(pipe, max_total_iterations=50, max_idle_iterations=8)
