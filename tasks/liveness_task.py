"""tasks.liveness_task — 活跃度宝箱领取任务(V2 真实接入)。

设计目标:
    主页 → 进入奖励中心 → 切到活跃奖励标签 → 领周度奖励 → 一键领取 → 关闭 → 返回主页。

实测 ROI (1920x1080 屏幕,来自真实模拟器):
    - 奖励按钮 (右侧中屏):       x=1170, y=290, w=130, h=100 → 模板 shared/award_button_v3.png
    - 活跃奖励 tab:              x=400,  y=80,  w=300, h=80  (待采集 liveness/liveness_tab.png)
    - 周度奖励未完成:             x=1125, y=633, w=145, h=87  → 模板 liveness/weekly_award_undone.png
    - 周度奖励确认按钮:           x=597,  y=431, w=91,  h=58  → 模板 liveness/confirm_weekly_award.png
    - 一键领取 (底部居中):        x=720,  y=720, w=480, h=100 → 模板 liveness/award_box_all.png
    - 关闭按钮 (右上角 X):        x=1820, y=60,  w=80,  h=80  → 模板 shared/x.png
    - 主页橙色按钮 (兜底):        x=30,   y=700, w=100, h=80  → 模板 shared/home_button_v3.png

真实模板路径:
    - resources/templates/actions/shared/award_button_v3.png     (已采集)
    - resources/templates/actions/liveness/liveness_tab.png      (待采集 - 切到活跃奖励 tab)
    - resources/templates/actions/liveness/weekly_award_undone.png (已有)
    - resources/templates/actions/liveness/confirm_weekly_award.png (已有)
    - resources/templates/actions/liveness/award_box_all.png     (已有)
    - resources/templates/actions/shared/x.png                   (复用)
    - resources/templates/actions/shared/home_button_v3.png       (兜底)

Pipeline 设计 (8 节点):
    1. ensure_home                  Noop
    2. find_award_button            主页找奖励按钮 → 点击进入奖励中心
    3. find_liveness_tab            在奖励中心切到"活跃奖励"标签
    4. find_weekly_award_undone     周度未领奖励 → 点击
    5. confirm_weekly               确认领奖弹窗
    6. try_one_click_claim          一键领取所有奖励 (可选)
    7. close_award_center           关闭奖励中心 (用 X 按钮, NOT BACK)
    8. back_to_home                 用主页按钮兜底 → 主页
    9. verify_done                  终点

关键约束:
    - **绝不** 使用 KeyAction(key="BACK") — 会触发"是否退出游戏"弹窗
    - 所有"返回"都用界面内 X 按钮 (shared/x.png) 或主页橙色按钮 (shared/home_button_v3.png)
    - recover() 也只使用界面内关闭按钮
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
)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
    PipelineRunner,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext

__all__ = ["LivenessTask"]


# ============================================================
# 实测 ROI (1920x1080,来自真实模拟器)
# ============================================================
ROI_AWARD_BUTTON = (1760, 460, 200, 180)        # 奖励按钮 (主页右下礼物盒图标, 2026-06-26 真机校准: conf=0.965 @ (1760, 470))
ROI_LIVENESS_TAB = (25, 255, 220, 60)             # 活跃奖励 tab (奖励中心左侧"每日任务"垂直 tab, 当前 UI 把活跃度合在每日任务页)
ROI_WEEKLY_UNDONE = (1125, 633, 145, 87)          # 周度奖励未完成
ROI_CONFIRM_WEEKLY = (597, 431, 91, 58)           # 周度奖励确认
ROI_ONE_KEY_CLAIM = (720, 720, 480, 100)          # 一键领取 (底部)
ROI_CLOSE_X = (1820, 60, 80, 80)                  # 关闭按钮 (右上)
ROI_HOME_BUTTON = (30, 700, 100, 80)              # 主页按钮 (橙色,兜底)


def _build_liveness_pipeline(nav: Navigator) -> Pipeline:
    """构造"活跃度宝箱" pipeline。"""
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

    # ---- 2. 找奖励按钮 → 点击进入奖励中心 ----
    pipe.add(Node(
        name="find_award_button",
        templates=tpls(
            "shared/award_button_v5_real.png",   # 2026-06-29 Q1 补采(新账号漩涡鸣人主页 conf=1.000 @ (1865, 537))
            "shared/award_button_v4_real.png",   # V1.2 §1.2.2 真机裁切(右下深蓝礼物盒,旧账号)
            "shared/award_center_entry_v2.png",
            "shared/award_center_entry.png",
        ),
        roi=ROI_AWARD_BUTTON,
        threshold=0.55,
        action=ClickAction(y_offset=-37),   # V1.2 §1.2.0 tap 偏上 25%
        next=["find_liveness_tab"],
        on_error=["verify_done"],
        max_hit=3,
        post_delay_ms=1500,
        focus="点击奖励按钮进入奖励中心",
    ))

    # ---- 3. 找"活跃奖励"标签 → 切换 ----
    # 模板: liveness/liveness_tab.png (待采集)
    pipe.add(Node(
        name="find_liveness_tab",
        templates=tpls(
            "liveness/liveness_tab.png",  # 优先
            "shared/check_in_daily_award.png",  # 备选
        ),
        roi=ROI_LIVENESS_TAB,
        threshold=0.55,
        action=ClickAction(),
        next=["find_weekly_award_undone"],
        on_error=["try_one_click_claim"],  # 找不到 tab,直接尝试一键领取
        max_hit=2,
        post_delay_ms=1000,
        focus="切到活跃奖励标签",
    ))

    # ---- 4. 找周度未领奖励 → 点击 ----
    pipe.add(Node(
        name="find_weekly_award_undone",
        templates=tpls("liveness/weekly_award_undone.png"),
        roi=ROI_WEEKLY_UNDONE,
        threshold=0.55,
        action=ClickAction(),
        next=["confirm_weekly"],
        on_error=["try_one_click_claim"],
        max_hit=2,
        post_delay_ms=1000,
        focus="点击周度活跃奖励未完成项",
    ))

    # ---- 5. 确认领奖 ----
    pipe.add(Node(
        name="confirm_weekly",
        templates=tpls("liveness/confirm_weekly_award.png"),
        roi=ROI_CONFIRM_WEEKLY,
        threshold=0.55,
        action=ClickAction(),
        next=["try_one_click_claim"],
        on_error=["try_one_click_claim"],
        max_hit=2,
        post_delay_ms=800,
        focus="确认周度奖励",
    ))

    # ---- 6. 一键领取所有奖励 ----
    pipe.add(Node(
        name="try_one_click_claim",
        templates=tpls(
            "liveness/award_box_all.png",
            "liveness/award_box_100.png",
            "liveness/award_box_80.png",
        ),
        roi=ROI_ONE_KEY_CLAIM,
        threshold=0.55,
        action=ClickAction(),
        next=["close_award_center"],
        on_error=["close_award_center"],
        max_hit=2,
        post_delay_ms=1200,
        focus="一键领取所有活跃奖励",
    ))

    # ---- 7. 关闭奖励中心 (界面内 X 按钮, NOT 系统 BACK) ----
    pipe.add(Node(
        name="close_award_center",
        templates=tpls(
            "shared/x.png",
            "shared/x_right_top.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["back_to_home"],
        on_error=["back_to_home"],
        max_hit=2,
        post_delay_ms=800,
        focus="关闭奖励中心 (X 按钮)",
    ))

    # ---- 8. 用主页按钮兜底回主页 (NOT 系统 BACK) ----
    pipe.add(Node(
        name="back_to_home",
        templates=tpls("shared/home_button_v3.png"),
        roi=ROI_HOME_BUTTON,
        threshold=0.5,
        action=ClickAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        max_hit=2,
        post_delay_ms=800,
        focus="点击主页按钮回主页 (兜底)",
    ))

    # ---- 9. 验证 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="活跃度宝箱流程完成",
    ))

    return pipe


class LivenessTask(BaseTask):
    """活跃度宝箱任务 (V2 真实接入)。

    流程:
        pre_check: ensure_state(HOME)
        run: Navigator 跑 9 步 pipeline
        post_check: ensure_state(HOME)
        recover: 界面内 X 按钮 + 主页按钮 (NOT 系统 BACK)
    """

    task_id = "liveness"
    name = "活跃度宝箱"
    category = "daily"
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        # P0-FIX-2026-06-29: 不用 ensure_state(HOME) — 会调 go_home() 按 BACK,
        # 触发"是否退出游戏"弹窗。让 pipeline 自己从任意状态起步。
        return ctx.common_actions is not None

    def post_check(self, ctx, result):
        # 不强制回 HOME — pipeline 内部已用 X + 主页按钮 recover
        return

    def cleanup(self, ctx, result):
        pass

    def enter(self, ctx: "ExecutionContext") -> bool:
        return True

    def verify(self, ctx: "ExecutionContext") -> bool:
        return True

    def recover(self, ctx: "ExecutionContext") -> bool:
        """恢复:使用界面内关闭按钮 (NOT 系统 BACK)。

        严格禁止 KeyAction(key="BACK") — 会触发"是否退出游戏"弹窗。
        v1.2 P1 #3: 委托给 tasks.common_actions.make_recovery_chain(double_x=True)。
        """
        if ctx.common_actions is None:
            return False
        return make_recovery_chain(
            ctx.common_actions,
            double_x=True,
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

        # 第一次尝试
        result = self._run_pipeline(adb, project_root, templates_root, log)
        if result.success:
            log.success("[liveness] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="liveness completed",
                attempts=1,
            )

        # 失败 → recover (X + 主页按钮) + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[liveness] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="liveness completed (after retry)",
                attempts=2,
            )

        # best-effort: 活跃度宝箱经常无可领奖励,接受降级成功
        # P0 修复(2026-07-02): 用 BEST_EFFORT 而非 SUCCESS 避免掩盖故障
        log.warning("liveness best-effort: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.BEST_EFFORT,
            message="liveness best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_liveness_pipeline(nav)
        return runner.run(pipe, max_total_iterations=25, max_idle_iterations=4)