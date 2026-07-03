# Changelog

所有重要变更记录在此。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased] - 2026-06-30

### Added (新增)
- **28 个业务 task**(从 `MaaAutoNaruto-win-x86_64-v1.3.35` 全抄):
  - **基础 7 任务**:mail / daily_signin / weekly_signin / liveness / recruit / activity / group_signin
  - **新增 21 任务**:monthly_signin / rich_room / team_dash / secret_realm / survival_challenge / shugyou_no_michi / stronghold / mission_office / advanture / elite_instance / point_race / rebel_ninja / use_energy / give_energy / leaderboard / more_gameplay / ninja_book / weekly_win / sky_ground / easy_helper / hundred_ninja
- **`tools/gen_11_tasks.py`** — 批量 task 生成器(统一 ROI / 模板 / 8 节点 pipeline)
- **`docs/standards/TASK_TEMPLATE.md`** — task 模板规范
- **`docs/standards/TEMPLATE_NAMING.md`** — 模板命名规范
- **`CONTRIBUTING.md`** — 多 AI 协作开发规范
- **`LICENSE`** — MIT License
- **`workgroup.md` → `docs/collaboration/WORKGROUP.md`** 链接(实际还在根,待迁移)
- 任务生成注释来源 + 抄自narutomobile 日期标注

### Changed (变更)
- **`tasks/monthly_signin_task.py`** — 用 narutomobile Activity.json ROI 重写
- **`tasks/group_signin_task.py`** — 用 narutomobile Group.json ROI 重写(原本错误的 award 中心 ROI 已修)
- **`dryrun_runner.py` line 28** — `SERIAL` 从 `127.0.0.1:16384` 改为 `127.0.0.1:5555`(MuMu 端口变化)
- **`config/app_config.yaml`** — `default_serial` 从 7555 备注为 5555(由代码改)
- **`main.py` header** — 从 "Phase 6 真实日常任务接入" → "Phase 7 narutomobile 全抄 + 工程治理"
- **`tasks/*.py`** — 多文件加 "生成日期:2026-06-30 + 来源:narutomobile v1.3.35" 注释
- **`tasks/pipeline_runner.py`** — 所有 task 的 on_error 不再 silent `verify_done`(失败真报)

### Deprecated (即将删除)
- `dryrun_v2.py` / `dryrun_v3.py` — 已 trash 入回收站
- `scripts/` 空目录 — 已 trash
- `resources/templates/narutomobile_ref/` — 5 个旧模板 已 trash(已被 actions/ 覆盖)
- 6 个空 templates 子目录(home_entries/liveness/loading/shared/startup/unknown)— 已 trash

### Fixed (修 Bug)
- **monthly_signin**:之前误命中 activity/page title.png(活动页"活动"标题),改为 mouthly_sign_undone.png 模板匹配正确 ROI
- **group_signin**:之前 "group_signin blocked" 完全是瞎编(user 一直在组织里);真实入口改为 reward 中心 → 组织祈福 任务卡 → 立刻前往 → 焚香祈福

### Removed (清理)
- `_tmp_a5_list.py` 根目录临时文件
- 13 个 `__pycache__/` 编译缓存
- `logs/*.bak` 3 个备份文件
- 临时 dryrun_v2.py / dryrun_v3.py

### Verified (验证)
- 680 个 narutomobile v1.3.35 模板复制覆盖到位(`batch_copy.py`)
- 18 个关键 ROI 与旧版 `narutomobile-main` 一致

## [0.6.0] - 2026-06-27

### Added
- Phase 6 真实日常任务接入 — 6 个 task(mail/liveness/signin/activity/...)
- Phase 5 PySide6 GUI
- Phase 4 RetryManager / RecoveryManager
- Phase 3 TaskEngine / DailySigninTask
- Phase 2 ADBClient / TemplateMatcher / PageRecognizer
- Phase 1 ConfigManager / Logger / WindowManager / ScreenshotManager / BaseTask / Scheduler

### Files
- ~32 Python files (~5000 lines)
- 24 tests
- ~200 templates
