# Changelog

所有重要变更记录在此。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased] - 2026-07-21 (narutomobile v1.3.36 同步)

### 2026-07-21 21:56 反馈合入 (积分赛容错 + 强制从奖励中心)
- **积分赛不出战就结束任务 修复** (narutomobile v1.3.41 自身也有这 bug):
  - 真因: `wait_for_select_opponent` 节点 TemplateMatch `Point_race/select_opponent.png` 漂移匹配不到 → 走 `back_main_screen_and_stop` 结束任务
  - 文件层面 v1.3.41 / OURS 100% 一致 (roi [68, 23, 418, 185], threshold=None)
  - **修复**:
    - ROI 扩大: `[68, 23, 418, 185]` → `[40, 0, 700, 240]` (覆盖 40-740, 0-240, 容错大)
    - threshold: `None` → `[0.7, 0.8]` (多阈值, UI 漂移时更容易匹配)
    - pre_wait_freezes: `None` → 1000 (等 1s 让 UI 稳定)
    - post_wait_freezes: `None` → 1000 (等 1s 让 click 后稳定)
    - post_delay: 0 → 500
- **积分赛改成必须从奖励中心进入** (跟 secret_realm/mission_office 同方案):
  - 新增 option 副本: `从奖励中心进入(积分赛)` (default_case=Yes)
  - point_race task def 替换 `从奖励中心进入` → `从奖励中心进入(积分赛)`, 删 `忍界指引寻找积分赛` option
  - 其他 task (group / point_race / weekly_win 等) 仍用共享 `从奖励中心进入` (default No), 不影响

### 2026-07-21 21:52 反馈合入 (team_dash 出战前取消 4 倍)
- **team_dash_auto_fight next 链前面插 team_dash_check_4x_reward**:
  - 旧: `['[JumpBack]team_dash_same_ninja', 'team_dash_loading', 'check_in_team_dash_sweep', 'team_dash_do_not_remind_gold', 'team_dash_auto_fight', '[JumpBack]team_dash_in_loading']`
  - 新: `['team_dash_check_4x_reward', '[JumpBack]team_dash_same_ninja', ...]`
- **team_dash_check_4x_reward 加 action=Click + post_wait_freezes=500**:
  - 旧 (v1.3.41): 纯识别节点, action=None, 仅判断"4倍已勾选"状态
  - 新: action=Click, post_wait_freezes=500, post_delay=300 — 出战前**自动取消 4 倍奖励**
- **narutomobile v1.3.41 设计 vs user 反馈**:
  - v1.3.41 默认**保留 4 倍** (有 `team_dash_confirm_4x_select` 弹窗逻辑, 弹窗出现直接确认)
  - user 要"取消 4 倍" = user-driven 偏离 v1.3.41
  - 实施: 在出战 (auto_fight) 之前插入取消 4 倍节点, 如果当前 4 倍已勾选就点掉

### 2026-07-21 21:32 反馈合入 (从奖励中心 + team_dash 容错)
- **秘境 / 集会所 任务 改 只能从奖励中心进入**:
  - 新增 option 副本: `从奖励中心进入(秘境)` / `从奖励中心进入(集会所)` (default_case=Yes)
  - `secret_realm` task def: 替换 `从奖励中心进入` -> `从奖励中心进入(秘境)`, 删 `忍界指引寻找秘境` option
  - `mission_office` task def: 替换 `从奖励中心进入` -> `从奖励中心进入(集会所)`, 删 `忍界指引寻找任务集会所` option
  - 其他 task (group / point_race / weekly_win / shugyou_no_michi 等) 仍用共享 `从奖励中心进入` option (default No)
- **team_dash 借组织助战 default 改回 Yes** (撤销 round 2 改动, 跟 v1.3.41 一致)
- **close_team_dash_out_team_sign ROI 扩大** (防"确定"退队弹窗 UI 漂移卡住):
  - 原 ROI: `[535, 418, 205, 74]` (覆盖 535-740, 418-492)
  - 新 ROI: `[300, 350, 680, 250]` (覆盖 300-980, 350-600, 容错大)
  - `post_wait_freezes`: 200 -> 500
  - 同步 `close_team_dash_without_out_team_sign` ROI 扩大 (inverse: 没"确定"就 exit)
