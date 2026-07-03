# Mavis + DeepSeek 协作群

> **用途**:Mavis 和 DeepSeek 协作完成《火影忍者手游》自动日常项目(Naruto Auto Daily)
> **创建时间**:2026-06-29
> **主持人**:user
> **项目根目录**:`D:\\火影自动日常`
> **项目代码仓库**:`D:\\火影自动日常`(workspace)

---

## 📌 协议

- 每条消息以 `#### Mavis` / `#### DeepSeek` / `#### user(协调)` 开头
- 每个回合以 `### YYYY-MM-DD HH:MM 主题` 分隔
- user 负责把 DeepSeek 的回复**复制粘贴**到对应 `#### DeepSeek` 位置
- 不要再拆出新文件,整个对话累积到这一个文件
- 引用资料用相对路径(相对 `D:\\火影自动日常\\`)
- 写代码 / 改代码是 **Mavis** 负责(DeepSeek 只出设计/算法,代码由 Mavis 实施)
- **Mavis**: 直入代码,显式拆 11 节点 task,每步 ROI 配 tap_offset
- **DeepSeek**: 长 case 分析,根因诊断(Q1: 红点 vs UI 变更)
- **user**: 指挥,提供 2 张截图锚定入口路径,纠正误解

**会议节奏**:
- 每个回合聚焦 **1-2 个具体问题**
- DeepSeek 回答 → Mavis 跑真机验证 → 把结果反馈到下一回合
- 不在群里贴大段代码 → 提到文件路径即可

---

## 🎯 项目一句话

**ADB 控制 MuMu 模拟器 + 全图模板匹配**(V1.2 §1.2.0),自动跑《火影忍者手游》28 个日常任务(邮件 / 每日签到 / 活跃 / 招募 / 每周签到 / 活动 / 组织祈福 / 每月签到 / 丰饶之间 / 小队突袭 / 秘境探险 / 生存挑战 / 修行之路 / 要塞 / 任务集会所 / 冒险 / 精英副本 / 积分赛 / 叛忍 / 使用体力 / 赠送体力 / 排行榜 / 更多玩法 / 忍者书 / 周胜 / 天地 / 简单助手 / 百忍),**阶段 1-7 渐进推进**(PROJECT_PLAN v1.4 + 工程治理 24 项完成)。

## 👥 角色分工

| 角色 | 头衔 | 职责 | 工具 | 不做什么 |
|---|---|---|---|---|
| **司机** | **Mavis**(我) | 实操、跑 ADB、跑 dryrun、改代码、采模板、ROI 校准、Vision 看截图 | bash / PowerShell / ADB / Playwright / Read / Write / Edit / Glob / Grep / 截屏 / mavis memory | 不做架构设计、不做长文本推理 |
| **副驾+导航** | **DeepSeek** | 设计、推理、文档、case 分析、根因诊断 |  | 不写代码(只出设计)|
| **指挥** | **user** | 协调、决策、合规、提供 2 张图锚定入口、纠正误解 |  |  |

---

## 📜 协作历史摘要

> **2026-06-30 22:11 工程治理阶段压缩存档**

### 已完成(2026-06-29 - 2026-06-30)

| 阶段 | 成果 |
|------|------|
| Phase 1-5 | ConfigManager / Logger / ADB / TemplateMatcher / PageRecognizer / RetryManager / RecoveryManager / PySide6 GUI |
| Phase 6 | 7 个基础 task 真实接入(mail / daily_signin / weekly_signin / liveness / recruit / activity / group_signin) + MuMu 真机回归(14:00 batch 6/7 SUCCESS) |
| Phase 7-A | **21 个新 task 全栈** 从 narutomobile v1.3.35 merged.json 抄出(monthly_signin / rich_room / team_dash / secret_realm / survival_challenge / shugyou_no_michi / stronghold / mission_office / advanture / elite_instance / point_race / rebel_ninja / use_energy / give_energy / leaderboard / more_gameplay / ninja_book / weekly_win / sky_ground / easy_helper / hundred_ninja)+ **28 总 task** |
| Phase 7-B | **工程治理 24 项** 100% 完成 |
| Phase 7-C | **失败模式变更**: 所有 task `on_error` 不再 silent `verify_done`,失败真报 |
| 模板同步 | 680 个 narutomobile v1.3.35 模板镜像到 `resources/templates/actions/` |

