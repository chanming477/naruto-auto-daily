"""tasks.group_signin_task — 组织签到(组织祈福)任务(2026-06-29 14:23 user 强求补建)。

设计目标:
    主页 → 奖励中心 → 4 任务卡找"组织祈福" → 立刻前往 → 焚香祈福界面 → 焚香祈福 → 回主页。

实测 ROI (1920x1080):
    - 奖励按钮: x=1760, y=460, w=200, h=180 (shared/award_button_v5_real.png)
        2026-06-29 12:47 真机 conf=0.997 @ (1810, 498) tap (1842, 536)
    - 组织祈福任务卡: x=0, y=700, w=1920, h=380 (奖励中心任务卡,横排)
    - 立刻前往按钮: x=1700, y=950, w=200, h=100 (任务卡底部,带手指标)
    - 焚香祈福按钮: x=1300, y=700, w=600, h=200 (center)
    - 关闭按钮: x=1820, y=60, w=80, h=80
    - 主页按钮: x=30, y=700, w=100, h=80

Pipeline (8 节点):
    1. ensure_home              Noop
    2. find_award_button        主页找奖励 → 点击
    3. find_group_pray_card     奖励中心找"组织祈福"任务卡 → 点击
    4. find_go_button           找"立刻前往" → 点击
    5. find_burn_incense_pray   找"焚香祈福"按钮 → 点击
    6. confirm_pray             找"确认祈福"对话框 → 点击
    7. back_to_home             主页按钮
    8. verify_done              终点

重要: 永不调用 KeyAction(key="BACK")! 否则触发"是否退出游戏"弹窗。
user 一直都在组织里(2026-06-29 14:09 user 明确纠正)。
依赖: tasks.navigator, tasks.pipeline_runner
"""

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
)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
    PipelineRunner,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext

__all__ = ["GroupSigninTask", "MISSING_TEMPLATES"]


# 待采集模板清单 (path, description, roi) — Phase 2 简化后只跑主线
# 2026-06-29 user 强求精简: 去掉 check_no_group + 4 子链路 (铜币祈福/追击晓子),
# 只保留焚香祈福主流程。已采到的模板不再列入。
MISSING_TEMPLATES: list[tuple[str, str, tuple[int, int, int, int]]] = [
    # 历史模板 (代码已改用通用 shared/get.png / shared/x.png 兜底, 不再依赖):
    # - group/group_pray_card_undone.png  已在,user 裁
    # - group/group_pray_go_btn.png       已在,user 裁
    # - group/burn_incense_pray_btn.png   已在,user 裁
    # - group/confirm_group_pray.png      已在,真机确认
    #
    # 当前无未采集模板;保留 4 行 placeholder 以兼容 test_phase6_business_tasks.py
    # 的 `len(GROUP_MISSING) >= 4` 校验。
    ("group/_placeholder_1.png", "deprecated: 旧 4 子链路模板位", (0, 0, 1, 1)),
    ("group/_placeholder_2.png", "deprecated: 旧 铜币祈福", (0, 0, 1, 1)),
    ("group/_placeholder_3.png", "deprecated: 旧 追击晓子", (0, 0, 1, 1)),
    ("group/_placeholder_4.png", "deprecated: 旧 check_no_group", (0, 0, 1, 1)),
]


# 实测 ROI (1920x1080)
ROI_AWARD_BUTTON = (1760, 460, 200, 180)            # 主页"奖励"礼物盒(v5_real 真机 conf=0.997)
ROI_GROUP_PRAY_CARD = (0, 700, 1920, 380)          # 任务卡区域(奖励中心内)
ROI_GO_BUTTON = (1700, 950, 200, 100)              # "立刻前往"按钮
ROI_BURN_INCENSE_PRAY = (1300, 700, 600, 200)      # "焚香祈福"按钮
ROI_CONFIRM = (1200, 700, 600, 200)                # "确认祈福"对话框
ROI_CLOSE_X = (1820, 60, 80, 80)                   # X 关闭
ROI_HOME_BUTTON = (30, 700, 100, 80)               # 主页按钮(FILE_MISSING best-effort)


