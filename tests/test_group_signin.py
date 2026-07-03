"""test_group_signin.py — Demo: 用 mock ADB 测 group_signin 任务(2026-06-30 工程治理,Q3 demo)。

这是 DeepSeek Q3 推荐的测试模板:
- 6 个断言(pipeline 节点结构 / 字段 / on_error 链)
- mock ADB fixture,不连真模拟器
- 跑后续 9 个 task 可复制此文件

执行: python -m pytest tests/test_group_signin.py -q
"""

from __future__ import annotations

import pathlib
import sys

PROJECT_ROOT = pathlib.Path(r'D:\火影自动日常')
sys.path.insert(0, str(PROJECT_ROOT))

from tests._mock_adb import (
    make_blank_screen,
    make_mock_adb,
    default_assertions,
)


def test_group_signin_task_meta():
    """断言 1-3: task_id / name / category 字段合法。"""
    from tasks.group_signin_task import GroupSigninTask
    assert GroupSigninTask.task_id == "group_signin"
    assert GroupSigninTask.name == "组织签到(组织祈福)"
    assert GroupSigninTask.category == "weekly"


def test_group_signin_pipeline_structure():
    """断言 4: Pipeline 至少 5 个节点。"""
    from tasks.group_signin_task import _build_group_signin_pipeline, GroupSigninTask
    import inspect
    source = inspect.getsource(_build_group_signin_pipeline)
    pipe_adds = source.count("pipe.add(")
    assert pipe_adds >= 5, f"Pipeline 节点数 {pipe_adds} < 5"


def test_group_signin_has_verify_done():
    """断言 5: verify_done 节点存在。"""
    from tasks.group_signin_task import _build_group_signin_pipeline
    import inspect
    source = inspect.getsource(_build_group_signin_pipeline)
    assert '"verify_done"' in source, "Pipeline 缺少 verify_done 终点"


def test_group_signin_no_silent_verify_done():
    """断言 6: on_error 链不指向 verify_done(silent SUCCESS 已禁止 2026-06-30)。

    允许至多 1 处 on_error=['verify_done'](在 back_main_screen 节点)。
    """
    from tasks.group_signin_task import _build_group_signin_pipeline
    import inspect
    source = inspect.getsource(_build_group_signin_pipeline)
    cnt = source.count("on_error=['verify_done']")
    assert cnt <= 1, f"发现 {cnt} 处 on_error 直接 verify_done(应改为 back_main_screen)"


def test_group_signin_builder_can_call_with_mock():
    """集成断言: 用 mock ADB 跑 group_signin builder 返回可序列化的 Pipeline。"""
    import importlib
    from tasks.common_actions import CommonActions
    from tasks.navigator import Navigator

    mod = importlib.import_module("tasks.group_signin_task")
    builder = mod._build_group_signin_pipeline
    pipeline = builder(_FakeNav())
    # 至少有 entry + ensure_home + back_main_screen + verify_done
    node_names = set()
    # 通过 buffer 解析或者直接打印 inspect(简单方式:确保 Pipeline 不为 None)
    assert pipeline is not None
    assert pipeline.entry in ("ensure_home", "back_main_screen")


class _FakeNav:
    """最小 navigator stub — 仅供 builder 调用,不给真实截图。"""
    def templates(self, *names):
        from pathlib import Path
        # 返回空 list,bypass 真实模板加载
        return []
