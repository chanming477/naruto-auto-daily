# 代码质量优化方案

> 2026-07-18 · 基于当前项目真实状态编写

---

## 一、当前状态

| 指标 | 数值 |
|------|------|
| 死代码行数 | ~1600 行 (`core/` 4 个文件) |
| main.py 死引用 | 4 个 import (base_task / screenshot_manager / state_machine / window_manager) |
| agent 文件重复 | 2 处 (`agent/custom/` + `frontend/MFAAvalonia/agent/custom/`) |
| pytest 失败 | 2 (`test_task_mapping.py`) |
| 配置冗余 | `config/` 含曾用但已死的 `task_registry.yaml`、`schedule.json` |
| 假绿无检测 | 任务报 SUCCESS 但可能只跑了 helper 节点 |

---

## 二、10 项优化

### OPT-1 · 删 core/ 死代码 (~1600 行)

`main.py` 引用了 4 个已无实际用途的模块，整条链都是旧自研调度系统的残余：

| 文件 | 行数 | 被谁引用 | 为什么死 |
|------|------|---------|---------|
| `core/window_manager.py` | 395 | `main.py:54` | 调试命令 `--list-windows` `--activate-window`，用户没用过 |
| `core/screenshot_manager.py` | 545 | `main.py:52` | 调试命令 `--capture-test`，用户可以 `adb exec-out screencap` 代替 |
| `core/base_task.py` | 315 | `main.py:48` | `BaseTask` 抽象类 — 27 个实现类 7/14 全删，0 个存活 |
| `core/scheduler.py` | ~300 | `main.py` | `Scheduler` — 7/18 跑出 `tasks=0 success=0` 假象 |
| `core/state_machine.py` | 323 | `main.py:53` | `StateMachine` — 旧的游戏状态机，MaaFW 不需要 |
| `tasks/task_engine.py` | ~200 | `main.py` | 旧 `TaskEngine` — 已删 `common_actions.py` 依赖 |

**操作**：
1. 删 `main.py:48/52-54` 的 4 个 import
2. 删 `main.py` 中依赖这些模块的命令：`--list-windows`、`--activate-window`、`--capture-test`、`--smoke-test`、`--daily-all`、`--run-task`、`--phase2/3/4`、`cmd_daily_signin_real/mail_real/liveness_real/group_signin_real` 等
3. 删 `main.py` 中的 `_assemble_real_runner()` 函数 (~50 行)
4. 删 `core/window_manager.py`、`core/screenshot_manager.py`、`core/base_task.py`、`core/state_machine.py`、`core/scheduler.py`
5. 删 `tasks/task_engine.py`
6. 跑 `pytest tests -q` 确认无新增失败

**风险**：无。这些模块仅被 main.py 的旧 CLI 命令引用，MaaFramework 路径完全不碰它们。

---

### OPT-2 · main.py 清理 (~300 行删减)

当前 `main.py` ~1400 行，其中 ~400 行是旧 CLI 死路径。

**保留**：
- `--gui` (启动前端)
- `--daily-maafw` (MaaFW 批量)
- `--maafw-task <id>` (MaaFW 单任务)
- `--check` (自检)
- `--list-tasks` / `--maafw-list`
- `parse_args()` 精简版
- 工具函数：`get_user_data_dir()`、`_print_task_result()`

**删除**：
- `_assemble_real_runner()` 及所有调用它的 `cmd_*_real` 函数
- `cmd_daily_all` 旧实现
- `--phase2/3/4/5`、`--phase2/3/4_smoke`
- `--list-windows`、`--activate-window`、`--capture-test`、`--smoke-test`
- `--run`、`--run-task`
- `--daily-signin-real`、`--mail-real`、`--liveness-real`、`--group-signin-real`、`--weekly-signin-real` 及相关 argparse 参数

**结果**：`main.py` ~1400 → ~1000 行。

---

### OPT-3 · agent 文件去重

当前 `agent/custom/` 和 `frontend/MFAAvalonia/agent/custom/` 各有独立副本，需同步维护。

**操作**：
1. 确认 `frontend/MFAAvalonia/agent/main.py` 的 `_find_project_root()` 正确找到项目根
2. 删 `frontend/MFAAvalonia/agent/custom/` 下的 `action.py`、`reco.py`、`sink.py`、`utils.py`
3. 改 `frontend/MFAAvalonia/agent/main.py` — 删直接的 `import agent.custom.*`，改为 `sys.path` 先加项目根再 import（实际已经在做了，只需确认）
4. 验证：删 frontend 版后，`python -m py_compile agent/main.py` 通过

**结果**：agent 代码只维护一份（项目根 `agent/`），frontend 版只保留 `main.py` 入口。

---

### OPT-4 · 修 pytest 2 个 fail

`tests/test_task_mapping.py:77-79`：
- `default.json` 的 TaskItems 有 2 个 `liveness_award` → 24 items → 23 unique keys
- 测试写了 `assert len(TASK_MAPPING) == 24`，实际 23

