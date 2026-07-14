# Changelog

所有重要变更记录在此。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

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
- **`schemes/daily.json`**: 5 task 跑批方案(`mail` / `liveness` / `group_signin` / `daily_signin` / `recruit`)
- **`tests/`**: 24 个测试文件(2026-06-30 阶段 7 时 27 个 - 3 个 PySide6 相关删除 = 24 个)

### 用户操作变更
- **老 CLI 用户**: `python main.py --mail-real` / `--daily-all` 不变
- **新 GUI 用户**: 下载 MFAAvalonia 到 `frontend/MFAAvalonia/` 后双击 `start.bat`
- **打包发布**: 无需 build.py(本项目源码分发),MFAAvalonia 自己维护 exe 发布

## [0.7.0] - 2026-06-30 (Phase 7 完成)

### Added
- **28 个业务 task**(从 `MaaAutoNaruto-win-x86_64-v1.3.35` 全抄):
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
- **`tasks/*.py`** — 加 "生成日期:2026-06-30 + 来源:narutomobile v1.3.35" 注释
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
- 680 个 narutomobile v1.3.35 模板复制覆盖到位(`batch_copy.py`)
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
