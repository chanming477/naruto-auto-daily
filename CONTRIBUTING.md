# Contributing to naruto-auto-daily

欢迎贡献!这个文档说明目录结构、模板规范、提 PR 流程。

## 1. 目录速查

```text
naruto-auto-daily/
├── main.py                # CLI 入口 (--gui / --check / --list-tasks / --init-config)
├── core/                  # config_manager / logger / app_paths / run_context / task_result
├── device/                # types (ActionResult)
├── recognition/           # template_matcher + types
├── maafw_bridge/          # MaaFramework 桥接 (event_sink / tasker / resource / _actions_core)
├── agent/                 # MFAAvalonia Agent 自定义 action/recognition/sink
├── tasks/                 # 业务 task (task_engine_maafw)
├── tools/                 # dryrun / utility (audit_templates / find_and_tap / fake_green_detect / pre_gui_smoke)
├── tests/                 # 单元测试
├── frontend/MFAAvalonia/  # .NET 10 桌面客户端 (~235 MB, .gitignore)
├── resources/narutomobile/  # MaaFramework 资源包 (pipeline/merged.json + image/ + model/)
├── config/                # YAML (app_config.yaml + task_registry.yaml)
├── logs/                  # 运行时日志
├── docs/                  # 设计 spec
└── screenshots/           # 调试截图 (calibration/ + failures/)
```

## 2. 新增一个 Task

业务 task 通过 MaaFramework pipeline 实现(`resources/narutomobile/pipeline/merged.json`),
不要手动创建 `tasks/<new_task>_task.py`。

新增流程:
1. 在 `merged.json` 里写任务节点(参考现有 task 的命名/结构)
2. 跑 `python tools/validate_templates.py` 检查模板无遗漏
3. 跑 `python tools/generate_template_manifest.py` 同步 manifest
4. 跑 `python -m pytest tests -q` 全绿
5. 在 `frontend/MFAAvalonia/config/instances/default.json` 注册任务
6. 真机跑一次确认

详见 `docs/standards/TASK_TEMPLATE.md`。

## 3. 新增 / 修改模板

- 模板放 `resources/templates/actions/<task_dir>/<name>.png`
- 同名模板按 `v3 → v4` 顺序追加在 fallback chain,**不要替换**
- 单张 PNG 不要超过 5 KB(大概率是被压缩损坏)
- 跑 `python tools/validate_templates.py` 检查缺失 / 孤儿
- 跑 `python tools/generate_template_manifest.py` 更新 `manifest.json`

## 4. 提 PR 流程

1. 提交前跑 `python -m pytest tests -q` 必须通过
2. 跑 `python tools/generate_template_manifest.py` 同步 manifest
3. 跑 `python tools/validate_templates.py` 通过
4. PR 描述包含:
   - 修改目的
   - 修改清单(逐条)
   - 测试截图(尤其 task 改动)
   - Risks(改识别算法 / 改 task 流程 / 改 task_engine_maafw / 改 MaaFramework 桥接层 时必须列出)

## 5. 改动红线

**禁止直接实施**的改动(必须在 PR 描述 "Risks" 部分说明):
- 修改识别算法 / ROI / threshold
- 修改 Task 流程(节点 next/on_error)
- 重构 task_engine_maafw / MaaFramework 桥接层
- 新增 task 但未走 MFAAvalonia 桌面 GUI

**允许**的改动:
- 项目结构整理 / 文件整理 / 文档整理 / 命名统一
- 无效资源清理
- 配置整理 / 注释补充 / README 完善
- 新建文档 / 新建模板生成器 / 添加 type hint

## 6. 紧急:重置模拟器

如果 MuMu 12 卡死:
```powershell
# 1. 关闭干跑工具
Get-Process python | Where-Object {$_.Path -match "firefox|chrome"} | Stop-Process
# 2. 重启 MuMu
Start-Process "D:\Program Files\Netease\MuMuNxDevice\MuMuNxMain.exe"
# 3. 等待 30 秒,验证端口
Test-NetConnection 127.0.0.1 -Port 5555
```