- **narutomobile 没法解决弹窗卡住的问题**:
  - 我们 merged.json 跟 v1.3.41 100% 一致, 包括 `close_team_dash_out_team_sign` (OCR 找"确定" 关闭退队弹窗)
  - 弹窗本身 narutomobile 用 `SharedNode/confirm.png` + `confirm_small.png` 模板处理
  - 卡住真因: OCR 在弹窗 UI 漂移时找不准"确定" — 我们扩大 ROI 容错, 不依赖 narutomobile 之外的方案
  - 已知: 真机 UI 漂移需要重新截图, 文件层面无差异可抄

### 2026-07-21 21:06 反馈合入 (弹窗通知删除 + 7 task 删除)
- **删弹窗通知功能**:
  - `agent/custom/sink.py`: 删 `NotificationSink` class (line 117-141)
  - `agent/custom/utils.py`: 删 `send_notification` function (line 93-113)
  - 保留 `AspectRatioChecker` (16:9 分辨率检查) — 还在用
- **删 7 个 task** (用户不要):
  - `start_up` (进入火影) - 启动游戏任务, GUI 启动已经在外面跑
  - `switch_account` (切换账号(beta))
  - `exit_naruto` (关闭火影手游APP)
  - `stronghold` (要塞)
  - `sky_ground` (天地)
  - `mini_game` (小游戏)
  - `joy_club` (心悦会员)
- **删 21 个 orphan options** (被删 task 引用的)
- **CurrentTasks** 跟着去重 (35 → 28, 每个 task 唯一)
- **最终 task 集合**: 28 task (v1.3.36 38 - 3 二级密码 - 7 用户不要 = 28)

### Changed
- **任务集合跟 `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.36` 同步**:
  - 加回: `招财` (get_copper basic) + `小队突袭` (team_dash basic)
  - 删除: `secondary_password_open` (v1.3.36 没有)
  - 保留删除: `shop` / `buy_energy` / `[二级密码]` 双重 entry (v1.3.36 也没有, "防扩" 决策)
- **任务 Chinese name 跟 v1.3.36 统一** (24 处):
  - 启动游戏 → 进入火影, 一键助手 → 轻松助手, 轻松赛季 → 轻松季(beta)
  - 赠送体力 → 送体力, 组织签到 → 组织, 招募 → 免费招募
  - 每日签到 → 月签到和一乐拉面, 刷碎片 → 刷体力(精英副本)
  - 集会所 → 任务集会所(beta), 忍术对战 → 忍法帖, 周胜 → 决斗场(连点器)
  - 火影情报社 → 火影情报社(beta), 邮件领取 → 邮箱, 活跃奖励 → 活跃宝箱
  - 切换账号 → 切换账号(beta), 退出火影 → 关闭火影手游APP
  - 天空之地 → 天地 (以 v1.3.36 真值为准, 不是之前的"天地战场")
  - 叛忍 → 叛忍(beta), 更多玩法 → 更多玩法(beta), 欢乐会员 → 心悦会员
  - 黑市商人 → 黑市商人(beta), 调试 → Debug, 清理备份 → 日志文件清理
  - 收尾 → 完成标记
- **option key 改名** (11 处):
  - `一键助手扫荡` → `轻松助手扫荡` (task 名改了跟着改)
  - `允许MAN管理QQ和火影信息` → `允许MAN管理qq和火影信息` (case)
  - `拒绝QQ获取火影信息` → `拒绝qq获取火影信息` (case)
  - 10× `忍者指南寻找X` → `忍界指引寻找X` (kanji fix)
