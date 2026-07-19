# Contributing to naruto-auto-daily

> 多 AI 协作开发规范 — 适用于人类开发者 & AI agent(Both Mavis / DeepSeek / 其他)。

## 0. 元规则

任何 **修改业务逻辑 / 修改识别算法 / 修改 Task 流程 / 重构核心框架** 的改动,**禁止直接实施**;必须先列在 PR 描述的 "Risks" 部分。

本次项目工程治理阶段(2026-06-29 → 2026-06-30)允许的改动:
- ✅ 项目结构整理 / 文件整理 / 文档整理 / 命名统一
- ✅ 无效资源清理(已先行 Trash)
- ✅ 配置整理 / 注释补充 / README 完善
- ✅ 新建文档 / 新建模板生成器 / 添加 type hint

**禁止**的业务改动类型:
- ❌ 修改识别算法 / ROI / threshold
- ❌ 修改 Task 流程(节点 next/on_error)
- ❌ 重构 task_engine_maafw / MaaFramework 桥接层
- ❌ 新增 task 但未走 MFAAvalonia 桌面 GUI (CLI 端跑批已废,统一走 agent/custom/)

## 1. 目录速查

```text
naruto-auto-daily/                          (2026-07-19 OPT-1+OPT-2 精简后)
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
└── docs/                  # 设计 spec (code-quality-optimization-plan, superpowers/specs/)
```

(2026-07-19 OPT-1+OPT-2 后: state_machine/ / recovery/ / tasks/<tid>_task.py 全删,
统一走 MaaFramework pipeline + agent/custom/ 自定义 action)
└── screenshots/         # 调试截图(calibration/ + failures/)
```

## 2. AI 协作守则(Mavis / DeepSeek)

| 角色 | 准守 |
|------|------|
| **Mavis** | "司机",直入代码,显式拆 11 节点 task,每步 ROI 配 tap_offset |
| **DeepSeek** | "副驾+导航",长 case 分析,根因诊断(Q1:红点 vs UI 变更) |
| **用户** | 指挥,提供 2 张截图锚定入口路径,纠正误解 |

**原则**:
1. **不重复犯相同错**(用户提醒过的事写进 memory)
2. **best-effort SUCCESS ≠ 跑通**(从 2026-06-30 起:失败真报失败,不掩饰)
3. **改任何代码前先问 user "入口路径"**,不要自己推断
4. **pipeline 是单一权威源**(`resources/narutomobile/pipeline/merged.json`,1554 节点,改它必跑 `python tools/fake_green_detect.py` 验无假绿)

## 3. 新增一个 Task

**不要手动写** `tasks/<new_task>_task.py`,使用模板生成器:

```powershell
# 1. 从 narutomobile / merged.json 抽 ROI,加到 tools/gen_11_tasks.py 的 TASKS 列表
# 2. 运行
python tools/gen_11_tasks.py
# 3. 加到 tools/dryrun_runner.py 的 TASK_BUILDERS 字典
# 4. 加到 config/task_registry.yaml (display_order / category / description)
# 5. 写一个 test_<task>_task.py
```

详见 `docs/standards/TASK_TEMPLATE.md`。

## 4. 新增 / 修改模板

- 模板放 `resources/templates/actions/<task_dir>/<name>.png`
- 同名模板按 `v3 → v4` 顺序追加在 fallback chain,**不要替换**
- 严禁超过 5 KB 的 PNG(大概率是被压缩损坏)
- 跑 `python tools/validate_templates.py` 检查缺失 / 孤儿
- 跑 `python tools/generate_template_manifest.py` 更新 `manifest.json`

## 5. 提 PR 流程

1. 提交前跑 `python -m pytest tests -q` 必须通过
2. 跑 `python tools/generate_template_manifest.py` 同步 manifest
3. 跑 `python tools/validate_templates.py` 通过
4. PR 描述包含:
   - 修改目的
   - 修改清单(逐条)
   - 测试截图(尤其 task 改动)
   - Risks(如有)

## 6. 紧急:重置模拟器

如果 MuMu 12 卡死:
```powershell
# 1. 关闭 干跑工具
Get-Process python | Where-Object {$_.Path -match "firefox|chrome"} | Stop-Process
# 2. 重启 MuMu
Start-Process "D:\Program Files\Netease\MuMuNxDevice\MuMuNxMain.exe"
# 3. 等待 30 秒,验证端口
Test-NetConnection 127.0.0.1 -Port 5555
```
