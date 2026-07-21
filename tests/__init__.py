"""tests package · Phase 1 冒烟测试。

覆盖范围（按文件，2026-07-21 P2 清理 + 扁平化后）：
    test_config_manager.py  — 配置加载 / 字段补齐 / YAML 损坏自动恢复
    test_clean_logs.py      — clean_logs_run 行为 (sessions 保留策略 + debug/ 清理)
    test_task_mapping.py    — task_id ↔ entry 翻译链 / CLI_ALIASES / reverse mapping
    test_pipeline_overrides.py — frontend override auto-load + hardcoded merge
    test_main.py            — CLI 参数解析 / --list-tasks / --check / --init-config

P2 已删 (2026-07-18):
    test_state_machine.py   (state_machine/ 已删)
    test_base_task.py       (base_task.py 已删)
    test_pipeline.py        (旧 task_engine + run_single 已删, 统一走 MaaTaskEngine)

所有测试都用 tmp_path 隔离文件系统，不依赖 Windows 平台（仅测试
非 Windows 专属逻辑；Win32 后端在 smoke-test 手动跑）。
"""