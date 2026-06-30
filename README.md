# naruto-auto-daily (Phase 6)

火影手游本地自动化工具 — **Phase 6 真实日常任务接入**。

> 当前交付 **Phase 1-6**:
> - Phase 1: `ConfigManager / Logger / WindowManager / ScreenshotManager / BaseTask / Scheduler`
> - Phase 2: `ADBClient / TemplateMatcher / PageRecognizer / GameStateMachine`
> - Phase 3: `TaskEngine / DailySigninTask / CommonActions`
> - Phase 4: `RetryManager / RecoveryManager / RunContext`
> - Phase 5: `PySide6 MainWindow` (LogPanel + ConfigDialog)
> - Phase 6: 6 个真实日常任务 (`mail / liveness / group_signin / daily_signin / weekly_signin / activity`)
>
> 当前阶段: **Phase 2 真机回归** (2026-06-29)

## 1. 快速开始

```powershell
# 1. 安装依赖
python -m pip install -r requirements.txt

# 2. 生成默认配置(已存在不覆盖)
python main.py --init-config

# 3. 自检(ADB / 配置 / 模板 / 任务注册表)
python main.py --check

# 4. 真机跑任务(需 MuMu 模拟器 + 游戏在主页 + 1920x1080)
python main.py --mail-real
python main.py --daily-signin-real
python main.py --daily-all         # 顺序跑 schemes/daily.json 全部任务

# 5. 不连真机的 demo(任意机器能跑)
python main.py --phase2-smoke

# 6. 跑测试
python -m pytest tests -q
```

## 2. 命令速查

| 命令 | 用途 |
|---|---|
| `--check` | **P1-7 自检**: ADB / Pydantic / 模板 / 任务注册表 |
| `--phase2-smoke` | 不连 ADB,跑 Phase 2 识别闭环 (默认行为) |
| `--phase2` | 尝试连真 ADB;失败自动 fallback |
| `--phase3` / `--phase3-task <id>` | 任务系统 TaskEngine + DailySigninTask |
| `--phase4` | 稳定性体系 RetryManager + RecoveryManager |
| `--gui` | PySide6 桌面客户端 |
| `--mail-real` | 真实模拟器跑邮件领取 |
| `--daily-signin-real` | 真实模拟器跑每日签到 |
| `--liveness-real` | 真实模拟器跑活跃奖励 |
| `--group-signin-real` | 真实模拟器跑组织祈福 |
| `--daily-all` | 顺序跑 schemes/daily.json 全部任务 |
| `--debug` / `--quiet` | 日志级别 DEBUG / WARNING |
| `--version` | 打印版本号 |

## 3. 目录结构

