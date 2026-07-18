"""recognition package · Phase 2 图像识别层 + 页面识别。

包含:
    types             — RecognitionResult 数据类
    template_matcher  — OpenCV 模板匹配封装
    page_recognizer   — detect_state() 入口 (从 recognizer/ 合并)

禁止引入:
    OCR(Tesseract / PaddleOCR / EasyOCR 等)
    深度学习模型(onnxruntime / torch / YOLO 等)
"""

__all__ = ["template_matcher", "types", "page_recognizer"]
__version__ = "0.7.0"