**操作**：改断言为去重后比较：
```python
expected = len(set(t["entry"] for t in items))
assert len(TASK_MAPPING) == expected
```

---

### OPT-5 · 配置清理

| 文件 | 处理 |
|------|------|
| `config/task_registry.yaml` | 删（8 个死 task_class 引用，无人 import）或精简为元数据注释 |
| `config/schedule.json` | 删（旧自研调度器用的，MaaFW 不走它） |
| `config/maa_option.json` | 保留（MFAAvalonia 自己读） |
| `config/app_config.yaml` | 删无用字段：`scheduler`、`retry`、`state_machine`、`template_matching`、`game_state` 配置块 |
| `config/device_config.yaml` | 删（WindowManager 已死，device config 无用） |

---

### OPT-6 · 消 default.json CurrentTasks 冗余

`CurrentTasks` 是 MFAAvalonia 左侧栏显示的任务清单，应跟 `TaskItems` 的 `default_check: true` 项对齐。

**当前问题**：
- `CurrentTasks` 26 项，`TaskItems` 22 项
- `CurrentTasks` 含重复 `give_energy`（line 24 "赠送体力" + line 28 "送体力"）
- `CurrentTasks` 含 `use_energy`（line 25 "领取体力"）但 TaskItems 的 use_energy 是 `default_check: false`
- `CurrentTasks` 与 `TaskItems` 顺序不一致

**操作**：用脚本从 TaskItems 生成 CurrentTasks，只保留 `default_check: true` 的项，按 TaskItems 顺序排列。

---

### OPT-7 · 代码注释统一

**操作**：清理代码中残留的 `MaaAutoNaruto v1.3.41 抄`、`MaaAutoNaruto` 等注释。

**不改**：`resources/narutomobile/` 目录名、`maafw_bridge/` 中的技术引用。

涉及文件：
- `maafw_bridge/task_mapping.py` — docstring 中 `MaaAutoNaruto entry` → `pipeline entry`
- `maafw_bridge/tasker.py` — docstring 中 `MaaAutoNaruto` → `pipeline`
- `maafw_bridge/resource.py` — 同上
- `maafw_bridge/_actions_core.py` — 参考路径注释 `D:\自动日常源码带\...` → 删
- `tasks/task_engine_maafw.py` — docstring 清理
- `pyproject.toml` — `description` 字段清理
- `main.py` header → 更新为当前准确描述

---

### OPT-8 · 清理 `resources/_test_backups/`

`resources/narutomobile/_test_backups/` 含 7/17 调试遗留的 20+ 个测试文件（~10 MB）。

**操作**：`rm -rf resources/narutomobile/_test_backups/`。

---

### OPT-9 · 添加假绿检测

当前任务即使只跑了 `close_*` `back_main_*` 等 helper 节点，也报 SUCCESS。用户无法区分"真干活"和"空跑"。

**实现**：扩展 `agent/custom/sink.py` 或新建独立脚本，分类节点：
- **BIZ 节点**：`mail_*` `headhunt_*` `liveness_award_*` `group_*` `activity_*` `energy_*` `ninja_book_*` `secret_realm_*` `point_race_*` 等
- **HELPER 节点**：`close_*` `back_main_*` `check_main_*` `swipe_*` `ninja_guide_*` 等

如果某任务只有 HELPER 节点被触发 → 标记为 "疑似假绿" → 日志 WARNING。

参考已有实现：`tools/_diagnose_business.py` 中的 `BIZ_HINTS` / `HELPER_HINTS` 分类逻辑。

---

### OPT-10 · README 真实化

**操作**：
- 28 task → 24 task
- 删 "28 任务快速一览" 表格（改为指向 `default.json`）
- "全栈就绪" → "24 个任务已对接 MaaFramework pipeline，其中忍者指引类任务已修复"
- 删 `--daily-all`、`--run-task` 等已删命令
- 更新目录结构图（删已移除的目录）

---

## 三、执行顺序

```
[第 1 轮 · 30 分钟 · 0 风险]
  OPT-4  修 pytest 2 fail                               (5 min)
  OPT-8  清 _test_backups/                              (1 min)
  OPT-7  注释统一                                       (15 min)
  OPT-5  配置清理                                       (10 min)

[第 2 轮 · 1 小时 · 需验证]
  OPT-6  消 default.json 冗余                           (15 min)
  OPT-3  agent 文件去重                                 (20 min)
  OPT-1  删 core/ 死代码                                (15 min)
  OPT-2  main.py 清理                                   (20 min)
  ↓ 跑 pytest 确认 0 fail
  ↓ 启 GUI 验证 agent 正常

[第 3 轮 · 1 小时 · 长期价值]
  OPT-9  假绿检测                                       (1 hour)
  OPT-10 README 真实化                                  (20 min)
```

**总工时**: ~3 小时, 零新增风险, 纯删减/修正。
