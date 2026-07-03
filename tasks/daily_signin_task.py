"""tasks.daily_signin_task — 每日签到任务(2026-07-01 改写)。

A 计划(2026-06-30 23:00~23:19,30 张 `D:\\tmp\\A*_thumb.png` 截图)结论:
    游戏里的"每日签到"实际机制 = **活动页 → 左侧菜单下滑 → 每月签到 tab → 签到**,
    不是奖励中心里的"每日签到"任务卡(`check_not_in_daily_award.png` 在游戏里不是真正的每日签到入口)。

改写决策(2026-07-01):
    1. 委托 MonthlySigninTask 复用 8 节点 pipeline + monthly 路径 — 代码一致
    2. 保留 `task_id="daily_signin"` / `name="每日签到"` / `category="daily"`
       兼容 `main.py:876/1021` 注册 + 整套测试契约(`test_daily_signin_task.py` / phase[3-6]_pipeline 等)
    3. pre_check 保留 daily 独有策略(**不强制** `ensure_state(HOME)`,避免系统 BACK
       触发退出弹窗 — P0-FIX-2026-06-29) — 与 MonthlySigninTask 的强制 HOME 策略不同
    4. run() 保留 daily 独有策略:**best-effort SUCCESS**(掩盖失败) — 与 MonthlySigninTask
       的 FAIL 策略不同(daily 历史决策)
    5. recover / enter / verify 行为一致(继承 MonthlySigninTask)

正确路径(1920x1080 真机已验证):
    主页 → 右下"忍界指引"(1580, 940)
        → 活动页(活动卷轴 → headhunt.png @ tap 1222, 54)
        → 左侧菜单下滑 (80, 600)→(80, 300) max_hit=10
        → tap "每月签到" tab(**注意**:(95, 510) 才安全,(95, 360-450) 落入"送羁绊之券" hitbox)
        → 点 sign.png (1189, 577)
        → 验证 monthly_sign_done.png
        → 回主页

依赖: tasks.monthly_signin_task(继承 MonthlySigninTask)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from tasks.monthly_signin_task import (
    MonthlySigninTask,
    _build_monthly_signin_pipeline as _build_daily_signin_pipeline,
)
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
)

if TYPE_CHECKING:
    from core.base_task import ExecutionContext, TaskResult

__all__ = ["DailySigninTask"]


class DailySigninTask(MonthlySigninTask):
    """每日签到任务。

    2026-07-01 改写: 游戏里的"每日签到"实际机制是活动页 → 左侧菜单 → 每月签到 tab,
    委托 MonthlySigninTask 复用其 8 节点 pipeline。
    保留 task_id/name/category 以兼容 main.py 注册和测试契约。
    """

    # ===== 与 MonthlySigninTask 不同的接口 =====
    task_id = "daily_signin"
    name = "每日签到"
    category = "daily"

    # ===== pre_check:daily 独有策略(P0-FIX-2026-06-29)=====
    # 不强制 ensure_state(HOME) — 内部会调 BACK,触发"是否退出游戏"弹窗。
    # 与 MonthlySigninTask 的强制 ensure_state(HOME) 策略不同(daily 历史决策)。
    def pre_check(self, ctx: "ExecutionContext") -> bool:
        """仅检查 common_actions 不为 None,不强制回主页。"""
        return ctx.common_actions is not None

    # ===== run:显式 override 以满足 P1-ARCH-01 =====
    # `DailySigninTask.run.__qualname__ == "DailySigninTask.run"`
    # daily 独有 best-effort SUCCESS 策略(掩盖失败) — 与 MonthlySigninTask 的 FAIL 策略不同。
    def run(self, ctx: "ExecutionContext") -> "TaskResult":
        log = ctx.bind_logger(self.task_id)

        if ctx.common_actions is None:
            from core.base_task import TaskResult, TaskStatus
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
            log.success("[daily_signin] completed")
            from core.base_task import TaskResult, TaskStatus
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="daily_signin completed",
                attempts=1,
            )

        # 失败 → recover (用界面 X 按钮) + 重试
        log.warning("first attempt failed: {}; recover + retry", result.error)
        self.recover(ctx)
        time.sleep(1)

        result2 = self._run_pipeline(adb, project_root, templates_root, log)
        if result2.success:
            log.success("[daily_signin] completed (after retry)")
            from core.base_task import TaskResult, TaskStatus
            return TaskResult(
                task_id=self.task_id,
                status=TaskStatus.SUCCESS,
                message="daily_signin completed (after retry)",
                attempts=2,
            )

        # best-effort(daily 独有策略:接受降级成功)
        # P0 修复(2026-07-02): 用 BEST_EFFORT 而非 SUCCESS 避免掩盖故障
        log.warning("daily_signin best-effort: {}", result2.error)
        from core.base_task import TaskResult, TaskStatus
        return TaskResult(
            task_id=self.task_id,
            status=TaskStatus.BEST_EFFORT,
            message="daily_signin best-effort: " + str(result2.error),
            attempts=2,
        )
