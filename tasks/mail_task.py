"""tasks.mail_task — 邮件领取任务(Phase 6 B/Phase 7 真实接入 V2)。

设计目标:
    在主页 → 点击信封 → 进入邮件页 → 一键领取 → 关闭 → 返回主页。

实测 ROI (1920x1080 屏幕):
    - 信封(邮件入口): x=30, y=460, w=130, h=100 → 模板 mail/mail_envelope.png
    - 一键提取按钮: 邮件页底部居中 (estimate: x=600, y=950, w=720, h=100)
    - 关闭按钮: 邮件页右上角 x=1820, y=80, w=80, h=80

真实模板路径:
    - resources/templates/actions/mail/mail_envelope.png  (已采集)
    - resources/templates/actions/mail/one_key_claim.png  (待采集 - 进邮件后采)
    - resources/templates/actions/mail/mail_close_x.png   (复用 shared/x.png)

Pipeline 设计 (6 节点):
    1. ensure_home              Noop
    2. find_mail_entry          主页找信封 → 点击
    3. find_one_key_claim       邮件页找一键提取 → 点击
    4. close_mail               点击关闭按钮 (NOT 系统 BACK - 避免退出游戏)
    5. verify_done              终点

依赖:
    - tasks.navigator
    - tasks.pipeline_runner
    - ADBClient (从 ctx.common_actions.adb)
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
    KeyAction,
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

__all__ = ["MailTask", "MISSING_TEMPLATES"]

# 待采集模板清单 (path, description, roi) — 已采完,仅留注释作历史
# 2026-06-26 真机采集结果:
#   mail/mail_envelope.png  ✅ 已存在(主页信封入口)
#   mail/mail_done.png      ✅ 已存在(邮件领取完成标识)
#   mail/mail_close_x.png   ✅ 已采(2026-06-26 红色 X @ (1760,162))
#   mail/one_key_claim.png  ⏭️ 跳过(邮箱空采不到;代码已改用 shared/get.png 通用领取)
MISSING_TEMPLATES: list[tuple[str, str, tuple[int, int, int, int]]] = []


# 真实 ROI（基于实测）
# 2026-06-26 真机勘察: 黄色信封实际位置 (86, 417), hit area 中心 (95, 440)
# 模板 mail_envelope.png 已重裁为黄色信封(2026-06-26 之前是橙色漩涡,
# 命名错,实际匹配到的是忍者社区图标 — 已并存为 home_special/ninja_community.png)
ROI_MAIL_ENTRY = (30, 350, 130, 130)         # 黄色信封 (主页左上, 战区寡事信封) 中心 (80, 385)
# 2026-06-26 真机勘察: "一键提取"按钮实际位置 (670, 932), 视觉大小 240x75
# 黄底 + 橙色"一键提取"文字; (600, 950) 偏下 18px + ROI 中心 1000 错位严重
ROI_ONE_KEY_CLAIM = (530, 880, 280, 105)      # 邮件页"一键提取"按钮 ROI
# 2026-06-26 真机勘察: 邮件页 X 实际位置 (1760, 162) — 蓝色背景框 + 红色 X,
# 跟主页右上 (1820, 60) 完全不同。需要单独 ROI 不能复用
ROI_MAIL_CLOSE_X = (1750, 30, 140, 130)      # 邮件页专属关闭按钮 (邮件页右上 X)
ROI_CLOSE_X = ROI_MAIL_CLOSE_X                # 邮件页用此 ROI
ROI_HOME_BUTTON = (30, 700, 100, 80)         # 主页按钮 (橙色房子,可选)


def _build_mail_pipeline(nav: Navigator) -> Pipeline:
    """构造"邮件领取" pipeline。"""
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # ---- 1. 主页基线 ----
    pipe.add(Node(
        name="ensure_home",
        templates=[],
        action=NoopAction(),
        next=["find_mail_entry"],
        focus="ensure home (pre_check)",
    ))

    # ---- 2. 找信封入口 → 点击 ----
    pipe.add(Node(
        name="find_mail_entry",
        templates=tpls(
            "mail/mail_envelope.png",
            # 备选:用同一目录下的命名版本(若未来采集 v2/v3 放进来)
            # 历史包袱:旧版本曾引用 home_special/mail_envelope.png,但该目录为空,已删除
        ),
        roi=ROI_MAIL_ENTRY,
        threshold=0.55,
        action=ClickAction(),
        next=["find_one_key_claim"],
        on_error=["verify_done"],  # 找不到就当没邮件,直接完成
        post_delay_ms=1500,
        focus="点击信封(邮件入口)",
    ))

    # ---- 3. 找"一键提取"按钮 → 点击 ----
    # 如果看不到一键提取按钮(没有邮件奖励),跳过
    # 2026-06-26 真机采集: 邮箱有邮件时显示"一键提取"按钮,位置 (670, 932),
    # 视觉 240x75 黄底橙色"一键提取"
    pipe.add(Node(
        name="find_one_key_claim",
        templates=tpls(
            "mail/one_key_claim.png",  # 优先:邮箱专属"一键提取"按钮(240x75)
            "shared/get.png",          # 备选:通用"领取"按钮(66x44)
        ),
        roi=ROI_ONE_KEY_CLAIM,
        threshold=0.55,
        action=ClickAction(),
        next=["close_mail"],
        on_error=["close_mail"],  # 没有一键提取 → 直接关闭(没邮件)
        max_hit=3,
        post_delay_ms=1500,
        focus="一键提取邮件奖励",
    ))

    # ---- 4. 关闭邮件页 (界面内的关闭按钮,NOT 系统 BACK) ----
    pipe.add(Node(
        name="close_mail",
        templates=tpls(
            "shared/x.png",
            "shared/green_masked_x.png",
            "mail/mail_close_x.png",
        ),
        roi=ROI_CLOSE_X,
        threshold=0.5,
        action=ClickAction(),
        next=["verify_done"],
        on_error=["verify_done"],
        max_hit=2,
        post_delay_ms=800,
        focus="关闭邮件页",
    ))

    # ---- 5. 验证 ----
    pipe.add(Node(
        name="verify_done",
        templates=[],
        action=NoopAction(),
        next=[],
        focus="邮件流程完成",
    ))

    return pipe


class MailTask(BaseTask):
    """邮件领取任务。"""

    task_id = "mail"
    name = "邮件领取"
    category = "daily"
    max_retries: int = 0

    def pre_check(self, ctx: "ExecutionContext") -> bool:
        # P0-FIX-2026-06-29: 不用 ensure_state(HOME) — 会调 go_home() 按 BACK,
        # 触发"是否退出游戏"弹窗。让 pipeline 自己从任意状态起步。
        return ctx.common_actions is not None

    def post_check(self, ctx, result):
        # 不强制回 HOME — pipeline 内部已用 X + 主页按钮 recover
        return

    def cleanup(self, ctx: "ExecutionContext", result: TaskResult) -> None:
        pass

    def enter(self, ctx: "ExecutionContext") -> bool:
        return True

    def verify(self, ctx: "ExecutionContext") -> bool:
        return True

    def recover(self, ctx: "ExecutionContext") -> bool:
        """恢复:用界面内关闭按钮 + 主页按钮(NOT 系统 BACK)。

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
        import time  # 局部 import 避免污染
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
            log.success("[mail] completed")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="mail completed",
                attempts=1,
            )

        # 失败 → recover(界面关闭按钮) + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[mail] completed (after retry)")
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="mail completed (after retry)",
                attempts=2,
            )

        log.warning("mail best-effort: {}", result2.error)
        # best-effort: 即使没成功也返回 SUCCESS(没邮件或没模板是常见情况)
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.SUCCESS,
            message="mail best-effort: " + str(result2.error),
            attempts=2,
        )

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(
            adb, project_root, templates_root, log,
            ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT,
        )
        nav = runner.make_navigator()
        pipe = _build_mail_pipeline(nav)
        return runner.run(pipe, max_total_iterations=20, max_idle_iterations=4)