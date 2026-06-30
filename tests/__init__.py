"""tests package · Phase 1 冒烟测试。

覆盖范围（按文件）：
    test_state_machine.py   — 转换 / 回调 / reset / history / 并发安全
    test_config_manager.py  — 配置加载 / 字段补齐 / YAML 损坏自动恢复
    test_base_task.py       — 任务生命周期 / pre_check skip / retry
    test_pipeline.py        — 端到端：build_context + smoke run + run_single

所有测试都用 tmp_path 隔离文件系统，不依赖 Windows 平台（仅测试
非 Windows 专属逻辑；Win32 后端在 smoke-test 手动跑）。
"""