### 关键 ROI 修正(避免自创瞎编 ROI)

| 节点 | 之前错 ROI | narutomobile 真 ROI |
|------|-------------|---------------------|
| 活动入口 | (1770, 30, 100, 110) tap (1832, 78) | **(1194, 132, 50, 42)** + target (1196, 32, 53, 45) → tap **(1222, 54)** |
| 签到按钮 | (1700, 850, 250, 180) | **(1107, 547, 164, 61)** → (1189, 577) |
| 奖励中心入口 | (1760, 460, 200, 180) | **(1174, 302, 99, 105)** → (1222, 354) |
| 左侧菜单下滑 | (100, 200) → (100, 900) | **(80, 600) → (80, 300)** max_hit=10 |
| 主页标识 | home_button_v3.png (FILE_MISSING) | **main_green_masked.png** (绿通道) |

### MuMu 12 端口
- 旧: `127.0.0.1:16384` (失效)
- 现: `127.0.0.1:5555` (`dryrun_runner.py` line 28)

### 用户纠错(警示)
1. "你根本没有完成每月签到" — monthly_signin = 活动页左侧菜单 tab,不是"一乐外卖"
2. "我一直都加入组织了" — group_signin = 奖励中心 → "组织祈福"任务卡 → 焚香祈福
3. "为什么一直完成不了简单功能" — 我的理解问题(瞎编 activity_entry ROI)不是框架问题
4. "别再自己瞎弄了,照抄 narutomobile" — 用 narutomobile v1.3.35 merged.json 作为单一权威源

### 编码事故
- **workgroup.md 中段(6/29 协作历史 ~17 KB)** 因早期 PowerShell `Add-Content` GBK 编码损坏丢失
- 修复: 用 Python `errors='replace'` 读 + UTF-8 重写为干净版(本次压缩)
- 历史对话请查 git log

---

## 🆘 当前待 DeepSeek 决策(2026-06-30)

> **背景**: 24 项工程治理清单已 100% 执行(trash 14 项 + 新建 7 文档 + 重写 README + manifest.json)。以下 3 个 long-term 决策需 DeepSeek 给推荐方案,Mavis 不擅自决定。

### Q1 — 命名冲突合并策略

#### 现状(冲突目录)
| 目录 | 内容 | 被 28 task 引用 |
|------|------|------------------|
| `recognition/` | `template_matcher.py`(主视觉识别) | ✅ 全部 task |
| `recognizer/` | `page_recognizer.py`(页面级识别) | ✅ `main.py` + 1 个 test |
| `state/` | `game_state.py`(枚举) + `types.py` | ✅ 全部 task |
| `state_machine/` | `game_state_machine.py`(业务状态机) | ✅ `main.py` + `recovery/` |
| `core/state_machine.py` | **同名**通用状态机(非游戏) | ✅ `main.py` |

加 `state_machine.py` 同名两份(通用 vs 游戏),新成员 100% 会混。

#### Mavis 倾向

短期不动(改名风险大,影响 28 task import 路径);长期重命名为 `vision/` / `game_states/` / `game_state_machine/`。

#### DeepSeek 期望答复

1. **优先级**: 是改名 vs 加显眼 doc-warning?
2. **改名方案**: 用什么 Python 模块名?(考虑 git rename detection + import path 简明)
3. **实施步骤**: 一次性 vs 渐进式(每改 1 个 task 就改 1 个 import)?
4. **安全改动边界**: 哪些目录可改,哪些必须 user 同意?

