"""tasks.recruit_task — 招募任务(Phase 7+,基于实跑校准的 ROI)。

设计目标:
    主页 → 点击"招募"入口 → 高级招募 tab → "1抽"(免费) → 确认 → 跳过动画 → 关闭 → 主页。

模板来源:
    - actions/shared/recruit_button_v3.png          (HOME 招募入口,实测在 1770,180 命中)
    - actions/recruit/headhunt_tab.png              (左侧"高级招募"tab,实截)
    - actions/recruit/normal_recruit_tab.png        (左侧"普通招募"tab,实截)
    - actions/recruit/free_headhunt.png             (免费"1抽"按钮,实截)
    - actions/recruit/discount_recruit.png          ("10抽"按钮,实截)
    - actions/recruit/headhunt_entry.png            (源仓库老版入口,作 fallback)
    - actions/recruit/free_headhunt_1.png           (源仓库备选免费按钮)
    - actions/recruit/no_free_headhunt.png          (源仓库无免费态,作 fallback)
    - actions/recruit/recruit_done.png / 2.png      (招募完成 / 跳过动画)
    - actions/recruit/confirm_free_headhunt.png    (招募确认弹窗,源仓库)

实测 ROI (1920x1080,本次实跑校准):
    - 招募入口 (HOME 右上):    x=1770, y=180,  w=100, h=110  (与 right_shop_v3 同列)
    - 高级招募 tab (左侧栏):   x=30,   y=180,  w=170, h=80
    - 免费"1抽"按钮:           x=640,  y=900,  w=440, h=110
    - "10抽"按钮:              x=1080, y=900,  w=440, h=110
    - 普通招募 tab (左侧栏):   x=30,   y=850,  w=170, h=80
    - 招募确认弹窗 (兜底 ROI): x=300,  y=525,  w=197, h=70   (源仓库 ROI)
    - 跳过动画按钮 (兜底):     x=624,  y=508,  w=427, h=143  (源仓库 ROI)
    - 关闭按钮 (右上 X):       x=1820, y=60,   w=80,  h=80
    - 主页按钮 (兜底):         x=30,   y=700,  w=100, h=80

Pipeline 设计 (8 节点,精简版 - 重点跑免费高招):
    1. ensure_home              Noop
    2. find_recruit_entry       主页找招募入口 → 点击
    3. switch_to_high_recruit   切到高级招募 tab (headhunt_tab.png)
    4. find_free_recruit        找免费"1抽" → 点击
    5. confirm_recruit          确认弹窗 (confirm_free_headhunt.png)
    6. skip_animation           跳过动画 (recruit_done.png)
    7. close_recruit            关闭招募页 (X)
    8. back_to_home             主页按钮兜底
    9. verify_done              终点

关键约束:
    - **绝不** 使用 KeyAction(key="BACK") — 会触发"是否退出游戏"弹窗
    - 所有"返回"都用界面内 X 按钮 (shared/x.png) 或主页橙色按钮 (shared/home_button_v3.png)
    - recover() 也只使用界面内关闭按钮
    - "best-effort SUCCESS" 语义: 招募已用完时仍以 SUCCESS 返回

依赖:
    - tasks.navigator
    - tasks.pipeline_runner
    - ADBClient (从 ctx.common_actions.adb)
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

__all__ = ["RecruitTask"]


# ============================================================
# 实测 ROI (1920x1080,本次实跑校准)
# ============================================================
ROI_RECRUIT_ENTRY = (1770, 180, 100, 110)      # HOME 右上招募入口
ROI_HIGH_RECRUIT_TAB = (30, 180, 170, 80)      # 左侧"高级招募"tab
ROI_FREE_RECRUIT = (640, 900, 440, 110)        # 主面板"1抽"按钮
ROI_DISCOUNT_RECRUIT = (1080, 900, 440, 110)   # 主面板"10抽"按钮
ROI_NORMAL_RECRUIT_TAB = (30, 850, 170, 80)    # 左侧"普通招募"tab
ROI_CONFIRM_RECRUIT = (300, 525, 197, 70)      # 招募确认弹窗 (源仓库 ROI)
ROI_SKIP_ANIM = (624, 508, 427, 143)           # 跳过动画 (源仓库 ROI)
ROI_CLOSE_X = (1820, 60, 80, 80)                # 关闭按钮 (右上)
ROI_HOME_BUTTON = (30, 700, 100, 80)            # 主页按钮 (兜底)


def _build_recruit_pipeline(nav: Navigator) -> Pipeline:
    """构造"招募" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_recruit_entry"],
        focus="ensure home (pre_check)",
    ))

    # ---- 2. 找招募入口 → 点击 ----
    # 实测 v3 模板命中 (1770, 180);源仓库 headhunt_entry.png 是老版布局,作 fallback
    pipe.add(Node(
        name="find_recruit_entry",
        templates=tpls(
            "shared/recruit_button_v3.png",
            "recruit/headhunt_entry.png",
        ),
        roi=ROI_RECRUIT_ENTRY,
        threshold=0.7,
        action=ClickAction(),
        next=["switch_to_high_recruit"],
        on_error=["verify_done"],
        max_hit=3,
        post_delay_ms=2000,
        focus="点击主页招募入口",
    ))

    # ---- 3. 切到"高级招募" tab ----
    pipe.add(Node(
        name="switch_to_high_recruit",
        templates=tpls(
            "recruit/headhunt_tab.png",
            "recruit/headhunt.png",            # 源仓库备选
            "recruit/headhunt_selected.png",
        ),
        roi=ROI_HIGH_RECRUIT_TAB,
        threshold=0.6,
        action=ClickAction(),
        next=["find_free_recruit"],
        on_error=["verify_done"],
        max_hit=3,
        post_delay_ms=1500,
        focus="切到高级招募 tab",
    ))

    # ---- 4. 找免费"1抽"按钮 → 点击 ----
    pipe.add(Node(
        name="find_free_recruit",
        templates=tpls(
            "recruit/free_headhunt.png",       # 实截的 1抽 按钮
            "recruit/free_headhunt_1.png",     # 源仓库备选
        ),
        roi=ROI_FREE_RECRUIT,
        threshold=0.6,
        action=ClickAction(),
        next=["confirm_recruit"],
        on_error=["close_recruit"],            # 没免费 → 关招募页
        max_hit=3,
        post_delay_ms=1500,
        focus="点击免费 1抽 按钮",
    ))

    # ---- 5. 招募确认弹窗 → 点击确定 ----
    pipe.add(Node(
        name="confirm_recruit",
        templates=tpls(
            "recruit/confirm_free_headhunt.png",
            "shared/confrim.png",              # 兜底:通用确认按钮
            "shared/confrim_small.png",
        ),
        roi=ROI_CONFIRM_RECRUIT,
        threshold=0.55,
        action=ClickAction(),
        next=["skip_animation"],
        on_error=["close_recruit"],
        max_hit=3,
        post_delay_ms=1000,
        focus="确认招募",
    ))

    # ---- 6. 跳过招募动画 ----
    pipe.add(Node(
        name="skip_animation",
        templates=tpls(
            "recruit/recruit_done.png",
            "recruit/recruit_done_2.png",
            "shared/x.png",                    # 兜底:动画结束 X
            "shared/notice_x.png",
        ),
        roi=ROI_SKIP_ANIM,
        threshold=0.55,
        action=ClickAction(),
        next=["close_recruit"],
        on_error=["close_recruit"],
        max_hit=3,
        post_delay_ms=2500,                    # 招募动画通常 2-3s
        focus="跳过招募动画",
    ))

    # ---- 7. 关闭招募页 (界面内 X, NOT 系统 BACK) ----
    pipe.add(Node(
        name="close_recruit",
        templates=tpls(
            "shared/x.png",
            "shared/x_right_top.png",
            "shared/green_masked_x.png",
            "shared/notice_x.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["back_to_home"],
        on_error=["back_to_home"],
        max_hit=2,
        post_delay_ms=800,
        focus="关闭招募页 (X 按钮)",
    ))

    # ---- 8. 主页按钮兜底 ----
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
        focus="点击主页按钮 (兜底)",
    ))

    # ---- 9. 终点 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="招募流程完成",
    ))

    return pipe


class RecruitTask(BaseTask):
    """招募任务 — Phase 7+,基于实跑校准的 ROI。"""

    task_id = "recruit"
    name = "招募"
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
            log.success("[recruit] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="recruit completed",
                attempts=1,
            )

        # 失败 → recover (X + 主页按钮) + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[recruit] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="recruit completed (after retry)",
                attempts=2,
            )

        # best-effort: 招募用完 / 模板失效是常态,接受降级成功
        # P0 修复(2026-07-02): 用 BEST_EFFORT 而非 SUCCESS 避免掩盖故障
        log.warning("recruit best-effort: {}", result2.error)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.BEST_EFFORT,
            message="recruit best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_recruit_pipeline(nav)
        return runner.run(pipe, max_total_iterations=30, max_idle_iterations=5)