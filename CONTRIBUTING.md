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
- ❌ 重构 TaskEngine / Navigator / RecoveryManager / RetryManager
- ❌ 新增 task 但未走 `tasks/<tid>_task.py` 标准流程(应该用 `tools/gen_11_tasks.py` 模板)

## 1. 目录速查

```
naruto-auto-daily/
├── core/                # Phase 1 核心引擎(只读,改动需评审)
├── device/              # ADB 客户端
├── recognition/         # template_matcher.py(主识别)
├── recognizer/          # page_recognizer.py(页面识别入口)
├── state/               # game_state.py + types.py
├── state_machine/       # game_state_machine.py(业务状态机)
├── recovery/            # Phase 4 稳定性
├── logging_ext/         # RunContext
├── ui/                  # PySide6 桌面
├── tasks/               # 28 个业务 task + 4 个核心(共 32 .py)
│   ├── navigator.py / pipeline_runner.py / common_actions.py / task_engine.py  # 核心 4
│   └── <task_id>_task.py ×28                                                  # 业务 28
├── tools/               # dryrun_* × 30 / calibrate_*.py / find_and_tap.py / 等
├── tests/               # 24 个 test_*.py
├── resources/templates/ # 模板库(actions/ 是主目录, 56 子目录)
├── docs/                # 文档
│   ├── PROJECT_PLAN.md  # 阶段总览
│   ├── standards/       # TASK_STANDARD / TASK_TEMPLATE / TEMPLATE_NAMING
│   ├── game_wiki/       # 15 个游戏系统知识库
│   ├── calibration/     # home_entry_paths / roi_calibration_log
│   ├── collaboration/   # WORKGROUP(Mavis+DeepSeek 协作日志)
│   └── CHANGELOG.md     # 版本变更(根目录链接)
├── config/              # YAML + schemes/*.json
├── logs/                # 运行时日志
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
4. **narutomobile-main 是单一权威源**(`D:\自动日常源码带\narutomobile-main` 或 `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\resource\base\pipeline\merged.json`)

## 3. 新增一个 Task

**不要手动写** `tasks/<new_task>_task.py`,使用模板生成器:

```powershell
# 1. 从 narutomobile / merged.json 抽 ROI,加到 tools/gen_11_tasks.py 的 TASKS 列表
# 2. 运行
python D:\tmp\gen_11_tasks.py
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