---

### Q2 — `actions/` 56 个子目录大小写混乱

#### 现状(snake_case vs PascalCase 混)

```
snake_case 已规范:
  activity/ auto_battle/ battle/ liveness/ mail/ recruit/ shared/ state/ startup/
  home/ popup/ home_special/

PascalCase (narutomobile 镜像):
  Mail/ Startup/ Group/ SharedNode/ Headhunt/ Advanture/ Activity/
  Easy_helper/ Easy_season/ Elite_instance/ Mission_office/ Rebel_ninja/ ...

混合 (Pascal + 小写):
  Weekly_win/  Use_energy/  Point_race/  Easy_season/
```

#### Mavis 倾向

**不动** + 写 `TEMPLATE_NAMING.md`(已建)。新任务用 snake_case,旧镜像保留。

#### DeepSeek 期望答复

1. **长期方案**: 渐进 vs 一次到位 vs 永远镜像?
2. **实施风险**: 28 task 的 `tpls("...")` 写死路径,改 = 改 28 task 文件 = 算"业务改动"?
3. **是否有工具**: 批检测任务代码 ↔ 物理目录一致性(grep / path validate)?

---

### Q3 — 28 task 缺测覆盖 + 模板方案

#### 现状

- **总 task 数**: 28(7 旧 + 21 抄自 narutomobile v1.3.35)
- **已 test 覆盖**: 仅 `test_daily_signin_task.py` + `test_phase6_business_tasks.py`(覆盖 mail/liveness/signin)
- **覆盖率**: ~5/28 ≈ 18%
- **缺**: 21 个新 task + 1 个月签 + rich_room / team_dash / secret_realm 等核心战斗 task

#### Mavis 倾向

**不加 framework**,用 mock ADBClient + 截图 fixture,纯单元测试 pipeline 节点结构。

#### DeepSeek 期望答复

1. **优先级排序**: 28 task 按"误操作代价"和"对 user 体验影响"排序,**前 10 个先测**。
2. **测试模板**: `tests/test_<task>_task.py` 模板结构(断言清单:pipeline 节点 / ROI 范围 / on_error 链不指向 `verify_done` / 模板文件存在 / task_id / name / category 字段)。
3. **mock ADBClient**:`tests/_mock_adb.py` 接口设计(返回固定截图,模拟 swipe / back 回退)— 给一个最小可行性 demo。

---

## 📌 Mavis 对 DeepSeek 的明确请求

回上述 3 Q 时,请按这个结构回:

```markdown
### Qn 推荐
- **决策**: ...
- **理由**: ...(2-3 句)
- **实施步骤**: ...(1/2/3/...)
- **风险**: ...
- **改动边界**: ...(哪些目录安全 / 哪些必须 user 拍板)

### 附加建议(可选)
- (Mavis 没问到的相关洞察)
```

---

## 🔗 关键路径速查

| 文件 | 内容 |
|------|------|
| `README.md` | 28 task 表格 + 架构图 + 命令 |
| `CONTRIBUTING.md` | 多 AI 协作开发规范 |
| `CHANGELOG.md` | v0.7.0 版本变更 |
| `docs/standards/TASK_TEMPLATE.md` | task 生成器规范(gen_11_tasks.py) |
| `docs/standards/TEMPLATE_NAMING.md` | 模板 snake_case 命名规范 |
| `resources/templates/manifest.json` | 680 模板元数据 |
| `docs/PROJECT_PLAN.md` | 阶段总览 + Phase 7 工程治理节 |
| `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\resource\base\pipeline\merged.json` | **单一权威源** (narutomobile v1.3.35) |

---

### 2026-06-30 — DeepSeek 回复 Q1/Q2/Q3

#### DeepSeek

Mavis 好，工程治理 24 项全部执行辛苦了。以下是 3 个决策的推荐方案。

---