- **35 个 orphan options 删除** (option 块): `兑换玉石*` / `玉石*号位*` / `铜币招财` / `招财轮次` / `招财次数` / `忍者指南寻找冠军送礼` / `忍者指南寻找集会所` / 等
- **CurrentTasks** (left-sidebar task list) 同步: 24 个 Chinese name 改名 + 删除 3 个不存在的 entry (商店一键/购买体力/二级密码)

### Migration warning
- 老用户保存的配置里, `邮件领取` / `组织签到` / `每日签到` 等旧 Chinese name 不再是 `TASK_MAPPING` 的 key
- `resolve_entry()` fallback 行为: 未知 task_id 原样返回, 任务可能被静默跳过或执行出错
- 建议: 用户升级后清空 `config/instances/default.json:CurrentTasks` 让 regen 重写 (TODO 工具)

### Not synced (intentional, per "防扩" 决策)
- `黑市二级密码` / `叛忍二级密码` (v1.3.36 新增 [二级密码] options): 不引入
- `display_pointer_location` / `display_touch` (v1.3.36 英文): 保留中文 `显示指针位置` / `显示触摸`
- description 字段富文本格式: 没改
- task 默认勾选 (default_check) 完全相同: 不强制
  - 例外: `complete` (完成标记) 我们 `default_check=true`,v1.3.36 `false`。有意保留 — 我们的 `complete` task 是真的标"今日跑完",默认开方便用户验收。v1.3.36 把完成标记归到 nil 节点(无 task),所以 v1.3.36 用户的完成标记由"未跑任何 task"隐式表达。我们的语义不同,**保留 true**。
- interface.json task 顺序: 跟 v1.3.36 不一致 (我们 start_up 后立刻是 get_copper, v1.3.36 是 easy_helper)

### Fixed (post-reviewer)
- **C-1**: `interface.json` 重复 `leaderboard` task (39→38),reviewer 抓到,已去重
- **C-2**: `config/instances/default.json:CurrentTasks` 27 行旧名 同步到新 name (在 7a1771a sync commit 里一起修了)
- **I-1**: `complete` task default_check 与 v1.3.36 不一致 — 见上面 Not synced 例外说明
- **I-2**: 32 个 orphan options 删除 (与 sync commit 一起;reviewer 提的 35 含早期合并,实际 32)
- **I-3/I-4**: `display_*` 英文键 / 二级密码 options — 防扩跳过
- **M-1**: `task_registry.yaml` 描述用 `TaskItems[name]` 重生成
- **M-2**: 本 CHANGELOG Unreleased section
- **M-3**: `tests/test_main.py` 加 `test_interface_and_default_task_count_in_sync` 防 C-1 复发
- **M-4**: `docs/MAF_CONFIG_FIX.md` 路径 (frontend/MFAAvalonia → 项目根) 全面更新
- **额外**: 补 `忍界指引寻找任务集会所` option def (mission_office 引用但 option 块无 def)

## [0.7.1] - 2026-07-18 (开源自检 + 模块合并)

