"""recognition package · Phase 2 图像识别层。

包含:
    types             — RecognitionResult 数据类 (V2 2026-07-18: state 改 str)
    template_matcher  — OpenCV 模板匹配封装 (find_and_tap.py / calibrate_templates.py 仍用)

P2 删 (2026-07-18):
    - page_recognizer  (自研识别, pipeline 走 MaaFramework 不消费)
    - ocr_matcher      (DBNet + CRNN 本地 OCR, onnxruntime dep, 走 MaaFramework 自带 OCR)

禁止引入:
    OCR (Tesseract / PaddleOCR / EasyOCR 等)
    深度学习模型 (onnxruntime / torch / YOLO 等)
"""

__all__ = ["template_matcher", "types"]
__version__ = "0.7.0"
