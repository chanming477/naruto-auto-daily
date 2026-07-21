# Last-Week Code Review (2026-07-20)

**范围:** 最近一周 30 个 commit (7 天内),BASE=`08c7d17`,HEAD=`d5e087e`
**拆 3 次 review:** 详见各小节
**总规模:** 108 文件,+44k/-61k 行
**整体判断:** Ready to merge with fixes(2 Critical + 13 Important + 25 Minor)

---

## 概览

| Review | 范围 | Commits | Critical | Important | Minor |
|--------|------|---------|----------|-----------|-------|
| [R1](#review-1-oss-cleanup--p0p1p2p3) | OSS cleanup + P0/P1/P2/P3 audit | 3 (7c9d650..be96937) | 0 | 3 | 10 |
| [R2](#review-2-code-quality--mvp) | code-quality refactor + MVP | 8 (c346ed3..e77af55) | **1** | 5 | 8 |
| [R3](#review-3-docs--ci--14项优化) | docs + CI + bundle + 14项优化 | 17 (895474e..d5e087e) | **1** | 5 | 7 |
| **合计** | | **30** | **2** | **13** | **25** |

---

## 🔴 Critical(2,必须修)

### C1 — MVP 标记跟 quality gate 打架(R2)

**文件:** `tools/fake_green_detect.py`
**问题:** `bd977bc`(OPT-9 commit)声称"0 假绿",但同一个 `fake_green_detect` 工具在 `e77af55`(MVP 标记)时报告 **9 假绿 + 20 override mismatch**。要么 V1 错了,要么 V2 在过度报警。
**影响:** MVP 标记建立在错误/未校准的 quality gate 上,失去"打 MVP"的意义。
**修复:**
- 选项 A:扩 `BIZ_HINTS` 把 `start_up` / `switch_account` / `buy_energy` / `shop` / `joy_club` / `secondary_password_open` / `easy_season` / `shugyou_no_michi` / `black_market_merchant` 归为工具任务(无需 BIZ 前缀)
- 选项 B:把 20 个 override mismatch 文档化为"已知可接受"(因 `merged.json` 用 `goto_<entry>_by_guide` 命名约定,而非 `ninja_guide_find_funtion_entry`)

### C2 — README FAQ 引导用户走错路(R3)

**文件:** `README.md:131`
**问题:** FAQ "Agent 注册失败" 排查指引要求用户检查 `agent/custom/reco.py` 和 `agent/custom/action.py`,但扁平化后实际是 `reco/base.py` 和 `action/base.py`。
**影响:** 用户遇到 exactly 这个 error 按指引排查会找不到文件,挫败感。
**修复:** 改成 `custom/sink.py` / `custom/reco/base.py` / `custom/action/base.py` / `main.py`,并在 FAQ 加一句"action/ 和 reco/ 现在是子包,不是单文件"。

---

## 🟡 Important(13,建议修后再打 tag)

### 扁平化残留(同主题,跨 review 反复出现)

| # | 文件 | 问题 | 来源 |
|---|------|------|------|
| I-1.1 | `tools/bundle_python.py:58-64` | `DEPS` 还列 `onnxruntime>=1.18`,但 `recognition/ocr_matcher.py` 已删 → bundle 多 100MB | R1 I-1 |
| I-1.2 | `tools/bundle_python.py:195-215` | `copy_agent_source()` 死函数,从未调用 | R3 I3 |
| I-1.3 | `tools/bundle_python.py:8,14,138,200,205,209,222` | docstring 还在引 `frontend/MFAAvalonia/` | R3 M1 |
| I-1.4 | `pyproject.toml:65` | `--ignore=frontend` 死配置,注释也过期 | R3 I2 |
| I-1.5 | `CONTRIBUTING.md:18,36` | 引 `frontend/MFAAvalonia/`(已删) | R3 I1 |
| I-1.6 | `CONTRIBUTING.md:33,34,46,47,52,53` | 引 `validate_templates.py` / `generate_template_manifest.py`(已删,实际是 `audit_templates.py`) | R2 I4 |
| I-1.7 | `docs/2026-07-20-cicd-release-design.md:16-18,31,54-56,62` | 设计文档写于扁平化前,引老路径 | R3 I4 |
| I-1.8 | `docs/operation_flows.md` | 引已删的 `RecruitTask` / `ShopTask` | R1 M-9 |
| I-1.9 | `maafw_bridge/__init__.py:14` | docstring 引已删的 `core.scheduler.Scheduler` | R1 M-4 |
| I-1.10 | `maafw_bridge/_actions_core.py:396,439` | 注释引 `frontend/MFAAvalonia/` | R3 M1 |
| I-1.11 | `maafw_bridge/pipeline_overrides.py:4,6` | docstring 引 `frontend/MFAAvalonia/` | R3 M1 |
| I-1.12 | `maafw_bridge/task_mapping.py:4,13,102` | docstring 引 `frontend/MFAAvalonia/` | R3 M1 |
| I-1.13 | `core/__init__.py:9,27` | `__all__` 还在 `"scheduler"`,docstring 树状图有 `└── core.scheduler` | R1 M-1 |
| I-1.14 | `config/task_registry.yaml:5-10` | header 还在讲已删的 `Scheduler` / `_NoopTask` | R1 M-5 |
| I-1.15 | `tasks/task_engine_maafw.py:10,105,117` | docstring 还在引 `RecoveryManager` | R1 M-7 |
| I-1.16 | `device/types.py:15` | docstring 引已删的 `ADBClient` | R1 M-8 |
| I-1.17 | `tests/__init__.py:8` | 引已删的 `test_pipeline.py` | R1 M-6 |

### 数字 / skipif / CHANGELOG 不一致

| # | 文件 | 问题 | 来源 |
|---|------|------|------|
| I-2.1 | `config/task_registry.yaml`(8) vs `default.json` TaskItems(43) vs `TASK_MAPPING`(47 task_ids) | `main.py:cmd_check` step 3 报"8 个任务",严重低估 | R2 I1 |
| I-2.2 | `README.md:102` | 架构图数字 1288 节点 / 786 PNG 模板过期,实际 1564 / 870 | R2 I2 |
| I-2.3 | `tests/test_task_mapping.py` + `tests/test_pipeline_overrides.py` | 13 个测试硬依赖 `frontend/MFAAvalonia/`,新 checkout 直接红 | R1 I-2 |
| I-2.4 | `CHANGELOG.md:33-40`(0.7.1 段) | 还写"recovery_manager 加 None-guard",但 `recovery/` 整个已删 | R1 I-3 |
| I-2.5 | `CHANGELOG.md` | 缺 `[0.7.2] - 2026-07-19` 段(code-quality 3 rounds + MVP) | R2 I3 |
| I-2.6 | `tools/fake_green_detect.py` | V1("0 假绿")vs V2("9 假绿")语义未校准 | R2 I5 |

---

## 🟢 Minor(25,顺手过一遍)

| # | 文件 | 问题 | 来源 |
|---|------|------|------|
| M-1 | `agent/main.py:22-23` | dev/deploy 两条路径完全重复,显然 typo | R2 M1 |
| M-2 | `LICENSE:1` vs `pyproject.toml:7` | SPDX 写法不统一(等价但不一致) | R3 M2 |
| M-3 | `requirements.txt:17` vs `pyproject.toml:24` | `notify-py` 一处注释掉一处 pin | R2 M3 |
| M-4 | `tests/test_main.py:81` | 注释"6 个保留命令"但实际断言 7 个 | R2 M5 |
| M-5 | `tools/fake_green_detect.py:80-93` | `keyword_to_entry` 手动映射表,加注释说明稳定性 | R2 M8 |
| M-6 | `docs/code-quality-optimization-plan.md:13,74,77-82` | 描述已解决的问题,加"已实施"标注 | R3 M3 |
| M-7 | `start_cli.bat:4-6` | 中文 echo 乱码(预先存在,非本次引入) | R3 I5 |
| M-8 | `agent/custom/reco/base.py:8` | docstring "来源: MaaAutoNaruto v1.3.41 reco.py" 应是 `reco/base.py` | R3 M6 |
| M-9 | `tests/test_main.py` 6 vs 7 命令 | 同 M-4 | R2 M5 |
| M-10 | `CONTRIBUTING.md:14` | `agent/` 描述准确,无需改 | R3 M4(无需 fix) |
| M-11..M-25 | 散点(略,见 R1/R2/R3 详细报告) | 略 | 略 |

完整 Minor 清单见各 review 详细输出(Mavis session 历史)。

---

## 跨 review 观察

**3 个 review 独立点出同一个模式:doc 滞后于代码。**
CONTRIBUTING/README/CHANGELOG 在每个 commit 都没同步更新,留到 review 阶段才暴露。建议:加 CI grep check 防复发(见 Block E)。

---

## 修复计划(明天执行)

### Block A — Critical + 数字(30 min, 2 文件)

- [ ] **A1** `tools/fake_green_detect.py`:扩 BIZ_HINTS 或文档化 9+20 为"已知可接受"
- [ ] **A2** `README.md:131` FAQ:`reco.py` → `reco/base.py`、`action.py` → `action/base.py`,加子包说明

### Block B — 扁平化残留(30 min, 9 文件)

- [ ] **B1** `tools/bundle_python.py`:删 `copy_agent_source()` + 删 `onnxruntime>=1.18` + 改 5 处 docstring
- [ ] **B2** `pyproject.toml:65`:删 `--ignore=frontend` + 删 stale 注释
- [ ] **B3** `CONTRIBUTING.md`:改 `frontend/MFAAvalonia/` → `interface.json` / `config/instances/default.json` + 3 个工具引用 → `audit_templates.py`
- [ ] **B4** `docs/2026-07-20-cicd-release-design.md`:加扁平化 appendix
- [ ] **B5** `docs/operation_flows.md`:删/改 `RecruitTask` / `ShopTask` 引用
- [ ] **B6** `maafw_bridge/{__init__.py, _actions_core.py, pipeline_overrides.py, task_mapping.py}` docstring 路径
- [ ] **B7** `core/__init__.py`:删 `__all__` 的 `"scheduler"`、docstring 树状图删 `└── core.scheduler`
- [ ] **B8** `config/task_registry.yaml` header 改写
- [ ] **B9** `tasks/task_engine_maafw.py:10,105,117` + `device/types.py:15` + `tests/__init__.py:8` docstring

### Block C — 数字 / skipif / CHANGELOG(20 min, 4 文件)

- [ ] **C1** 写脚本 `tools/regen_task_registry.py` 从 `default.json` TaskItems 重新生成 `config/task_registry.yaml`
- [ ] **C2** `main.py:cmd_check` step 3 改用 `default.json` TaskItems 计数
- [ ] **C3** `README.md:102` 1288/786 → 1564/870
- [ ] **C4** `tests/test_task_mapping.py` + `tests/test_pipeline_overrides.py` 加 `pytest.mark.skipif(not default_json.exists(), ...)`
- [ ] **C5** `CHANGELOG.md`:修 0.7.1 描述(删 `recovery_manager` 那条)+ 写 0.7.2 段

### Block D — Minor 散点(15 min)

- [ ] `agent/main.py:22-23` dev/deploy 重复路径
- [ ] `LICENSE` vs `pyproject.toml:7` SPDX 写法统一(选 `AGPL-3.0-only`)
- [ ] `requirements.txt:17` vs `pyproject.toml:24` `notify-py` 注释一致化
- [ ] `tests/test_main.py:81` "6 个" → "7 个"
- [ ] `tools/fake_green_detect.py:80-93` keyword_to_entry 加注释
- [ ] `docs/code-quality-optimization-plan.md` 已解决问题加 "已实施" 标注
- [ ] `start_cli.bat` 中文重存为 UTF-8 无 BOM(放最后)

### Block E — CI 防复发(15 min, 1 新文件)

- [ ] 新建 `.github/workflows/doc-coupling-check.yml`
- 扫描 `*.md` / `*.yaml` / `*.yml` / `*.toml` / `*.json`(排除 `interface.json` 和 `merged.json`)里的以下关键字:
  - `RecoveryManager` / `RetryManager` / `Recovery` / `recovery/`
  - `state_machine` / `state/`
  - `scheduler.py` / `Scheduler` / `core.scheduler`
  - `frontend/MFAAvalonia` / `MFAAvalonia/`
  - `adb_client` / `ADBClient`
  - `page_recognizer` / `PageRecognizer`
  - `navigator` / `pipeline_runner`
- 任何引用 → fail
- 豁免机制:`# noqa: doc-coupling` 注释

### 修完跑回归

```powershell
cd D:\火影自动日常
pytest tests/ --ignore=tests/test_task_mapping.py --ignore=tests/test_pipeline_overrides.py
python main.py --check
python tools/pre_gui_smoke.py
git diff --stat  # 检视改动范围
```

---

## 关联 session 历史

3 个 review 完整输出在本 session 的对话历史里:
- Review 1 (bg: 在 session mvs_6cd31a7fe52840a28e0ed6394c49f403 turn 期间)
- Review 2 (bg task: `bg_b876fb7e-f3ec-4885-8fc7-cd0c6d9229dd`)
- Review 3 (bg task: `bg_a65dd5db-23a1-4652-a449-8469dfb774ae`)

---

## 复盘 / 教训

1. **Doc 滞后于代码是本次 review 的主旋律**(17/40 个 issue 是 doc 滞后),不是单次失误,是流程缺口 → Block E
2. **MVP 标记应自检 quality gate 输出一致性**(R2 C1)→ 流程:tag 前必跑 `fake_green_detect` 并贴输出
3. **扁平化这类大重构应在 commit 里同时改所有引用方**(本次 17 处 docstring/注释遗漏)→ 用 `git grep` 扫一遍再提交
4. **删模块前要列完整 impact map**(`recovery/` 删了,`main.py:cmd_check` / `pre_gui_smoke` / `CHANGELOG` 还在用)
5. **数字/统计数据应在文档里用相对量**("~1.5K 节点" 而非"1288"),不然每次更新都要追