### Added
- **`agent/` Python 子进程模块** — MFAAvalonia (C# GUI) 启动时自动 spawn 的 Python 进程,负责注册 `NonlinearSwipe` / `GoIntoEntryByGuide` / `CleanLogs` 三个 custom action
  - 通过 MaaAgentServer/MaaAgentClient IPC 接 C# 调
  - 直接 API 模式 (Direct API) 和 Agent 模式 (子进程) 共享 `maafw_bridge._actions_core` 核心逻辑
- **`maafw_bridge/_actions_core.py`** — 从 `custom_actions.py` 抽出的核心逻辑(方案 A),Direct API + Agent 双模式都调它
  - `go_into_entry_by_guide_run` 完整版(narutomobile 算法 1:1 移植,5 步 OCR + 3 次 click)
  - `clean_logs_run` 维护性 task(清理旧 session debug + MFAAvalonia backup)
- **`config/maa_option.json`** — MaaFramework 启动选项配置
- **`config/schedule.json`** — 任务跑批方案(从 `schemes/daily.json` 迁移)
- **`tools/bundle_python.py`** — Python 打包工具(python-build-standalone 下载,用于 MFAAvalonia 部署)

### Changed
- **模块合并(4 项)**:
  - `state/` → `state_machine/`(`GameState` 枚举移入)
  - `recognizer/` → `recognition/`(`PageRecognizer` 移入)
  - `logging_ext/` → `core/run_context.py`(`RunContext` 移入)
  - `schemes/daily.json` → `config/schedule.json`
- **`core/base_task.py:pre_flight`** — 简化为 no-op(直接 return True)
  - 旧版委托 `CommonActions.ensure_game_in_foreground()`,新版由 MaaFramework merged.json pipeline 接管
  - docstring 明确说"前台守护已从 Python 移走,pipeline 接管" + 解释原因
- **`tasks/task_engine_maafw.py`** — `list_supported_tasks()` 改用 `list_supported_entries()`(避免同 entry 重复跑)
- **`pyproject.toml`**: `packages =` 更新(移除 `logging_ext/` / `recognizer/` / `state/`,加入 `agent/`)
- **`README.md` / `CONTRIBUTING.md`**: 反映新的目录结构(注: docs/operation_flows.md 已在 0.7.1 之后清理时删)
- **测试更新**:
  - `test_custom_actions.py` (5 个):适配 `_actions_core.go_into_entry_by_guide_run` 3-click 算法
  - `test_clean_logs.py` (2 个):硬编码路径改为 `Path(__file__).resolve().parent.parent`,`clean_logs` entry 缺失时 skip(留作回归保险)
  - `test_task_mapping.py` (1 个):任务计数从 `default.json` TaskItems 动态读取,不再 hardcode 21
  - `test_pipeline_overrides.py` (1 个):改为用 `monkeypatch` + `tmp_path` 测 fallback 行为(MFAAvalonia 清空 `ResourceOptionItems` 后 `_FALLBACK_YES_OPTIONS` 仍生效)

### Removed
- **`logging_ext/`** 整个目录(2 个文件)
- **`recognizer/`** 整个目录(2 个文件)
- **`state/`** 整个目录(2 个文件)
- **`schemes/`** 整个目录(只有 `daily.json`,已迁到 `config/schedule.json`)
- **`recovery/`** 整个目录(同次 P2 清理删除,本段"Changed"中原提到的 `recovery/recovery_manager.py` 3 个 None-guard 修改在删除前未保留,故从 CHANGELOG 移除相关条目)

### 用户操作变更
- 无破坏性变化 — 所有 CLI 命令(`--xxx-real` / `--maafw-task` / `--daily-all` / `--gui`)保持兼容
- `--daily-all` 现在读 `config/schedule.json`(原 `schemes/daily.json`)

## [0.7.2] - 2026-07-19 (代码质量 + MVP 标记)

### Added
- **`maafw_bridge/pipeline_overrides.py: v3 auto-sync`** — 8 个 entry override 从 frontend `default.json` 选中的 option case 自动加载,Python 端不再 hardcode
- **`tools/fake_green_detect.py: V2`** — 除静态 chain walk 外,新增:
  - 忍者指引 override 节点 expected / biz_next 一致性检查(20 条 warning,已知可接受)
  - 工具任务(9 条:`start_up` / `switch_account` / `buy_energy` / `shop` / `easy_season` / `joy_club` / `secondary_password_open` / `shugyou_no_michi` / `black_market_merchant`)显式归类为 BIZ(避免误报假绿)
  - 已知 broken 标注(`point_race` / `secret_realm` 业务模板匹配不稳定)

### Changed
- **3 轮 code-quality 重构 (OPT-1..OPT-10)**:
  - Round 1 (`6fd19fe`): OPT-4/7/8/5/6 — 小型安全项
  - Round 2 (`2c9de59`): OPT-1/2/3 — 高影响删除
    - `main.py` 1383 → 297 行(-78%)
    - 删 4 个 `core/` 死模块(`window_manager` / `screenshot_manager` / `base_task` / `state_machine`)
    - 删 6 个 `--xxx-real` + `cmd_weekly_signin_real` + `--capture-test` / `--smoke-test` / `--list-windows` / `--activate-window` CLI flag
    - 拆 `core/task_result.py`(从已删 `base_task.py` 抽出 `TaskStatus` / `TaskResult`)
  - Round 3 (`bd977bc`): OPT-9/10 — 长期价值项
    - `fake_green_detect.py` 静态分析工具
    - `tools/audit_templates.py` 重写自 `validate_templates.py`(更准的孤儿/缺失检测)
- **MVP 标记 (`e77af55`)** — 真活儿,不是空 tag:
  - 加 `.github/workflows/test.yml` CI 跑 pytest
  - 加 ISSUE/PR 模板
  - `fake_green_detect.py` v2 实现 override-mismatch 检查
- **`schedule.json` / `device_config.yaml` 删** (OPT-5) — 5 个 `test_config_manager.py` 引用 + 2 个 `test_task_mapping.py` schedule.json 测试同步删
- **`pre_gui_smoke.py` / `cmd_check` step 1** 用 Pydantic `ConfigManager` 替换旧 `ConfigParser`

### Removed
- 20 个 `test_base_task.py` 死测试(`base_task.py` 已删)
- `test_state_machine.py` 整个文件(`state_machine.py` 已删)
- 3 个 schedule.json 测试(`schedule.json` 已删)
- `tests/_mock_adb.py` (自包含 mock,无人 import)

### Stats
- 文件数: 9 → 8 测试文件
- 测试函数: 129 → 117 (净 -12,-20 dead + 11 new CLI 测试)
- 净代码行: -4115(纯删除重构,无功能变更)

## [Unreleased] - 2026-07-11 (前端整合 + UI 清理)

### Added
- **前端 `MFAAvalonia` 接入** — 桌面 GUI 不再内置 PySide6,改用 MaaFramework 官方 Avalonia 客户端
  - 用户从 [MaaFramework releases](https://github.com/MaaXYZ/MaaFramework/releases) 下载到 `frontend/MFAAvalonia/`(`start.bat` 启动时打印下载链接)
  - `frontend/MFAAvalonia/` 已加 `.gitignore`(234 MB 二进制不进 git)
  - `frontend/.gitkeep` 保留目录结构,提示用户下载位置
  - `start.bat` / `start_cli.bat` 新增 — GUI / CLI 启动器,自动检测 .NET 10 Desktop Runtime
- **`main.py --gui` / 默认行为**: 无参数 / `--gui` 都启动 MFAAvalonia 桌面客户端
- **`README.md`**: 加 GUI 启动段 + 目录树更新 + MFAAvalonia 架构图

### Removed
- **整个 `ui/` 目录**(15 个 py 文件,114.8 KB)— 自研 PySide6 桌面 GUI(随本次 commit 删除)
- **3 个 GUI 相关测试**(随本次 commit 删除):
  - `tests/test_phase5_pipeline.py`(PySide6 dependent)
  - `tests/test_config_dialog.py`(PySide6 dependent)
  - `tests/test_scheme_manager.py`(依赖已删 ui.scheme_manager)
- **`PySide6>=6.5`**: 从 `pyproject.toml` 移除(运行时不再需要 Qt)
- **空 schemes 文件**: `schemes/event.json` / `schemes/weekly.json`(无人引用,占位符,已 trash 到回收站)
- **OCR 模型副本**: `resources/ocr_models/{README.md, det.onnx, keys.txt, rec.onnx}`(15 MB,改用 `resources/narutomobile/model/ocr/`,SHA256 验证一致)
- **死代码** `_SimpleRunReport`(`tasks/task_engine_maafw.py` 新增但全项目无人引用)

### Changed
- **OCR 模型路径**(`recognition/ocr_matcher.py`): 从 `resources/ocr_models/` 改为 `resources/narutomobile/model/ocr/`
- **`LICENSE`**: 从 MIT 切换为 AGPL-3.0-only(与上游 MaaFramework + narutomobile 模板授权兼容)
  - 版权行: `naruto-auto-daily — 火影忍者手游日常任务自动化工具 / Copyright (C) 2026  naruto-auto-daily contributors`
  - `pyproject.toml` license 字段同步更新
- **`pyproject.toml`**: `[tool.pytest.ini_options]` 调整 ignore / deselect 项(从 3 项保留,符合当前测试矩阵)
- **`main.py`**: 模块 docstring + argparse description + epilog 三处对齐 — 都反映"默认启 MFAAvalonia GUI"
- **`README.md`**: 全面重写(28 task 表格 + MFAAvalonia 架构图 + 启动说明)
- **`CHANGELOG.md`**: 拆分 4 个 `[Unreleased]` 为版本段,符合 Keep-a-Changelog 规范

### Preserved (保留)
- **`main.py`**: CLI 入口(1383 行),所有 `--xxx-real` / `--maafw-task` / `--maafw-list` / `--daily-all` 命令保留
- **`tasks/`**: 28 业务 task + `MaaTaskEngine`(详见下方 [0.7.0] 段)
- **`maafw_bridge/`**: MaaFramework 5.10.4 Python binding
- **`resources/narutomobile/`**: 24.9 MB 资源包(`pipeline/merged.json` + 786 张 PNG 模板 + OCR 模型)
- **`core/` / `device/` / `recognition/` / `recognizer/` / `recovery/` / `state/` / `state_machine/` / `logging_ext/`**: 业务支撑模块
- **`config/schedule.json`**: 5 task 跑批方案(`mail` / `liveness` / `group_signin` / `daily_signin` / `recruit`)
- **`tests/`**: 24 个测试文件(2026-06-30 阶段 7 时 27 个 - 3 个 PySide6 相关删除 = 24 个)

### 用户操作变更
- **老 CLI 用户**: `python main.py --mail-real` / `--daily-all` 不变
- **新 GUI 用户**: 下载 MFAAvalonia 到 `frontend/MFAAvalonia/` 后双击 `start.bat`
- **打包发布**: 无需 build.py(本项目源码分发),MFAAvalonia 自己维护 exe 发布

### Fixed (2026-07-14 跟进)
- **MFAAvalonia `interface.json` option 块缺失** — 跑批时 4 张 on_error 截图(`up_swipe_for_ninja_guide_find_funtion_entry` × 3 + `energy_entry` × 1),任务报告"成功"但实际走 swipe 兜底,OCR 找不到"装备"等默认文字
  - 根因: 上游 MaaAutoNaruto v1.3.41 的 `interface.json` 138 KB,本项目 2.3 KB 缺 `option` 块(`merged.json` 和模板完全相同)
  - 修复: 选择性复制 10 个相关 option(覆盖 19 个 task 中的 9 个),`ninja_guide_find_funtion_entry.expected` 从默认 `["装备"]` 动态覆盖为实际任务入口文字(如 `["组织"]` / `["积分赛"]` / `["秘境"]` 等)

### Changed (2026-07-14 全面清理 — 用户审计 18 项 P0/P1/P2/P3)

#### P0 阻塞 (3 项全修)
- **`cmd_weekly_signin_real` 迁移到 MaaTaskEngine** — 走 `activity` entry(同 `daily_signin`),不再用旧自研 `WeeklySigninTask`
- **`onnxruntime` 加到 `pyproject.toml`** — `recognition/ocr_matcher.py:36` 真的在用(用户 P0#2, 但只 `onnxruntime`; `rapidocr-onnxruntime` 是 `tasks/navigator.py` 用,navigator 已删所以不用加)
- **27 个死 `tasks/*_task.py` 删** — 用户说 19, 实际 27, 加上 `navigator.py` / `pipeline_runner.py` / `pure_actions/` 共 32 个

#### P1 严重冗余 (5 项全修)
- **`resources/templates/` (10 MB, 770 PNG) 删** — 跟 `resources/narutomobile/image/` 重复, 只旧自研 Navigator 在用
- **Phase 2/3/4 demos ~410 行删** — `cmd_phase2` / `cmd_phase3` / `cmd_phase4` 等 8 个 demo 函数 + `_assemble_real_runner` (拖死 `tasks/assembly.py` / `common_actions.py` / `task_engine.py` / `weekly_signin_task.py` 4 个文件)
- **5 个 `cmd_*_real` + `cmd_weekly_signin_real` 合 1 个 `_run_real_task_impl`** — 走 `--run-task <id>` 通用参数, `TASK_MAPPING` 20 个 task_id 复用 (`weekly_signin` 加到映射, 走 `activity` entry)
- **9 个引用已删模块的测试删** — `test_common_actions.py` / `test_daily_signin_task.py` / `test_navigator_jumpback.py` / `test_phase2-4_pipeline.py` / `test_pure_go_into_entry.py` / `test_retry_manager.py` / `test_task_engine.py` / `test_group_signin.py`
- **`config/app_config.yaml` 修**:
  - `version: 0.6.0 → 0.7.0` / `phase: 6 → 8`
  - `adb_path: "C:\\tmp\\android-sdk\\..." → ""` (改走 PATH)
  - `default_serial: "127.0.0.1:7555" → "127.0.0.1:16384"` (MuMu 12 实际端口)
  - `templates_dir: "resources/templates" → "resources/narutomobile/image"` (旧 dir 删了)

#### P2 文档/配置过时 (6 项, 5 修 1 跳过)
- **README 5 个 broken refs 删** — `PROJECT_PLAN.md` / `COMPLETION_REPORT.md` / `operation_flows.md` / `calibration/` / `game_wiki/` 全不存在
- **5 个 `common_actions.py` TODO stub 删** — 整个 `common_actions.py` 文件删(只 Phase 2/3/4 demos 用, 现都删了)
- **`__version__` 统一到 0.7.0** — `core/device/recognition/recognizer/state/state_machine/tasks` 之前是 0.1.0-0.3.2 错位
- **`docs/MAF_CONFIG_FIX.md` commit** — 之前 untracked
- **`.vscode/` audit 修正** — 用户说被跟踪, 实际**没**被 git 跟踪, 这条不做
- **`docs/operation_flows.md` 26 KB Phase 6 旧引擎** — 用户提到但**不删**(可能用户还想要历史参考, 不强行删)

#### P3 优化 (4 项, 2 修 2 跳过)
- **`core/screenshot_utils.py` 删** — 零引用
- **`state/types.py` 删** — 1 行 `GameContext = ExecutionContext` 别名
- **`recognition/` + `recognizer/` 合并** — 用户提到但**不动**(重构范围太大, 留作 follow-up)
- **`frontend/MFAAvalonia/debug/` 23 MB 清** — `maafw.log` 10.5 MB + 截图 12 MB 删

#### 净效果
- **代码量**: `main.py` 1405 → 736 行(-669, -48%); `tasks/` 35 文件 → 2 文件; `tests/` 24 → 15 文件
- **磁盘**: 删 `resources/templates/` 10 MB + `debug/` 23 MB = **33 MB 释放**
- **依赖**: 删 `rapidocr-onnxruntime`(无用户), 加 `onnxruntime>=1.18`(ocr_matcher 真用)
- **测试**: 192/192 pass, 0 fail, 0 引用死代码
- **CLI 兼容**: `--run-task <id>` 替代 6 个 `--<task>-real` + `cmd_weekly_signin_real`; `--list-tasks` 替代 `--maafw-list` 重复
  - 来源: `https://github.com/duorua/MaaAutoNaruto` v1.3.41 (AGPL-3.0,与本项目许可证兼容)
  - 详见 `docs/MAF_CONFIG_FIX.md`
  - **注意**: `frontend/MFAAvalonia/interface.json` 在 `.gitignore` 内 (234 MB 二进制),此修复为本地操作,重装 MFAAvalonia 时需重新应用

## [0.7.0] - 2026-06-30 (Phase 7 完成)

### Added
- **28 个业务 task**(从 `MaaAutoNaruto-win-x86_64-v1.3.41` 全抄):
  - **基础 7 任务**:mail / daily_signin / weekly_signin / liveness / recruit / activity / group_signin
  - **新增 21 任务**:monthly_signin / rich_room / team_dash / secret_realm / survival_challenge / shugyou_no_michi / stronghold / mission_office / advanture / elite_instance / point_race / rebel_ninja / use_energy / give_energy / leaderboard / more_gameplay / ninja_book / weekly_win / sky_ground / easy_helper / hundred_ninja
- **`tools/gen_11_tasks.py`** — 批量 task 生成器(统一 ROI / 模板 / 8 节点 pipeline)
- **`docs/standards/TASK_TEMPLATE.md`** — task 模板规范
- **`docs/standards/TEMPLATE_NAMING.md`** — 模板命名规范
- **`CONTRIBUTING.md`** — 多 AI 协作开发规范
- **`LICENSE`** — MIT License(后续在 [Unreleased] 改为 AGPL-3.0)
- **`workgroup.md` → `docs/collaboration/WORKGROUP.md`** 链接(实际还在根,待迁移)
- 任务生成注释来源 + 抄自narutomobile 日期标注

### Changed
- **`tasks/monthly_signin_task.py`** — 用 narutomobile Activity.json ROI 重写
- **`tasks/group_signin_task.py`** — 用 narutomobile Group.json ROI 重写(原本错误的 award 中心 ROI 已修)
- **`dryrun_runner.py` line 28** — `SERIAL` 从 `127.0.0.1:16384` 改为 `127.0.0.1:5555`(MuMu 端口变化)
- **`config/app_config.yaml`** — `default_serial` 从 7555 备注为 5555
- **`main.py` header** — 从 "Phase 6 真实日常任务接入" → "Phase 7 narutomobile 全抄 + 工程治理"
- **`tasks/*.py`** — 加 "生成日期:2026-06-30 + 来源:MaaAutoNaruto v1.3.41" 注释
- **`tasks/pipeline_runner.py`** — 所有 task 的 on_error 不再 silent `verify_done`(失败真报)

### Deprecated
- `dryrun_v2.py` / `dryrun_v3.py` — 已 trash
- `scripts/` 空目录 — 已 trash
- `resources/templates/narutomobile_ref/` — 5 个旧模板 已 trash(已被 actions/ 覆盖)
- 6 个空 templates 子目录(home_entries/liveness/loading/shared/startup/unknown) — 已 trash

### Fixed
- **monthly_signin**:之前误命中 activity/page title.png(活动页"活动"标题),改为 mouthly_sign_undone.png 模板匹配正确 ROI
- **group_signin**:之前 "group_signin blocked" 完全是瞎编(user 一直在组织里);真实入口改为 reward 中心 → 组织祈福 任务卡 → 立刻前往 → 焚香祈福

### Removed
- `_tmp_a5_list.py` 根目录临时文件
- 13 个 `__pycache__/` 编译缓存
- `logs/*.bak` 3 个备份文件
- 临时 dryrun_v2.py / dryrun_v3.py

### Verified
- 680 个 MaaAutoNaruto v1.3.41 模板复制覆盖到位(`batch_copy.py`)
- 18 个关键 ROI 与旧版 `narutomobile-main` 一致

## [0.6.0] - 2026-06-27

### Added
- Phase 6 真实日常任务接入 — 6 个 task(mail/liveness/signin/activity/...)
- Phase 5 PySide6 GUI(后续在 [Unreleased] 2026-07-11 改为 MFAAvalonia 官方 UI)
- Phase 4 RetryManager / RecoveryManager
- Phase 3 TaskEngine / DailySigninTask
- Phase 2 ADBClient / TemplateMatcher / PageRecognizer
- Phase 1 ConfigManager / Logger / WindowManager / ScreenshotManager / BaseTask / Scheduler

### Files
- ~32 Python files (~5000 lines)
- 24 tests
- ~200 templates
