"""tasks.pipeline_runner — 业务 Task 共享的 Navigator 运行封装(Phase 6 业务扩展增量)。

设计目标:
    抽取 ``DailySigninTask._run_pipeline`` 中的可复用逻辑,让新增的
    MailTask / LivenessTask / GroupSigninTask 不用各自复制一份:

        1. 构造 Navigator(adb + project_root + templates_root)
        2. 自动设置分辨率缩放(adb.screenshot → set_resolution_scale)
        3. 跑 Pipeline(允许调用方传入 max_total_iterations / max_idle_iterations)
        4. 返回结构化结果(成功 / 失败原因 / history)

    **不重写 Navigator**,**不重写 Pipeline**,只复用现有 API。

    与 ``common_actions.py`` 的区别:
        - ``common_actions`` 是「跨任务共享动作」(go_home / ensure_state / close_popup)
        - 本模块是「跨任务共享运行容器」(run pipeline + 分辨率自适应 + 重试一次)

    允许使用:
        - Navigator.set_resolution_scale / run (现有 API)
        - tasks.navigator 的所有公开类 (Node / Pipeline / Action)

    禁止使用:
        - 不动 Navigator 的状态机逻辑
        - 不增加新异常类型
        - 不做任务特定的硬编码

新增于 Phase 6 业务扩展阶段,代码量控制在 ~60 行。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from tasks.navigator import Navigator, Pipeline

if TYPE_CHECKING:
    from device.adb_client import ADBClient

__all__ = ["PipelineRunner", "DEFAULT_REF_WIDTH", "DEFAULT_REF_HEIGHT"]


# 默认参考分辨率(narutomobile 平板推荐)
DEFAULT_REF_WIDTH = 1920
DEFAULT_REF_HEIGHT = 1080


class PipelineRunner:
    """Navigator + Pipeline + 分辨率自适应的统一运行器。

    用法(典型):
        runner = PipelineRunner(adb, project_root, log)
        result = runner.run(pipe, max_total_iterations=30, max_idle_iterations=4)
        if result.success:
            ...

    字段:
        adb: ADBClient 实例(注入)
        project_root: 项目根目录(Path)
        templates_root: 模板根目录(默认 project_root/resources/templates/actions)
        log: loguru 绑定 logger
        ref_width / ref_height: 参考分辨率(默认 1920x1080)

    设计:
        - 不持有任何状态,每次 run() 都是独立的
        - 分辨率自适应只做一次(screenshot → set_resolution_scale),
          失败时降级到 1.0(后续走 ROI 原值)
        - 单次运行;重试由调用方(BusinessTask.run)决定
    """

    def __init__(
        self,
        adb: "ADBClient",
        project_root: Path,
        templates_root: Path,
        log,
        *,
        ref_width: int = DEFAULT_REF_WIDTH,
        ref_height: int = DEFAULT_REF_HEIGHT,
    ) -> None:
        self._adb = adb
        self._project_root = Path(project_root).resolve()
        self._templates_root = Path(templates_root).resolve()
        self._log = log
        self._ref_width = ref_width
        self._ref_height = ref_height

    @property
    def ref_width(self) -> int:
        return self._ref_width

    @property
    def ref_height(self) -> int:
        return self._ref_height

    def make_navigator(self) -> Navigator:
        """构造 Navigator(给调用方用,例如 Pipeline 构造需要 ``nav.templates``)。"""
        return Navigator(
            self._adb,
            self._project_root,
            templates_root=self._templates_root,
            ref_width=self._ref_width,
            ref_height=self._ref_height,
        )

    def run(
        self,
        pipe: Pipeline,
        *,
        max_total_iterations: int = 30,
        max_idle_iterations: int = 4,
    ):
        """跑一次 Pipeline(带分辨率自适应)。

        Args:
            pipe: 已构造好的 Pipeline(调用方负责 add 节点)。
            max_total_iterations: 同 Navigator.run。
            max_idle_iterations: 同 Navigator.run。

        Returns:
            Navigator.RunResult(success, last_node, total_iterations, error, history)。
            **不抛异常** — Navigator 内部已捕获,失败时 result.success=False。
        """
        nav = self.make_navigator()

        # 分辨率自适应(失败不阻塞,用 1.0 原值)
        try:
            screen = self._adb.screenshot()
            if screen.success and screen.payload is not None:
                h, w = screen.payload.shape[:2]
                nav.set_resolution_scale(self._ref_width, self._ref_height, w, h)
                # P3 修复(2026-07-02): 改用公共属性 scale_x / scale_y
                # 之前直接读 ``nav._scale_x`` 是私有属性访问,违反封装。
                self._log.info(
                    "Navigator: ref {}x{} -> screen {}x{} (scale={:.3f} x {:.3f})",
                    self._ref_width, self._ref_height, w, h,
                    nav.scale_x, nav.scale_y,
                )
        except Exception as exc:
            self._log.warning("resolution scale detection failed: {}", exc)

        self._log.info("running pipeline ({} nodes)", len(pipe))
        result = nav.run(
            pipe,
            max_total_iterations=max_total_iterations,
            max_idle_iterations=max_idle_iterations,
        )

        self._log.info(
            "pipeline finished: success={} last={} iters={} history={}",
            result.success, result.last_node, result.total_iterations,
            "->".join(result.history[-5:]),
        )
        return result


# ============================================================
# 模板路径工具 — 让 Task 不用自己拼路径
# ============================================================


def actions_templates_root(project_root: Path) -> Path:
    """返回 ``resources/templates/actions`` 绝对路径。"""
    return (Path(project_root) / "resources" / "templates" / "actions").resolve()


def action_subdir(project_root: Path, subdir: str) -> Path:
    """返回 ``resources/templates/actions/<subdir>`` 绝对路径(用于新建子目录)。"""
    return actions_templates_root(project_root) / subdir