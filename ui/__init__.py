"""ui — Phase 5 桌面客户端(PySide6)。

包入口。子模块:
    - main_window          MainWindow + 启动入口
    - task_panel           任务列表
    - resource_status_panel 资源状态(模板)
    - control_panel        Start / Stop
    - status_panel         实时统计
    - log_panel            实时日志
    - scheme_manager       方案 JSON 持久化
    - config_dialog        配置编辑
    - qt_log_handler       loguru → Qt signal 桥接
    - run_worker           QThread 包 TaskEngine.run_all()

启动方式:
    python -m ui.main_window
    python main.py --gui
"""
