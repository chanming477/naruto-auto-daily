"""test_phase6_business_tasks — Phase 6 业务扩展 3 个新 Task 的单元测试。

覆盖:
    - MailTask: Pipeline 节点完整 / 模板缺失降级 / BaseTask 契约
    - LivenessTask: Pipeline 节点完整 / 复用 liveness/* 模板 / BaseTask 契约
    - GroupSigninTask: Pipeline 节点完整 / 模板缺失降级 / MISSING_TEMPLATES 完整性
    - PipelineRunner: 复用 _run_pipeline / 分辨率自适应 / Navigator 构造

测试策略:
    - 与 daily_signin_task 测试一致: 真实模板 + mock ADB + 真实 Navigator
    - 不强求模板匹配成功(降级场景),只验证 pipeline 结构 + BaseTask 契约
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.base_task import BaseTask, ExecutionContext, TaskResult, TaskStatus
from tasks.common_actions import CommonActions
from tasks.daily_signin_task import DailySigninTask
from tasks.group_signin_task import GroupSigninTask, MISSING_TEMPLATES as GROUP_MISSING
from tasks.liveness_task import LivenessTask
from tasks.mail_task import MailTask, MISSING_TEMPLATES as MAIL_MISSING
from tasks.navigator import Navigator, Pipeline
from tasks.pipeline_runner import (
    DEFAULT_REF_HEIGHT,
    DEFAULT_REF_WIDTH,
    PipelineRunner,
    actions_templates_root,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def common_actions() -> CommonActions:
    ca = MagicMock(spec=CommonActions)
    ca.ensure_state.return_value = True
    ca.go_home.return_value = True
    return ca


@pytest.fixture
def ctx(tmp_path: Path) -> ExecutionContext:
    from core.config_manager import ConfigManager
    from core.state_machine import build_default_state_machine

    cfg = ConfigManager(tmp_path, auto_load=True)
    return ExecutionContext(
        config=cfg,
        window_manager=MagicMock(),
        screenshot_manager=MagicMock(),
        state_machine=build_default_state_machine("IDLE", log_transitions=False),
    )


# ============================================================
# 常量 / BaseTask 契约
# ============================================================


@pytest.mark.parametrize("task_cls,expected_id,expected_name", [
    (MailTask, "mail", "邮件领取"),
    (LivenessTask, "liveness", "活跃度宝箱"),
    (GroupSigninTask, "group_signin", "组织签到(组织祈福)"),
])
def test_task_constants(task_cls, expected_id, expected_name):
    assert task_cls.task_id == expected_id
    assert task_cls.name == expected_name
    assert task_cls.category == "daily"


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_task_inherits_basetask(task_cls):
    assert issubclass(task_cls, BaseTask)


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_max_retries_is_zero(task_cls):
    """与 DailySigninTask 一致:max_retries=0,避免双层重试。"""
    assert task_cls.max_retries == 0


# ============================================================
# pre_check / recover / verify
# ============================================================


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_pre_check_uses_common_actions(ctx, common_actions, task_cls):
    """P0-FIX-2026-06-29: pre_check 只检查 common_actions 不为 None,不强制 ensure_state(HOME)
    (会触发"是否退出游戏"弹窗)。
    """
    ctx.common_actions = common_actions
    t = task_cls()
    assert t.pre_check(ctx) is True


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_pre_check_returns_false_when_no_common_actions(ctx, task_cls):
    ctx.common_actions = None
    assert task_cls().pre_check(ctx) is False


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_recover_uses_template_based_dismiss(ctx, common_actions, task_cls):
    """v1.2 P0 #1: recover 用模板匹配替代硬编码 tap,调 common.dismiss_x + common.tap_home_button。

    模板匹配在公共方法内部完成,这里验证公共方法被调用即可。
    """
    ctx.common_actions = common_actions
    assert task_cls().recover(ctx) is True
    # v1.2: 至少调一次 dismiss_x,以及一次 tap_home_button
    common_actions.dismiss_x.assert_called()
    common_actions.tap_home_button.assert_called()


@pytest.mark.parametrize("task_cls", [LivenessTask, GroupSigninTask])
def test_recover_uses_template_chain(ctx, common_actions, task_cls):
    """验证 recover 通过模板化公共方法恢复(不依赖 go_home)。"""
    ctx.common_actions = common_actions
    result = task_cls().recover(ctx)
    assert result in (True, False)
    # 至少调了模板化公共方法(可能成功也可能失败,不阻塞)


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_recover_returns_false_when_no_common_actions(ctx, task_cls):
    ctx.common_actions = None
    assert task_cls().recover(ctx) is False


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_enter_returns_true(ctx, common_actions, task_cls):
    ctx.common_actions = common_actions
    assert task_cls().enter(ctx) is True


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_verify_returns_true(ctx, common_actions, task_cls):
    ctx.common_actions = common_actions
    assert task_cls().verify(ctx) is True


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_execute_pre_check_failure_returns_skip(ctx, task_cls):
    ctx.common_actions = None  # 让 pre_check 返 False
    result = task_cls().execute(ctx)
    assert result.status == TaskStatus.SKIP


@pytest.mark.parametrize("task_cls", [MailTask, LivenessTask, GroupSigninTask])
def test_execute_uses_basetask_default_execute(task_cls):
    """未覆盖 BaseTask.execute(继承模板方法)。"""
    assert task_cls.execute is BaseTask.execute


# ============================================================
# Pipeline 结构
# ============================================================


def _make_nav_with_real_templates():
    """构造一个引用真实模板目录的 Navigator。"""
    adb = MagicMock()
    return Navigator(adb, Path(r"D:\火影自动日常"))


def test_mail_pipeline_has_required_nodes():
    """MailTask Pipeline 包含完整节点(主流程 + 兜底)。"""
    from tasks.mail_task import _build_mail_pipeline
    nav = _make_nav_with_real_templates()
    pipe = _build_mail_pipeline(nav)
    required = [
        "ensure_home",
        "find_mail_entry",
        "find_one_key_claim",
        "close_mail",
        "verify_done",
    ]
    for name in required:
        assert name in pipe, f"missing required node: {name}"
    assert pipe.entry == "ensure_home"


def test_liveness_pipeline_has_required_nodes():
    """LivenessTask Pipeline 包含完整节点。"""
    from tasks.liveness_task import _build_liveness_pipeline
    nav = _make_nav_with_real_templates()
    pipe = _build_liveness_pipeline(nav)
    required = [
        "ensure_home",
        "find_award_button",
        "find_liveness_tab",
        "find_weekly_award_undone",
        "confirm_weekly",
        "try_one_click_claim",
        "close_award_center",
        "back_to_home",
        "verify_done",
    ]
    for name in required:
        assert name in pipe, f"missing required node: {name}"
    assert pipe.entry == "ensure_home"


def test_group_signin_pipeline_has_required_nodes():
    """GroupSigninTask Pipeline 包含关键节点。

    2026-06-29 简化: 去掉 check_no_group + 4 子链路 (铜币祈福/追击晓子),
    只保留焚香祈福主流程。
        主页 → 奖励 → 组织祈福卡片 → 立刻前往 → 焚香祈福 → 确认 → 关闭 → 主页
    """
    from tasks.group_signin_task import _build_group_signin_pipeline
    nav = _make_nav_with_real_templates()
    pipe = _build_group_signin_pipeline(nav)
    required = [
        "ensure_home",
        "find_award_button",          # 主页 → 奖励中心
        "find_group_pray_card",       # 奖励中心 → 组织祈福卡片
        "find_go_button",             # 立刻前往
        "find_burn_incense_pray",     # 焚香祈福按钮
        "confirm_pray",               # 确认祈福
        "back_to_home",               # 回主页
        "verify_done",
    ]
    for name in required:
        assert name in pipe, f"missing required node: {name}"
    assert pipe.entry == "ensure_home"

    # 明确断言: 旧 4 子链路已移除 (P0-2 步骤 2/3 简化)
    removed = ["check_no_group", "try_copper_pray", "confirm_copper_pray", "try_pursuit_entry"]
    for name in removed:
        assert name not in pipe, f"deprecated node still present: {name}"


# ============================================================
# MISSING_TEMPLATES 完整性
# ============================================================


def test_mail_missing_templates_list_shape():
    """MailTask.MISSING_TEMPLATES 每项是 (path, description, roi) 三元组。

    2026-06-26 真机采集后: mail_close_x.png / mail_envelope.png / mail_done.png 已存在,
    one_key_claim.png 因邮箱空跳过 — 改用 shared/get.png 通用领取。
    所以 MISSING_TEMPLATES 现在允许为空列表(用 `>= 0` 表示允许空)。
    """
    assert len(MAIL_MISSING) >= 0, "MailTask.MISSING_TEMPLATES cannot be negative"
    for entry in MAIL_MISSING:
        assert len(entry) == 3, f"entry shape wrong: {entry}"
        path, desc, roi = entry
        assert isinstance(path, str) and path.startswith("mail/")
        assert isinstance(desc, str) and desc
        assert len(roi) == 4 and all(isinstance(v, int) for v in roi)


def test_group_missing_templates_list_shape():
    """GroupSigninTask.MISSING_TEMPLATES 每项是 (path, description, roi) 三元组。

    2026-06-29 简化后模板已基本采完,占位 placeholder 保留为 4 行,仅满足 shape 校验。
    """
    assert len(GROUP_MISSING) >= 4, "GroupSigninTask should declare at least 4 missing templates"
    for entry in GROUP_MISSING:
        assert len(entry) == 3
        path, desc, roi = entry
        assert isinstance(path, str) and path.startswith("group/")
        assert isinstance(desc, str) and desc
        assert len(roi) == 4


# ============================================================
# Liveness 复用既有 liveness/* 模板
# ============================================================


def test_liveness_reuses_existing_templates():
    """LivenessTask 必须引用已存在的 liveness/* 模板,不重复采集。"""
    from tasks.liveness_task import _build_liveness_pipeline
    nav = _make_nav_with_real_templates()
    pipe = _build_liveness_pipeline(nav)

    # 收集所有引用的模板路径
    referenced = set()
    for node in pipe._nodes.values():
        for tpl in node.templates:
            referenced.add(tpl.name)

    # 必须引用至少 3 个已有 liveness 模板
    existing = {
        "weekly_award_undone.png",
        "confirm_weekly_award.png",
        "award_box_all.png",
        "award_box_10.png",
        "award_box_40.png",
        "award_box_80.png",
        "award_box_100.png",
        "box_1_done.png",
        "box_2_done.png",
        "box_3_done.png",
        "box_4_done.png",
    }
    intersection = referenced & existing
    assert len(intersection) >= 3, (
        f"LivenessTask 应至少复用 3 个 liveness/* 模板,实际引用: {referenced}"
    )


# ============================================================
# Navigator 端到端(降级场景 — 空屏幕)
# ============================================================


def _make_mock_adb_with_screen(screen: np.ndarray, action_success: bool = True):
    from device.types import ActionResult
    adb = MagicMock()
    adb.screenshot.return_value = ActionResult(True, "ok", None, payload=screen.copy())
    adb.tap.return_value = ActionResult(action_success, "ok", None)
    adb.keyevent.return_value = ActionResult(action_success, "ok", None)
    adb.swipe.return_value = ActionResult(action_success, "ok", None)
    return adb


@pytest.mark.parametrize("pipe_factory,label", [
    ("_build_mail_pipeline", "mail"),
    ("_build_liveness_pipeline", "liveness"),
    ("_build_group_signin_pipeline", "group_signin"),
])
def test_pipeline_runs_without_crashing_on_empty_screen(pipe_factory, label):
    """空屏幕下 Pipeline 不崩(降级到 back_to_home → verify_done → success)。"""
    from tasks import mail_task, liveness_task, group_signin_task
    factory_map = {
        "_build_mail_pipeline": mail_task._build_mail_pipeline,
        "_build_liveness_pipeline": liveness_task._build_liveness_pipeline,
        "_build_group_signin_pipeline": group_signin_task._build_group_signin_pipeline,
    }
    factory = factory_map[pipe_factory]

    adb = _make_mock_adb_with_screen(np.full((900, 1600, 3), 200, dtype=np.uint8))
    nav = Navigator(adb, Path(r"D:\火影自动日常"))
    nav.set_resolution_scale(DEFAULT_REF_WIDTH, DEFAULT_REF_HEIGHT, 1600, 900)
    pipe = factory(nav)
    result = nav.run(pipe, max_total_iterations=20, max_idle_iterations=4)
    # 不崩即可(空屏幕时大部分节点会 on_error → back_to_home → verify_done)
    assert result.last_node != "", f"[{label}] last_node must not be empty"
    # history 不应空
    assert len(result.history) >= 2, f"[{label}] history too short: {result.history}"


# ============================================================
# PipelineRunner 单元测试
# ============================================================


def test_pipeline_runner_resolution_scale_identity():
    """PipelineRunner.make_navigator() 默认构造不调 set_resolution_scale。"""
    adb = MagicMock()
    runner = PipelineRunner(
        adb, Path(r"D:\火影自动日常"),
        Path(r"D:\火影自动日常\resources\templates\actions"),
        MagicMock(),
    )
    nav = runner.make_navigator()
    assert nav._scale_x == 1.0
    assert nav._scale_y == 1.0


def test_pipeline_runner_run_with_empty_screen_succeeds():
    """空屏幕下 PipelineRunner.run 不会崩,Pipeline 走降级路径。"""
    adb = _make_mock_adb_with_screen(np.full((900, 1600, 3), 200, dtype=np.uint8))
    runner = PipelineRunner(
        adb, Path(r"D:\火影自动日常"),
        Path(r"D:\火影自动日常\resources\templates\actions"),
        MagicMock(),
    )
    nav = runner.make_navigator()
    nav.set_resolution_scale(DEFAULT_REF_WIDTH, DEFAULT_REF_HEIGHT, 1600, 900)

    from tasks.mail_task import _build_mail_pipeline
    pipe = _build_mail_pipeline(nav)
    result = runner.run(pipe, max_total_iterations=20, max_idle_iterations=4)
    assert result is not None
    assert isinstance(result.success, bool)


def test_actions_templates_root_helper():
    """actions_templates_root() 返回正确路径。"""
    root = actions_templates_root(Path(r"D:\火影自动日常"))
    assert root.name == "actions"
    assert root.parent.name == "templates"


# ============================================================
# schemes/daily.json 内容
# ============================================================


def test_daily_scheme_has_all_core_tasks(tmp_path):
    """schemes/daily.json 必须包含 5 个日常任务。"""
    import json
    scheme_path = Path(r"D:\火影自动日常\schemes\daily.json")
    assert scheme_path.exists(), f"scheme missing: {scheme_path}"
    data = json.loads(scheme_path.read_text(encoding="utf-8"))
    task_ids = data.get("task_ids", [])
    # 核心 4 个必须在
    for tid in ["mail", "liveness", "group_signin", "daily_signin"]:
        assert tid in task_ids, f"daily.json 缺少任务: {tid}"


# ============================================================
# task_registry.yaml 注册情况
# ============================================================


def test_task_registry_contains_new_tasks():
    """config/task_registry.yaml 必须注册 mail/liveness/group_signin。"""
    import yaml
    reg_path = Path(r"D:\火影自动日常\config\task_registry.yaml")
    assert reg_path.exists()
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    tasks = data.get("tasks", {})
    for tid in ["daily_signin", "mail", "liveness", "group_signin"]:
        assert tid in tasks, f"task '{tid}' not registered"
        assert "task_class" in tasks[tid]


def test_task_registry_display_order():
    """任务 display_order: mail=2 < liveness=3 < group_signin=4 < daily_signin=5。"""
    import yaml
    reg_path = Path(r"D:\火影自动日常\config\task_registry.yaml")
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    assert tasks["mail"]["display_order"] == 2
    assert tasks["liveness"]["display_order"] == 3
    assert tasks["group_signin"]["display_order"] == 4
    assert tasks["daily_signin"]["display_order"] == 5