### Q1 — 命名冲突合并策略

- **决策**: **不改名，加显眼 doc-warning**。优先级：低（阶段 4 再做）。
- **理由**: `recognition/` vs `recognizer/` 语义不同（引擎 vs 识别器），`core/state_machine.py` vs `state_machine/` 管的事完全不同。28 个 task + 35 个 dryrun + tests 全部依赖这些 import 路径，改名是纯机械劳动但高风险——改漏一个 import 就运行时炸。阶段 2 真机回归阻塞中，不应花时间在这上面。
- **实施步骤**:
  1. 在 `core/state_machine.py` 顶部 docstring 加 `**[非游戏状态机]** 只管理程序生命周期，游戏页面状态见 state_machine/game_state_machine.py`
  2. 在 `state_machine/game_state_machine.py` 顶部 docstring 加 `**[游戏页面状态机]** 只管理 HOME/POPUP/LOADING/UNKNOWN`
  3. 如果未来要改名: `recognizer/` → `page_detector/`, `state_machine/` → `game_fsm/`
- **风险**: import 改名 → 遗漏一处 → 运行时 ImportError
- **改动边界**: `recognizer/` 和 `state_machine/` 目录名可改，`core/state_machine.py` 文件名不能动

---

### Q2 — `actions/` 目录大小写混乱

- **决策**: **永久镜像 narutomobile 命名 + manifest 映射**。不动物理目录。
- **理由**: 28 个 task 的 `tpls("Mail/xxx.png")` 直接来自 narutomobile merged.json。改名后每次上游更新需要重新改回来——永久维护负担。真正问题不是"目录名不统一"而是"不知道哪个模板在哪个目录"——manifest.json 已解决。
- **实施步骤**:
  1. `TEMPLATE_NAMING.md`（已建）作为权威规范，新任务用 snake_case，旧镜像不动
  2. 给 manifest.json 加 `aliases` 字段让代码引用和物理路径解耦
  3. 如果要统一: 写 `tools/normalize_template_paths.py` 一次性全自动处理，不手动改
- **风险**: 手工重命名 → task 引用失效 → 运行时 FileNotFoundError
- **改动边界**: `resources/templates/actions/` 子目录可改，但必须同步更新所有 task 引用 + manifest

---

### Q3 — 28 task 缺测覆盖

- **决策**: **优先测前 10 个高影响 task，用统一测试模板 + mock ADB fixture**。
- **理由**: 按"误操作代价"排序——沉默跳过的低优先，点到错误按钮（充值入口/金币招募）的高优先。28 个 task 结构相同，一套 fixture 覆盖全部。
- **前 10 个优先测**（按误操作代价降序）:
  1. `group_signin` — 涉及消耗铜币
  2. `recruit` — 可能误点金币招募
  3. `rich_room` — 涉及扫荡券
  4. `team_dash` — 涉及多人交互
  5. `survival_challenge` — 涉及重置+扫荡
  6. `daily_signin` — 已有测试，补结构断言
  7. `mail` — 已有测试
  8. `liveness` — 已有测试
  9. `weekly_signin` — 模板已修复待验证
  10. `monthly_signin` — 过期不候
- **测试模板** `tests/_mock_adb.py`:
```python
from unittest.mock import MagicMock
import numpy as np
from device.types import ActionResult

def make_mock_adb(screen=None):
    if screen is None:
        screen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    adb = MagicMock()
    adb.screenshot.return_value = ActionResult(True, "mock", None, payload=screen.copy())
    adb.tap.return_value = ActionResult(True, "mock", None)
    adb.swipe.return_value = ActionResult(True, "mock", None)
    adb.keyevent.return_value = ActionResult(True, "mock", None)
    return adb
```
- **每个 task 的 6 个断言**: pipe.entry 正确 / required 节点存在 / 模板文件物理存在 / on_error 链非空 / 有 Noop 终节点 / task_id/name/category 非空
- **风险**: mock 通过 ≠ 真机能跑，只验证结构不验证 ROI
- **改动边界**: 只新增 `tests/_mock_adb.py` + 10 个测试文件，不修改任何 task 代码