```
naruto-auto-daily/
├── main.py                       # CLI 入口 (含 --check / --mail-real 等)
├── pyproject.toml
├── requirements.txt
├── README.md
│
├── config/
│   ├── app_config.yaml           # 全局应用配置 (Pydantic)
│   ├── device_config.yaml        # 窗口/模拟器 profile
│   └── task_registry.yaml        # 任务注册表 (8 个任务)
│
├── core/                         # 核心引擎层
│   ├── config_manager.py         # YAML + Pydantic
│   ├── logger.py                 # Loguru 三 sink
│   ├── window_manager.py         # Win32 + RLock
│   ├── screenshot_manager.py     # PrintWindow + mss
│   ├── base_task.py              # 5 阶段生命周期
│   ├── state_machine.py          # 通用状态机
│   └── scheduler.py              # 任务调度
│
├── device/                       # 设备控制层
│   ├── adb_client.py             # ADB connect/screenshot/tap/swipe
│   └── types.py                  # ActionResult
│
├── recognition/                  # 图像识别层
│   ├── template_matcher.py       # OpenCV TM_CCOEFF_NORMED
│   └── types.py                  # RecognitionResult
│
├── state/                        # 游戏状态层
│   ├── game_state.py             # GameState 枚举
│   └── types.py                  # ExecutionContext
│
├── recognizer/                   # 页面识别入口
│   └── page_recognizer.py        # detect_state()
│
├── state_machine/                # 游戏业务状态机
│   └── game_state_machine.py     # update_state / recover
│
├── recovery/                     # Phase 4 稳定性
│   ├── retry_manager.py          # execute_adb_action 真实链
│   └── recovery_manager.py       # recover_unknown/popup/adb_error
│
├── logging_ext/                  # RunContext 日志上下文
│
├── tasks/                        # 业务任务 (Phase 6)
│   ├── navigator.py              # Pipeline/Node/Action 基类
│   ├── pipeline_runner.py        # 跨任务共享运行容器
│   ├── common_actions.py         # 跨任务共享动作
│   ├── daily_signin_task.py      # 每日签到
│   ├── mail_task.py              # 邮件领取
│   ├── liveness_task.py          # 活跃奖励
│   ├── group_signin_task.py      # 组织祈福
│   ├── weekly_signin_task.py     # 每周签到
│   ├── activity_task.py          # 一乐外卖活动
│   ├── monthly_signin_task.py    # 每月签到
│   ├── recruit_task.py           # 招募
│   └── task_engine.py            # Scheduler 业务包装
│
├── ui/                           # Phase 5 PySide6
│   ├── main_window.py            # MainWindow
│   ├── log_panel.py              # LogPanel (setMaximumBlockCount 自动截断)
│   └── config_dialog.py          # ConfigDialog
│
├── schemes/
│   └── daily.json                # 全日常任务顺序
│
├── resources/templates/actions/  # 真机采集的模板 (146 个)
│   ├── shared/                   # 跨任务共享 (home/x/award_button 等)
│   ├── mail/                     # 邮件页
│   ├── group/                    # 组织祈福
│   ├── activity/                 # 活动页
│   ├── liveness/                 # 活跃奖励
│   └── deprecated/               # 废弃模板 (weekly_sign.png 等)
│
├── screenshots/failures/         # 节点失败时的 ROI 截图 (P1-1 增强)
├── logs/                         # 运行时日志
└── tests/                        # 376 个 pytest 用例 (98.4% 通过)
```

## 4. 当前任务清单

| task_id | 名称 | 入口 | 模板状态 |
|---|---|---|---|
| `mail` | 邮件领取 | 主页 → 信封 (80,385) | ✅ 已采 |
| `liveness` | 活跃奖励 | 主页 → 奖励 → 活跃 tab | ✅ 16 个 liveness/* 复用 |
| `group_signin` | 组织祈福 | 主页 → 奖励 → 组织祈福卡 | ✅ group/* 已采 |
| `daily_signin` | 每日签到 | 主页 → 奖励 → 每日签到 | ✅ shared/check_in_daily_award |
| `weekly_signin` | 每周签到 | (待补采) | ⚠️ deprecated, 当前 best-effort 跳过 |
| `activity` | 一乐外卖 | 主页 → 活动 → 菜盒 | ⚠️ 部分缺失 |
| `monthly_signin` | 每月签到 | 主页 → 活动 → 每月签到 tab | ⚠️ OCR 引导 |
| `recruit` | 招募 | (待补采) | ⚠️ best-effort |

## 5. 设计原则

- **不调 KeyAction(key="BACK")**: 会触发"是否退出游戏"弹窗。recover() 用模板化 dismiss_x + tap_home_button。
- **best-effort SUCCESS**: 模板缺失时 Pipeline 降级到 back_to_home,任务仍返 SUCCESS。
- **Pipeline 借鉴 MaaFramework**: Navigator + Pipeline + Node/Action 结构,fallback chain 模板依次匹配。
- **Pydantic 全量校验**: ConfigManager 启动时跑一次,失败阻止启动。

## 6. 已知限制

- MuMu 12 + adb input 对系统弹窗"是否退出游戏"无响应 (native rendering),需要 force-stop 重启游戏。
- 每周签到 / 招募 / 活动 模板缺失较多,best-effort 跳过。
- 跨账号模板失效: 旧账号 conf=0.99,新账号 conf=0.114-0.617 (奖励按钮红点差异)。已加 v5_real / v4_real fallback。

## 7. 进一步阅读

- `D:\claude-data\claude-config\plans\d-narutomobile-main-logical-brooks.md` — 完整修复方案 (P0/P1/P2)
- `docs/` — 业务任务规格、决策记录
- `C:/Users/27392/.mavis/memory/project_naruto_helper.md` — 项目知识库