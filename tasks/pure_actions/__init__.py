"""tasks.pure_actions — 本项目(不依赖 narutomobile 资源)版的动作层。

设计目标:
    narutomobile ``merged.json`` 里的 GoIntoEntryByGuide / 15-JumpBack recovery 链
    默认走 Maafw 引擎 + 抄来的社区模板/模型。本目录提供 **纯 Python 替代实现**,
    用本项目自己的:
        - ``recognition.ocr_matcher.OCRMatcher`` (onnxruntime,模型在 resources/ocr_models/)
        - ``recognition.template_matcher.TemplateMatcher`` (OpenCV,本项目自写)
        - ``device.adb_client.ADBClient`` (本项目封装)
        - ``tasks.common_actions.CommonActions`` (本项目封装)

adapters 模式:
    - ``maafw_bridge.custom_actions.GoIntoEntryByGuideAction`` 走 maa context(narutomobile)
    - 本目录 ``GoIntoEntryByGuide`` 走纯 Python(本项目)
    两套并存,逐步迁移。
"""
