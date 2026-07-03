"""recognition.ocr_matcher — **[本项目 OCR 节点]** onnxruntime 文字识别封装。

设计来源:
    narutomobile ``merged.json`` 6 个 OCR 节点(``ninja_guide_find_funtion_entry`` 等)
    走 Maafw 内置 OCR,模型是 ``det.onnx`` (DBNet 文字检测) + ``rec.onnx`` (CRNN 文字识别)
    + ``keys.txt`` (字符表)。

    我们不依赖 narutomobile,把模型从 ``resources/narutomobile/model/ocr/`` 拷到
    ``resources/ocr_models/`` 下,本模块用 onnxruntime 加载,自己实现 pre/post process。

公开 API:
    OCRMatcher
        .match(expected, screen, *, roi=None, threshold=0.3) -> MatchResult | None
        .match_all(expected, screen, *, roi=None, threshold=0.3, max_results=10) -> list[MatchResult]

依赖:
    - onnxruntime(纯 Python pip install,推理在 CPU/GPU 都行)
    - 模型在 ``D:\\火影自动日常\\resources\\ocr_models\\``(首次跑自动加载)

与 ``recognition.template_matcher.TemplateMatcher`` 风格对齐:
    - 都返回 ``MatchResult``(x, y, w, h, confidence, template_name)
    - 同样的 ROI 规范化,同样的 match/match_all/exists 模式
    - 同样的 threshold 概念(OCR 用置信度 0~1)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

try:
    import onnxruntime as ort  # type: ignore

    _ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    ort = None  # type: ignore
    _ONNX_AVAILABLE = False

__all__ = ["OCRMatcher", "OCRConfig", "OCRMatchResult", "load_default_ocr_model_dir"]


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True)
class OCRMatchResult:
    """OCR 单个文字匹配的位置结果(对齐 ``recognition.template_matcher.MatchResult``)。

    Attributes:
        text: 识别出的文字。
        x: 命中区域左上角 x(相对 screen 原点,非 ROI 原点)。
        y: 命中区域左上角 y。
        width: 命中区域宽度。
        height: 命中区域高度。
        confidence: 识别置信度 [0.0, 1.0]。
    """

    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": round(self.confidence, 4),
            "center": self.center,
        }


# 兼容外部按 MatchResult 引用的场景(只暴露必需字段)
MatchResult = OCRMatchResult


# ============================================================
# Config
# ============================================================


@dataclass(frozen=True)
class OCRConfig:
    """OCR 配置。

    Attributes:
        model_dir: 模型目录,含 ``det.onnx`` / ``rec.onnx`` / ``keys.txt``。
        default_threshold: 默认匹配阈值,识别置信度 >= threshold 才算命中(0~1)。
        use_gpu: 是否尝试用 GPU(onnxruntime CUDA provider)。
    """

    model_dir: Path
    default_threshold: float = 0.3
    use_gpu: bool = False


def load_default_ocr_model_dir(project_root: Path | None = None) -> Path:
    """返回本项目默认 OCR 模型目录 ``{project_root}/resources/ocr_models``。

    Args:
        project_root: 项目根,None 时用 ``Path.cwd()``。
    """
    root = project_root or Path.cwd()
    return root / "resources" / "ocr_models"


# ============================================================
# Manager
# ============================================================


class OCRMatcher:
    """基于 onnxruntime(DBNet 检测 + CRNN 识别)的 OCR 节点。

    对齐 ``TemplateMatcher`` 的 API 风格:``match`` / ``match_all`` / ``exists``。
    截图需 BGR uint8 ndarray(与 TemplateMatcher 一致)。
    """

    def __init__(self, config: OCRConfig) -> None:
        if not _ONNX_AVAILABLE:
            raise RuntimeError("onnxruntime 未安装,先跑: pip install onnxruntime")
        if not config.model_dir.is_dir():
            raise FileNotFoundError(f"OCR model dir not found: {config.model_dir}")
        det_path = config.model_dir / "det.onnx"
        rec_path = config.model_dir / "rec.onnx"
        keys_path = config.model_dir / "keys.txt"
        for p in (det_path, rec_path, keys_path):
            if not p.exists():
                raise FileNotFoundError(f"OCR model file missing: {p}")

        self._config = config
        self._default_threshold = float(config.default_threshold)

        # 选择 ExecutionProvider
        providers = ["CPUExecutionProvider"]
        if config.use_gpu and "CUDAExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")

        self._det_sess = ort.InferenceSession(str(det_path), providers=providers)
        self._rec_sess = ort.InferenceSession(str(rec_path), providers=providers)
        self._keys = self._load_keys(keys_path)

        # 缓存输入 shape(用于 pre/post)
        self._det_input_name = self._det_sess.get_inputs()[0].name
        self._rec_input_name = self._rec_sess.get_inputs()[0].name

    # ----- public --------------------------------------------------------

    def match(
        self,
        expected: str | list[str] | tuple[str, ...],
        screen: np.ndarray | None,
        *,
        roi: Sequence[int] | None = None,
        threshold: float | None = None,
    ) -> OCRMatchResult | None:
        """在 ``screen`` 上找任一 expected 文字,返回最佳匹配。

        Args:
            expected: 期望文字(单 str 或多 alias 列表,任一命中即用)。
            screen: BGR 截图 (H, W, 3) uint8。
            roi: 可选 ROI ``(x, y, w, h)``,None 表示全图。
            threshold: 置信度阈值,None 用构造时配置的默认值。

        Returns:
            最佳 ``OCRMatchResult``,或 None 表示未匹配 / 截图非法。
        """
        if not self._validate_screen(screen):
            return None
        thr = self._resolve_threshold(threshold)
        expected_list = [expected] if isinstance(expected, str) else list(expected)

        all_results = self.match_all(expected_list, screen, roi=roi, threshold=thr, max_results=10)
        return all_results[0] if all_results else None

    def match_all(
        self,
        expected: str | list[str] | tuple[str, ...],
        screen: np.ndarray | None,
        *,
        roi: Sequence[int] | None = None,
        threshold: float | None = None,
        max_results: int = 10,
    ) -> list[OCRMatchResult]:
        """在 ``screen`` 上找所有 expected 文字(按置信度降序)。"""
        if not self._validate_screen(screen):
            return []
        thr = self._resolve_threshold(threshold)
        expected_list = [expected] if isinstance(expected, str) else list(expected)
        expected_set = {self._normalize_text(e) for e in expected_list}

        # 1. 限定 ROI
        roi_xywh = self._normalize_roi(screen, roi)
        rx, ry, rw, rh = roi_xywh
        roi_view = screen[ry : ry + rh, rx : rx + rw]

        # 2. 文字检测 → 文字框列表
        boxes = self._detect_text(roi_view)

        # 3. 对每个文字框做识别
        results: list[OCRMatchResult] = []
        for box_in_roi in boxes:
            x0, y0, x1, y1 = box_in_roi
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(rw, x1), min(rh, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            crop = roi_view[y0:y1, x0:x1]
            text, conf = self._recognize_text(crop)
            if not text or conf < thr:
                continue
            norm = self._normalize_text(text)
            if not self._matches_expected(norm, expected_set):
                continue
            results.append(
                OCRMatchResult(
                    text=text,
                    x=rx + int(x0),
                    y=ry + int(y0),
                    width=int(x1 - x0),
                    height=int(y1 - y0),
                    confidence=float(conf),
                )
            )
            if len(results) >= max_results:
                break

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def exists(
        self,
        expected: str | list[str] | tuple[str, ...],
        screen: np.ndarray | None,
        *,
        roi: Sequence[int] | None = None,
        threshold: float | None = None,
    ) -> bool:
        """``match()`` 的布尔包装。"""
        return self.match(expected, screen, roi=roi, threshold=threshold) is not None

    # ----- internals -----------------------------------------------------

    def _detect_text(self, img_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        """DBNet 文字检测,返回 ``[(x0, y0, x1, y1), ...]``(相对输入图像)。"""
        h, w = img_bgr.shape[:2]
        # 模型期望 4D float32 NCHW(归一化到 mean=0.485/0.456/0.406, std=0.229/0.224/0.225)
        # OpenCV 4.13 的 cv2.dnn.blobFromImage 不支持 std 参数,手动 normalize
        resized = cv2.resize(img_bgr, (320, 320))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (rgb - mean) / std
        blob = normalized.transpose(2, 0, 1)[np.newaxis, :, :, :]  # NCHW
        out = self._det_sess.run(None, {self._det_input_name: blob})[0]
        # out shape: (1, 1, H', W') 概率图
        prob = out[0, 0]
        prob = cv2.resize(prob, (w, h))

        # 二值化 + 找轮廓
        mask = (prob > 0.3).astype(np.uint8) * 255
        # 膨胀让文字区域更连贯
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.dilate(mask, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes: list[tuple[int, int, int, int]] = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 30:  # 太小的噪点跳过
                continue
            rect = cv2.boundingRect(cnt)  # (x, y, w, h)
            x, y, bw, bh = rect
            # 文字区域加一点 padding
            pad = 2
            boxes.append((max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)))
        return boxes

    def _recognize_text(self, crop_bgr: np.ndarray) -> tuple[str, float]:
        """CRNN 文字识别,返回 ``(text, avg_confidence)``。"""
        ch, cw = 32, 320  # 模型期望高度 32,宽度 320
        # 高度缩放到 32,宽度按比例缩放 + pad
        h, w = crop_bgr.shape[:2]
        if h == 0 or w == 0:
            return "", 0.0
        scale = ch / h
        new_w = max(1, int(round(w * scale)))
        resized = cv2.resize(crop_bgr, (new_w, ch))
        if new_w < cw:
            # 右侧 pad 到 320
            padded = np.full((ch, cw, 3), 0, dtype=np.uint8)
            padded[:, :new_w, :] = resized
            resized = padded
        elif new_w > cw:
            resized = cv2.resize(crop_bgr, (cw, ch))

        # OpenCV 4.13 不支持 std 参数,手动 normalize (mean=0.5, std=0.5)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        normalized = (rgb - 0.5) / 0.5
        blob = normalized.transpose(2, 0, 1)[np.newaxis, :, :, :]  # NCHW
        out = self._rec_sess.run(None, {self._rec_input_name: blob})[0]
        # out shape: (1, T, num_classes)  —  T 是时间步,num_classes = len(keys) + 1(blank)
        preds = out[0]
        argmax = preds.argmax(axis=-1)
        max_prob = preds.max(axis=-1)
        keys = self._keys

        # CTC decode: 合并重复 + 去 blank
        decoded: list[int] = []
        probs: list[float] = []
        last = -1
        for i, idx in enumerate(argmax.tolist()):
            if idx != last and 0 <= idx < len(keys):
                decoded.append(idx)
                probs.append(float(max_prob[i]))
            last = idx
        text = "".join(keys[k] for k in decoded)
        avg_conf = sum(probs) / len(probs) if probs else 0.0
        return text, avg_conf

    @staticmethod
    def _normalize_text(s: str) -> str:
        """去除空白,便于匹配 expected。"""
        return "".join(s.split())

    @staticmethod
    def _matches_expected(text: str, expected_set: set[str]) -> bool:
        """任一 expected 包含 text 或 text 包含 expected 即匹配(宽松匹配)。"""
        if text in expected_set:
            return True
        for e in expected_set:
            if e and (e in text or text in e):
                return True
        return False

    @staticmethod
    def _normalize_roi(
        screen: np.ndarray,
        roi: Sequence[int] | None,
    ) -> tuple[int, int, int, int]:
        """与 ``recognition.template_matcher._normalize_roi`` 行为一致。"""
        img_h, img_w = screen.shape[:2]
        full = (0, 0, int(img_w), int(img_h))
        if roi is None:
            return full
        x, y, w, h = (int(v) for v in roi)
        if w <= 0 or h <= 0:
            return full
        x0 = max(0, min(x, img_w))
        y0 = max(0, min(y, img_h))
        x1 = max(x0, min(x + w, img_w))
        y1 = max(y0, min(y + h, img_h))
        rw, rh = x1 - x0, y1 - y0
        if rw <= 0 or rh <= 0:
            return full
        return (x0, y0, rw, rh)

    @staticmethod
    def _validate_screen(screen: np.ndarray | None) -> bool:
        if screen is None or not isinstance(screen, np.ndarray):
            return False
        if screen.size == 0 or screen.ndim < 2:
            return False
        if screen.shape[0] < 1 or screen.shape[1] < 1:
            return False
        return True

    def _resolve_threshold(self, override: float | None) -> float:
        if override is None:
            return self._default_threshold
        v = float(override)
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"threshold must be in [0.0, 1.0], got {v}")
        return v

    @staticmethod
    def _load_keys(path: Path) -> list[str]:
        """加载 keys.txt,每行一个字符。narutomobile keys.txt 第一行可能是 'character' 头,跳过。"""
        keys: list[str] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                ch = line.rstrip("\n").rstrip("\r")
                if not ch or ch == "character":  # 跳过 PaddleOCR 风格的表头
                    continue
                keys.append(ch)
        return keys
