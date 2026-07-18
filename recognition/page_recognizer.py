"""recognizer.page_recognizer — **[页面识别入口]** 遍历 GameState 模板。

职责:
    给定一张截图,遍历每个 GameState 对应的模板目录,取最佳匹配,
    把最佳匹配的 GameState + confidence + 模板来源打包成 ``RecognitionResult`` 返回。

⚠️ 模块辨识警告(2026-06-30 工程治理):
    本模块与同级目录 ``recognition/`` 和 ``recognizer/`` 命名近似但语义不同:
        - ``recognition.template_matcher``:**单图 → 单模板匹配**(ROI 区域,Node)
        - ``recognizer.page_recognizer`` (本模块):**单图 → 多个 GameState 模板循环**(页面级)
    调用者请明确选哪个模块,不要 import 错了:
        状态识别/页面级用 ``recognizer.page_recognizer``(本模块,整体页面级)。
        任务/task 节点级用 ``recognition.template_matcher``(ROI 区域级)。
    未来改名计划(Phase 10): ``recognizer/`` → ``page_detector/``。

    例如:
        resources/templates/HOME/main_hall_button.png
        resources/templates/POPUP/announcement_close.png
        resources/templates/LOADING/loading_icon.png

    Phase 2 demo 阶段目录是空的(``.gitkeep`` 占位),detect_state 会返回
    ``RecognitionResult(state=UNKNOWN, confidence=0.0, method="fallback:empty_templates")``,
    不抛错。这是符合验收的"正常退出"语义。

公开 API:
    PageRecognizer
        .detect_state(screen) -> RecognitionResult
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from recognition.template_matcher import MatchResult, TemplateMatcher
from recognition.types import RecognitionResult
from state_machine.game_state import GameState

__all__ = ["PageRecognizer"]


class PageRecognizer:
    """基于多模板投票的页面识别器。

    遍历所有 GameState 的模板目录,每个 state 内部取该目录下所有模板中
    置信度最高的那一个;最后在所有 state 的「最高分」中再选一次最佳。
    """

    def __init__(
        self,
        templates_root: Path,
        matcher: TemplateMatcher | None = None,
        threshold: float | None = None,
    ) -> None:
        """初始化识别器。

        Args:
            templates_root: 模板根目录(包含 ``<state>/`` 子目录)。
            matcher: 可选 TemplateMatcher;None 时新建一个。
            threshold: 可选单次阈值覆盖;None 用 matcher 默认。
        """
        self._root = Path(templates_root).resolve()
        self._matcher = matcher or TemplateMatcher()
        self._threshold = threshold
        # P6-REAL-02: 用 set 记录已经 warning 过的「空模板」state,防止
        # detect_state 每次调用都重复刷 warning,污染日志。
        self._warned_empty_states: set[str] = set()
        # P6-REAL-02: 记录「加载失败」的模板文件,同样防止 silent skip 反复出现。
        self._warned_failed_templates: set[str] = set()
        logger.bind(component="recognizer").debug(
            "PageRecognizer initialized: templates_root={}, threshold={}",
            self._root,
            threshold if threshold is not None else "<matcher default>",
        )

    # ----- public --------------------------------------------------------

    def detect_state(self, screen: Any) -> RecognitionResult:
        """在 ``screen`` 上识别当前页面。

        Args:
            screen: BGR uint8 截图,可以是 ``numpy.ndarray`` 或 None。

        Returns:
            ``RecognitionResult``:
                - 全部 GameState 都无匹配 → ``state=UNKNOWN, confidence=0.0,
                  method="fallback:no_match"`` (或 "fallback:empty_templates" 当所有目录都空)
                - 至少一个 state 命中 → 最佳 state 的 ``RecognitionResult``,
                  method 形如 ``"template_match:HOME:main_hall_button"``。
        """
        valid: list[tuple[GameState, MatchResult]] = []
        empty_dirs = 0
        for state in GameState:
            if state == GameState.UNKNOWN:
                # UNKNOWN 是 fallback,不参与模板匹配
                continue
            state_dir = self._root / state.value
            if not state_dir.exists():
                # P6-REAL-02: 每个空 state 只 warning 一次,后续降到 debug,避免日志污染
                if state.value not in self._warned_empty_states:
                    logger.bind(component="recognizer").warning(
                        "templates dir for GameState={} does not exist: {}; "
                        "this state will never match. Hint: mkdir -p {} and put PNG/JPG templates inside.",
                        state.value,
                        state_dir,
                        state_dir,
                    )
                    self._warned_empty_states.add(state.value)
                empty_dirs += 1
                continue
            if not state_dir.is_dir():
                if state.value not in self._warned_empty_states:
                    logger.bind(component="recognizer").warning(
                        "templates path for GameState={} is not a directory: {}; skipping",
                        state.value,
                        state_dir,
                    )
                    self._warned_empty_states.add(state.value)
                empty_dirs += 1
                continue
            if not any(state_dir.iterdir()):
                if state.value not in self._warned_empty_states:
                    logger.bind(component="recognizer").warning(
                        "templates dir for GameState={} is empty: {}; "
                        "this state will never match. Hint: place PNG/JPG templates inside.",
                        state.value,
                        state_dir,
                    )
                    self._warned_empty_states.add(state.value)
                empty_dirs += 1
                continue
            # state_dir 非空,清掉它的 warning 标记(用户可能中途放入模板)
            self._warned_empty_states.discard(state.value)
            match = self._matcher.match(state_dir, screen, threshold=self._threshold)
            if match is not None:
                valid.append((state, match))

        if not valid:
            total_dirs = sum(1 for s in GameState if s != GameState.UNKNOWN)
            if empty_dirs == total_dirs:
                method = "fallback:empty_templates"
                msg = "all template directories are empty"
            else:
                method = "fallback:no_match"
                msg = "no template matched above threshold"
            logger.bind(component="recognizer").info("detect_state: UNKNOWN ({})", msg)
            return RecognitionResult(
                state=GameState.UNKNOWN,
                confidence=0.0,
                method=method,
            )

        # 在所有 state 的「最佳匹配」中,取 confidence 最高者
        winner_state, winner_match = max(valid, key=lambda x: x[1].confidence)
        method = f"template_match:{winner_state.value}:{winner_match.template_name}"
        logger.bind(component="recognizer").info(
            "detect_state: {} (confidence={:.4f}, method={})",
            winner_state.value,
            winner_match.confidence,
            method,
        )
        return RecognitionResult(
            state=winner_state,
            confidence=winner_match.confidence,
            method=method,
        )