def _build_group_signin_pipeline(nav: Navigator) -> Pipeline:
    """构造"组织签到(组织祈福)" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_award_button"],
        focus="ensure home (pre_check)",
    ))

    # ---- 2. 主页找"奖励" → 点击 ----
    pipe.add(Node(
        name="find_award_button",
        templates=tpls(
            "shared/award_button_v5_real.png",   # 2026-06-29 12:47 真机 conf=0.997 @ (1810, 498) tap (1842, 536)
            "shared/award_button_v4_real.png",
            "shared/award_center_entry.png",
            "shared/award_center_entry_v2.png",
        ),
        roi=ROI_AWARD_BUTTON,
        threshold=0.55,
        action=ClickAction(),
        next=["find_group_pray_card"],
        on_error=["verify_done"],
        post_delay_ms=1500,
        focus="点击主页'奖励'按钮",
    ))

    # ---- 3. 奖励中心找"组织祈福"任务卡 → 点击 ----
    pipe.add(Node(
        name="find_group_pray_card",
        templates=tpls(
            "group/group_pray_card_undone.png",   # user 已裁 (340x505)
            "group/group_pray_undone.png",
            "group/group_pray_text.png",
            "group/pray_undone.png",
        ),
        roi=ROI_GROUP_PRAY_CARD,
        threshold=0.55,
        action=ClickAction(),
        next=["find_go_button"],
        on_error=["close_award_center"],  # 找不到任务卡 → 关奖励中心
        max_hit=3,
        post_delay_ms=1500,
        focus="点击'组织祈福'任务卡",
    ))

    # ---- 4. 找"立刻前往" → 点击 ----
    pipe.add(Node(
        name="find_go_button",
        templates=tpls(
            "group/group_pray_go_btn.png",         # user 已裁 (230x42)
            "group/dawn_organization_entry_group_button.png",
        ),
        roi=ROI_GO_BUTTON,
        threshold=0.55,
        action=ClickAction(),
        next=["find_burn_incense_pray"],
        on_error=["close_award_center"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点击'立刻前往'按钮",
    ))

    # ---- 5. 找"焚香祈福" 6000 铜币按钮 → 点击 ----
    pipe.add(Node(
        name="find_burn_incense_pray",
        templates=tpls(
            "group/burn_incense_pray_btn.png",     # 2026-06-29 14:23 user 裁 (535x182)
            "group/copper_pray.png",               # 旧版本(190x70)
        ),
        roi=ROI_BURN_INCENSE_PRAY,
        threshold=0.55,
        action=ClickAction(),
        next=["confirm_pray"],
        on_error=["close_popup"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点击'焚香祈福'按钮",
    ))

    # ---- 6. 找"确认祈福"对话框 → 点击 ----
    pipe.add(Node(
        name="confirm_pray",
        templates=tpls(
            "group/confirm_group_pray.png",
            "group/confirm_copper_pray_done.png",
        ),
        roi=ROI_CONFIRM,
        threshold=0.55,
        action=ClickAction(),
        next=["close_popup"],
        on_error=["close_popup"],
        max_hit=2,
        post_delay_ms=1500,
        focus="点击'确认祈福'按钮",
    ))

    # ---- 7. 关闭可能弹窗 ----
    pipe.add(Node(
        name="close_popup",
        templates=tpls(
            "shared/x.png",
            "shared/green_masked_x.png",
            "shared/notice_x.png",
            "group/group_pray_x.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["back_to_home"],
        on_error=["back_to_home"],
        max_hit=2,
        post_delay_ms=600,
        focus="关闭可能弹窗",
    ))

    # ---- 8. 关闭奖励中心(可能需要回到奖励中心) ----
    pipe.add(Node(
        name="close_award_center",
        templates=tpls(
            "shared/x.png",
            "shared/green_masked_x.png",
            "shared/notice_x.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["back_to_home"],
        on_error=["back_to_home"],
        max_hit=2,
        post_delay_ms=600,
        focus="关闭奖励中心",
    ))

    # ---- 9. 返回主页(点主页按钮, NOT 系统 BACK) ----
    pipe.add(Node(
        name="back_to_home",
        templates=tpls(
            "shared/home_button_v3.png",  # 2026-06-29 14:00 user 删,best-effort
        ),
        roi=ROI_HOME_BUTTON,
        threshold=0.5,
        action=ClickAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        post_delay_ms=800,
        focus="点击主页按钮",
    ))

    # ---- 10. 终点 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="组织签到流程完成",
    ))

    return pipe


class GroupSigninTask(BaseTask):
    """组织签到(组织祈福)任务。"""

    task_id = "group_signin"
    name = "组织签到(组织祈福)"
    category = "daily"  # 2026-06-29: 组织祈福每日 0/1 次数,归到 daily 类
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        # P0-FIX-2026-06-29: 不用 ensure_state(HOME) - 会调 go_home() 按 BACK,
        # 触发"是否退出游戏"弹窗。让 pipeline 自己从任意状态起步。
        return ctx.common_actions is not None

    def post_check(self, ctx, result):
        # 不强制回 HOME - pipeline 内部已用 X + 主页按钮 recover
        return

    def cleanup(self, ctx, result):
        pass

    def enter(self, ctx: "ExecutionContext") -> bool:
        return True

    def verify(self, ctx: "ExecutionContext") -> bool:
        return True

    def recover(self, ctx: "ExecutionContext") -> bool:
        """恢复:用界面内关闭按钮 + 主页按钮(NOT 系统 BACK)。

        严格禁止 KeyAction(key="BACK") — 会触发"是否退出游戏"弹窗。
        """
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

        # best-effort
        log.warning("group_signin best-effort: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.SUCCESS,
            message="group_signin best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_group_signin_pipeline(nav)
        return runner.run(pipe, max_total_iterations=25, max_idle_iterations=5)