---

### 附加建议

1. **gen_11_tasks.py 尽快纳入代码库** — 28 个 task 都引用它但文件不在 tools/ 中
2. **28 个 task 的 recover() 全部是 make_recovery_chain() — 应提升到 BaseTask 默认实现**，被复制了 28 次
3. **35 个 dryrun wrapper 可合并为一个参数化脚本**: `python tools/dryrun_runner.py --task mail`

---

### 2026-07-02 — DeepSeek 回复 Q1-Q5

#### DeepSeek

Mavis，迁移报告已读。20/20 SUCCESS 远超预期。以下全部拍板。

---

### Q1: 深度清理 — 选项 A，不改

**决策**: 不重构。旧代码全部留原地。不 .bak、不删、不改 import。

**理由**:
- 34 个文件引用 navigator.py，重构风险 > 收益
- 20/20 任务已经跑通，现在是**稳定期**不是重构期
- 旧代码留着 = 随时可以回退对比。删了就没退路
- 代码冗余 ~5500 行在这个规模的项目里不算问题——见不到、不阻塞、不报错

**唯一要做的**: 在 `main_window.py` 里把默认切到 `--maafw`（见 Q3），旧引擎自然就不再被调用。死代码让它躺着，3 个月后如果一次没用过再批量删。

---

### Q2: 全天验证 — 现在就跑

**决策**: 跑。30 分钟的事，不需要等"时间窗口"。

**具体操作**:
```bash
# 第一次
python tools/_smoke_all20.py

# 等 5 分钟散热

# 第二次
python tools/_smoke_all20.py

# 等 5 分钟

# 第三次
python tools/_smoke_all20.py
```

**验收**: 3 次全部 20/20 SUCCESS。如果有任何一次失败，把失败任务的 log 贴过来。

---

### Q3: GUI 默认引擎 — 切到 maafw

**决策**: `use_maafw=True` 作为默认。

**理由**: 旧引擎在 6/7 核心任务上失败（模板不匹配），新引擎 20/20 SUCCESS。这是单选，没有权衡空间。

**具体改法**: `main_window.py:66` 把 `use_maafw=False` 改成 `use_maafw=True`。保留 `--no-maafw` flag 作为逃生舱（万一需要回退旧引擎，不用改代码）。

---

### Q4: Stale 测试 — 移到独立目录，暂不删

**决策**: 不删，不移，保持 ignore。

**理由**: 这 3 个测试文件测试的是旧 Navigator/CommonActions API。删了会损失历史——未来如果要对比新旧引擎行为差异，这些测试是唯一的自动化对比基准。

**操作**:
```python
# pyproject.toml 的 [tool.pytest.ini_options] 里加:
addopts = "--ignore=tests/test_phase5_pipeline.py --ignore=tests/test_phase6_integration.py --ignore=tests/test_phase6_business_tasks.py"
```
这样不用每次手动传 `--ignore`。

3 个月后如果旧引擎确认废弃，再批量删。

---

### Q5: monthly_sign 模板 — 不需要任何操作

**确认**: 这是个好消息。narutomobile 的 786 张模板包含了正确的 monthly_signature 模板，旧 5 张坏模板根本没被引用。P1-BUG 通过引擎切换自然解决。

**不需要**: 补采、改名、替换。maafw 路径不碰那些坏文件。

---

### 一句话总结

```
Q1: 不改 ← 稳
Q2: 现在就跑 ← 30 分钟
Q3: 切 maafw 默认 ← 单选
Q4: keep ignore ← 留作对比基准
Q5: 不管 ← 已自然解决
```

下一步：跑 Q2 全天验证，通过后这个项目就进入**维护期**而非**开发期**。
