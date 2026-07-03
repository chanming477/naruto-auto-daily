# naruto-auto-daily

> 火影手游本地自动化工具 — **28 个真实日常任务** + 工程治理(2026-06-30)。

[![Python](https://img.shields.io/badge/Python-3.11+-blue)]() [![License](https://img.shields.io/badge/License-MIT-green)]() [![Tasks](https://img.shields.io/badge/Tasks-28-brightgreen)]() [![Template](https://img.shields.io/badge/Templates-680+-orange)]()

---

## 📑 目录

- [0. 一句话总结](#0-一句话总结)
- [1. 当前阶段 (2026-06-30)](#1-当前阶段-2026-06-30)
- [2. 28 任务快速一览](#2-28-任务快速一览)
- [3. 快速开始](#3-快速开始)
- [4. 命令速查](#4-命令速查)
- [5. 目录结构](#5-目录结构)
- [6. 架构图](#6-架构图)
- [7. 模板](#7-模板)
- [8. 工程治理](#8-工程治理)
- [9. 开发规范](#9-开发规范)
- [10. Roadmap](#10-roadmap)
- [11. 贡献](#11-贡献)
- [12. License](#12-license)

---

## 0. 一句话总结

> **naruto-auto-daily** = 通过模板匹配(OpenCV `TM_CCOEFF_NORMED`)+ MaaFramework pipeline 节点,把火影手游里 28 个"日常任务"(邮件/签到/活跃/招募/活动/战斗副本/叛忍/百忍/...)自动化执行,无需 GPU 只需 MuMu 12 模拟器(1920x1080)+ 永不停歇的小忍者。

## 1. 当前阶段 (2026-06-30)

**Phase 7 — 工程治理 + 28 task 全栈就绪**

- ✅ Phase 1-6: 核心引擎 + 7 基础 task
- ✅ Phase 7-A: **21 个新 task 全抄自 [narutomobile-main](D:\自动日常源码带\narutomobile-main)**(v1.3.35 merged.json)
- ✅ Phase 7-B: 工程治理(目录/文档/命名/LICENSE/CONTRIBUTING/CHANGELOG)
- 🔄 阶段 2 真机回归(MuMu 12 端口 `127.0.0.1:5555`)

## 2. 28 任务快速一览

| task_id | 中文名 | 类别 | 入口 | 备注 |
|---------|--------|------|------|------|
| **基础 7 task** | | | | |
| `mail` | 邮件领取 | daily | 主页右上"邮件" | Phase 6 P0 |
| `daily_signin` | 每日签到 | daily | 奖励中心 → 每日签到 | Phase 3 P0 |
| `weekly_signin` | 每周签到 | weekly | 主页 → 每周签到入口 | Phase 6 P0 |
| `liveness` | 活跃度奖励 | daily | 主页 → 活跃度 | Phase 6 P0 |
| `recruit` | 招募 | daily | 主页 → 招募 | Phase 7 |
| `activity` | 一乐外卖活动 | weekly | 主页 → 一乐拉面活动页 | Phase 6 |
| `group_signin` | 组织祈福 | daily | 奖励中心 → 组织祈福 | Phase 6 P1 |
| **月度签到类** | | | | |
| `monthly_signin` | 每月签到 | monthly | 主页 → 活动 → 每月签到 | Phase 7 (2026-06-30) |
| **战斗副本类** | | | | |
| `rich_room` | 丰饶之间 | combat | 奖励中心 → 丰饶之间 | Phase 7 |
| `team_dash` | 小队突袭 | combat | 奖励中心 → 小队突袭 | Phase 7 |
| `secret_realm` | 秘境探险 | combat | 奖励中心 → 秘境探险 | Phase 7 |
| `survival_challenge` | 生存挑战 | combat | 奖励中心 → 生存挑战 | Phase 7 |
| `shugyou_no_michi` | 修行之路 | combat | 奖励中心 → 修行之路 | Phase 7 |
| `stronghold` | 要塞 | combat | 奖励中心 → 组织 → 要塞 | Phase 7 |
| `mission_office` | 任务集会所 | combat | 奖励中心 → 任务集会所 | Phase 7 |
| `advanture` | 冒险 | combat | 主页右下"冒险"卷轴 | Phase 7 |
| `elite_instance` | 精英副本 | combat | 主页 → 冒险 → 精英副本 | Phase 7 |
| `point_race` | 积分赛 | combat | 奖励中心 → 积分赛 | Phase 7 |
| `rebel_ninja` | 叛忍 | combat | 忍界指引 → 叛忍 | Phase 7 |
| `use_energy` | 使用体力 | daily | 体力入口 → 一键扫荡 | Phase 7 |
| `give_energy` | 赠送体力 | daily | 主页右上"送S忍" | Phase 7 |
| **玩法/社交类** | | | | |
| `leaderboard` | 排行榜点赞 | social | 忍者书 → 排行榜 | Phase 7 |
| `more_gameplay` | 更多玩法 | combat | 奖励中心 → 更多玩法 | Phase 7 |
| `ninja_book` | 忍者书奖励 | daily | 忍者书 → 9 类奖励 | Phase 7 |
| `weekly_win` | 周胜 | combat | 奖励中心 → 周胜 | Phase 7 |
| `sky_ground` | 天地 | combat | 忍界指引 → 天地 | Phase 7 |
| `easy_helper` | 简单助手 | daily | 主页右下"简单助手" | Phase 7 |
| `hundred_ninja` | 百忍 | combat | 主页右下"决斗场" | Phase 7 |

> 详见 `config/task_registry.yaml`

## 3. 快速开始

```powershell
# 1. 安装依赖
python -m pip install -r requirements.txt

# 2. 生成默认配置(已存在不覆盖)
python main.py --init-config

# 3. 自检(ADB / 配置 / 模板 / 任务注册表)
python main.py --check

# 4. 真机跑任务(需 MuMu 12 模拟器 + 游戏在主页 + 1920x1080)
python tools\dryrun_runner.py mail
python tools\dryrun_runner.py monthly_signin

# 5. 不连真机的 demo(任意机器能跑)
python main.py --phase2-smoke

# 6. 跑测试
python -m pytest tests -q

# 7. 验证模板库
python tools/validate_templates.py
python tools/generate_template_manifest.py
```

## 4. 命令速查

| 命令 | 用途 |
|---|---|
| `--check` | **P1-7 自检**: ADB / Pydantic / 模板 / 任务注册表 |
| `--phase2-smoke` | 不连 ADB,跑 Phase 2 识别闭环 (默认行为) |
| `--phase2` | 尝试连真 ADB;失败自动 fallback |
| `--phase3` / `--phase3-task <id>` | 任务系统 TaskEngine + DailySigninTask |
| `--phase4` | 稳定性体系 RetryManager + RecoveryManager |
| `--gui` | PySide6 桌面客户端 |
| `<task>-real` (28 个) | 真模拟器跑指定 task(需 MuMu 12 + 127.0.0.1:5555) |
| `--daily-all` | 顺序跑 `schemes/daily.json` 全部 task |
| `--debug` / `--quiet` | 日志级别 DEBUG / WARNING |
| `--version` | 打印版本号 |

## 5. 目录结构

```
naruto-auto-daily/
├── main.py                       # CLI 入口(1297 行)
├── pyproject.toml                # 项目元数据 + Ruff 配置 + dev deps
├── requirements.txt              # 12 个运行时依赖
├── README.md                     # 本文件
├── CHANGELOG.md                  # 版本变更日志
├── CONTRIBUTING.md               # 多 AI 协作开发规范
├── LICENSE                       # MIT
├── workgroup.md                  # Mavis+DeepSeek 协作日志
│
├── config/
│   ├── app_config.yaml           # 全局 YAML
│   ├── device_config.yaml
│   └── task_registry.yaml        # 28 task 注册表
│
├── core/                         # Phase 1 核心引擎
├── device/                       # ADB 客户端
├── recognition/                  # template_matcher(主识别)
├── recognizer/                   # page_recognizer(页面识别入口)
├── state/                        # game_state 枚举 + types
├── state_machine/                # 游戏业务状态机
├── recovery/                     # Phase 4 稳定性
├── logging_ext/                  # RunContext
├── ui/                           # Phase 5 PySide6
├── tasks/                        # 28 业务 + 4 核心
├── tools/                        # 39 dryrun/utility
├── tests/                        # 24 测试
│
├── resources/
│   └── templates/
│       ├── manifest.json         # 模板元数据
│       ├── actions/              # 680 个模板(56 子目录)
│       ├── shared/               # 公共模板(主页/关闭按钮等)
│       ├── state/                # main_green_masked.png 主页标识
│       ├── startup/              # 启动页模板
│       ├── popup/                # 弹窗关闭按钮
│       ├── home/                 # 主页背景
│       ├── home_special/         # 特殊主页卷轴
│       └── liveness/             # 活跃度
│
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── COMPLETION_REPORT.md
│   ├── operation_flows.md
│   ├── 项目准备.md
│   ├── home_for_reference.png
│   ├── calibration/              # ROI 校准
│   ├── game_wiki/                # 15 个游戏系统知识库
│   ├── standards/                # TASK_STANDARD / TASK_TEMPLATE / TEMPLATE_NAMING
│   └── collaboration/            # WORKGROUP.md(Mavis+DeepSeek)
│
├── screenshots/                  # 调试截图
├── logs/                         # 运行时日志(按日期分)
└── schemes/                      # daily/event/weekly JSON
```

## 6. 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                     UI Layer (PySide6)                       │
│      main_window / log_panel / task_panel / config_dialog  │
└────────────────────────┬─────────────────────────────────────┘
                         │ qasync / signals
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  Pipeline Orchestration                     │
│   scheduler → task_engine → pipeline_runner → navigator     │
│   (BaseTask lifecycle: pre → enter → execute → verify)      │
└────────────────────────┬─────────────────────────────────────┘
                         │
        ┌────────────────┼─────────────────┐
        ▼                ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Recognition  │ │  Device (ADB)  │ │  Recovery/Retry │
│ TemplateMatcher│ │   ADBClient   │ │ RetryManager    │
│   damer/match  │ │  screenshot/tap│ │ RecoveryManager │
└──────┬──────┘ └──────┬────────┘ └──────────────────┘
       │                │
       ▼                ▼
┌──────────────────────────┐
│   Template Library       │
│   resources/templates/   │
│   actions/ + shared/...  │
└──────────────────────────┘
```

数据流:`UI 触发 task → Pipeline.run → 每个 Node 跑(模板匹配 → 找坐标 → ADB tap)→ 截图 → 进入下个 Node → 全部 Node 完成 → verify_done → 回主页`

## 7. 模板

| 模板目录 | 数量 | 来源 |
|---------|------|------|
| `actions/` 主目录 | 56 子目录,680+ PNG | narutomobile v1.3.35 merged.json 镜像 |
| `shared/` | 公共(主页 / 关闭 / 忍者指南 / 进忍法帖 等) | 含 `award_center_entry.png` / `headhunt.png` / `guide.png` |
| `state/main_green_masked.png` | 主页绿通道标识 | narutomobile 权威 |
| `startup/` | 启动页(`naruto_logo.png` / `start_game.png`) | 启动流程 |

**模板元数据**: `resources/templates/manifest.json`(template_count / task_dirs / main_screen_detector / 来源 / 注意事项)。

**校验**: `python tools/validate_templates.py` 检查孤儿 / 缺失。

## 8. 工程治理

2026-06-30 完成清理:

✅ 删除 `_tmp_a5_list.py`(根临时)
✅ 删除 `dryrun_v2.py` / `dryrun_v3.py`(已替代)
✅ 删除 `__pycache__/` ×13 个
✅ 删除 `scripts/` 空目录
✅ 删除 `narutomobile_ref/` 5 文件(已覆盖)
✅ 删除 6 个空 templates 子目录
✅ 删除 `logs/*.bak` ×3
✅ 重写 `pyproject.toml`(v0.7.0 + dev deps)
✅ 更新 `main.py` header(Phase 7)
✅ 新建 `LICENSE`(MIT)
✅ 新建 `CONTRIBUTING.md`(多 AI 协作)
✅ 新建 `CHANGELOG.md`(版本变更)
✅ 新建 `docs/standards/TASK_TEMPLATE.md`(task 生成器规范)
✅ 新建 `docs/standards/TEMPLATE_NAMING.md`(模板命名规范)
✅ 新建 `resources/templates/manifest.json`(模板元数据)
✅ README.md 全面重写(28 task 表格 + 架构图 + 完整命令)

未做(将来):
- ⏳ `state/` vs `state_machine/` / `recognition/` vs `recognizer/` 命名合并(改动大)
- ⏳ actions/ 子目录大小写统一(影响 tasks/*.py 路径)

## 9. 开发规范

> 完整规范见 `CONTRIBUTING.md` + `docs/standards/`

**硬规则**:
- ❌ 禁止修改识别算法 / ROI / threshold
- ❌ 禁止修改 Task 流程(节点 next/on_error)
- ❌ 禁止重构 TaskEngine / Navigator / RecoveryManager
- ❌ 新增 task **不得手写** `tasks/<tid>_task.py` — 必须用 `tools/gen_11_tasks.py`
- ✅ 新增 / 修改模板放 `resources/templates/actions/<task_dir>/`
- ✅ 同名模板 `v3 → v4` 顺序追加在 fallback chain 前端,**不替换**
- ✅ 提交前跑 `pytest tests -q` 必须通过

**失败真报**:
- 自 2026-06-30 起,所有 task 的 `on_error` 不再 silent `verify_done`(best-effort SUCCESS 掩饰已废弃)
- 失败真报失败,Pipeline 状态 FAIL

## 10. Roadmap

- ✅ Phase 1: 核心引擎 — config / logger / screenshot / window / task / scheduler
- ✅ Phase 2: ADB / Template / Recognize / GameStateMachine
- ✅ Phase 3: TaskEngine + DailySigninTask
- ✅ Phase 4: RetryManager + RecoveryManager
- ✅ Phase 5: PySide6 GUI
- ✅ Phase 6: 7 基础真实日常 task
- ✅ Phase 7: 21 新 task(narutomobile 全抄)+ 工程治理
- 🔄 Phase 8: 真机回归(2026-06-30 开始,等 user MuMu 重启)
- ⏳ Phase 9: Task-level 测试 + CI(GitHub Actions)
- ⏳ Phase 10: Template 版本管理(SHA + commit)
- ⏳ Phase 11: 模板生成器 v2(支持 custom_action / MultiSwipe 等复杂节点)
- ⏳ Phase 12: 自愈机制(RecoveryManager 升级)

## 11. 贡献

详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

本项目支持 **多人 + 多 AI 协作** 模式:
- 人类开发者:指挥 + 测试 + 真机验证
- AI Agent(Mavis/DeepSeek):代码实现 + 根因诊断 + 文档撰写

**提 PR 前必读**: `CONTRIBUTING.md` + `docs/standards/TASK_TEMPLATE.md`

## 12. License

本项目采用 [MIT License](./LICENSE)。

---

**Built with ❤️ by naruto-auto-daily contributors · 2026**
