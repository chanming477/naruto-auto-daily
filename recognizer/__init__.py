"""recognizer package · Phase 2 页面识别层。

包含:
    page_recognizer — detect_state() 入口

注意: 不引入 OCR / 深度学习 / 颜色检测等高级识别手段。
仅基于 Phase 2 的 TemplateMatcher 做多模板投票。
"""

__all__ = ["page_recognizer"]
__version__ = "0.2.0"
