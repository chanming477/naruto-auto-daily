"""recognition package · Phase 2 图像识别层。

包含:
    types             — RecognitionResult 数据类
    template_matcher  — OpenCV 模板匹配封装

禁止引入:
    OCR(Tesseract / PaddleOCR / EasyOCR 等)
    深度学习模型(onnxruntime / torch / YOLO 等)
"""

__all__ = ["template_matcher", "types"]
__version__ = "0.2.0"