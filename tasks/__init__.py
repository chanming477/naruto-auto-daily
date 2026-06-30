"""tasks package · Phase 3 任务系统。

包含:
    common_actions        — 跨任务共享导航/等待/弹窗处理(go_home / close_popup /
                            wait_loading / ensure_state)
    task_engine           — Scheduler 业务包装层(register / unregister / run_task /
                            run_all / stop),严格轻量,不重写调度逻辑
    daily_signin_task     — 第一个真实任务骨架(BaseTask 子类,enter/execute/verify
                            mock,recover 真做)
    mail_task             — Phase 6 真实接入的邮件领取任务
    liveness_task         — Phase 6 真实接入的活跃度宝箱任务
    group_signin_task     — Phase 6 真实接入的组织签到任务
    weekly_signin_task    — Phase 7 周签到任务
    activity_task         — Phase 7 活动(一乐外卖)任务
    recruit_task          — Phase 7+ 按 docs/operation_flows.md 补全的招募任务

依赖方向(严格自上而下):
    tasks → core / device / recognition / recognizer / state / state_machine

禁止:
    - 新建 scheduler / executor / 第二个 state_machine
    - 在任务内部复制 CommonActions 已有的导航逻辑
    - 修改 core/* / device/* / recognition/* / recognizer/* / state/* /
      state_machine/* 的核心逻辑(只允许增量加方法/字段/docstring)
"""

__all__ = [
    "common_actions",
    "task_engine",
    "daily_signin_task",
    "mail_task",
    "liveness_task",
    "group_signin_task",
    "weekly_signin_task",
    "activity_task",
    "recruit_task",
]
__version__ = "0.3.2"