# 任务开发标准 / Task Development Standard

> **适用对象**: 任何新增 / 修改 `tasks/*.py` 的开发者(包括其他模型接手时)
> **核心目标**: 一个新任务开发完成时, 必须满足以下所有项才能合并

---

## 0. TL;DR — 提交检查清单

提交新任务前, 对照此清单逐项勾选:

```
□ 1. 入口说明已写入 docs/game_wiki/<task>.md
□ 2. 至少 1 个核心模板已采集(必要时 ≥ 2 备选)
□ 3. 成功验证条件明确(能看到什么 = 成功)
□ 4. 失败恢复路径已实现(recover() 内有 ≥ 2 步兜底)
□ 5. 最小 Pipeline 已写完(ensure_home → 入口 → 操作 → 关闭 → 主页)
□ 6. 单元测试通过(pipeline 状态机 dry-run 跑通)
□ 7. 集成测试通过(真机 dry-run 跑通, 截图存盘)
□ 8. template_manifest.json 中 task 字段已更新
□ 9. best-effort 语义明确(SUCCESS / SKIP / FAIL 边界)
□ 10. pre_flight / ensure_game_in_foreground 已生效(默认)
```

---

## 1. 入口说明

### 必须文档化的内容

```markdown
## 1. 入口在哪

### 主页入口
- 位置: <具体坐标 + 视觉描述>
- 模板: <文件名>
- ROI: (x, y, w, h)  ← 1920×1080 参考
- 备选: <fallback 模板列表>

### 备选入口(若存在)
- 路径: ...
```

### 入口识别原则

| 原则 | 描述 |
|---|---|
| **ROI 必须实测校准** | 不要直接抄 narutomobile 数据 — 用户的实际游戏 UI 可能漂移 |
| **备选模板 ≥ 2 个** | 主模板 + 至少 1 个 fallback(可能源自不同版本) |
| **OCR 兜底优先** | 文字入口比按钮稳定(详见后文 §3) |
| **"在不在前台"先检查** | 任务入口必须假设"游戏可能不在前台", 用 `pre_flight()` 兜底 |

---

## 2. 核心模板

### 模板采集最小集

一个新任务的模板清单必须包含:

| 类别 | 数量 | 说明 |
|---|---|---|
| **入口模板** | ≥ 1 (+ 备选) | 主页到任务页的入口 |
| **状态判断模板** | ≥ 1 对 | "已完成" + "未完成" 配对 |
| **操作按钮模板** | ≥ 1 | 主要点击目标 |
| **关闭弹窗模板** | ≥ 1 | 通常复用 `shared/x.png` |
| **主页兜底模板** | ≥ 1 | 通常复用 `shared/home_button_v3.png` |

### 模板命名约定

按 **子目录 + 任务语义** 命名:

```
resources/templates/actions/
├── shared/            ← 跨任务共享
│   ├── x.png
│   ├── home_button_v3.png
│   └── award_center_entry.png
├── group/             ← 组织任务专用
│   ├── copper_pray.png
│   └── first_box_wait.png
├── mail/              ← 邮件任务专用
│   ├── mail_envelope.png
│   └── mail_wait.png
└── <新任务名>/         ← 新建子目录
    ├── entry.png
    ├── state_done.png
    ├── state_undone.png
    └── action_button.png
```

### 模板质量检查

- ⚠️ **不能用场景背景图当按钮图**(例如 `shared/ninja_guide_v3.png` 实际是场景背景)
- ⚠️ **不能用排行榜文字当列表图**(例如 `group/group_list.png` 实际是排行榜)
- ⚠️ **不能用图标当按钮**(例如 `group/copper_pray.png` 实际是铜币图标)

**判断方法**: 用图片查看器打开, 确认图片内容与命名意图一致。

### 模板采集工具

- 当前项目: `capture_*.py` 系列(`capture_home_entries.py`, `capture_award_center.py` 等)
- 推荐: 单独写 `capture_<task>.py`, 截图时**人工确认**每个 ROI 的内容

---

## 3. 成功验证条件

### 必须明确写出

```markdown
## 4. 成功条件

- [ ] <具体视觉/状态变化 1>
- [ ] <具体视觉/状态变化 2>
- [ ] <任务结束信号>
```

### 推荐的"成功判定模式"

**模式 A: 状态模板命中**

```python
Node(
    name="check_done",
    templates=tpls("xxx_done.png"),  # 已完成态模板
    roi=...,
    action=NoopAction(),  # 只识别不点击
    next=["next_subtask"],
    focus="判定已完成",
)
```

**模式 B: 弹窗消失 + 主页元素出现**

```python
# 状态:关闭弹窗 → 出现主页橙色按钮
# 通过 post_delay + 二次截图验证
```

**模式 C: OCR 关键字命中**

```python
Node(
    name="verify_claim",
    ocr_expected=["领取", "已领取"],  # 任一命中即成功
    ocr_roi=...,
    ocr_threshold=0.5,
    action=OCRAction(),
    next=["next"],
)
```

### 反模式(禁止)

- ❌ 只靠"点了"就算成功(无任何验证)
- ❌ 用 `time.sleep(2)` 等待后就算成功
- ❌ 不验证游戏是否回到主页

---

## 4. 失败恢复路径

### `recover()` 方法的最低标准

```python
def recover(self, ctx: "ExecutionContext") -> bool:
    """恢复路径:至少 2 步兜底。"""
    if ctx.common_actions is None:
        return False
    adb = ctx.common_actions._adb
    try:
        # 1. 关闭任何弹窗(X 按钮, NOT BACK)
        adb.tap(1826, 84)
        time.sleep(0.5)
        # 2. 主页按钮兜底
        adb.tap(85, 760)
        time.sleep(1.0)
        return True
    except Exception as e:
        log.warning("recover failed: {}", e)
        return False
```

### 恢复路径清单

| 步骤 | 用途 | 工具 |
|---|---|---|
| 1. 关闭右上 X | 任何弹窗 | `adb.tap(1826, 84)` |
| 2. 主页橙色按钮 | 兜底回主页 | `adb.tap(85, 760)` |
| 3. (可选) HOME 键 | 极端情况 | `adb.keyevent("HOME")` |

### 禁止

- ❌ 在 recover() 里调系统 BACK 键 — 会触发"是否退出游戏"弹窗
- ❌ recover() 不抛异常 — 必须 try/except 包裹
- ❌ recover() 只做 1 步 — 至少 2 步

### 与 pre_flight 的协作

- `pre_flight()` 在 `pre_check` **之前**自动执行 `ensure_game_in_foreground()`
- 不需要在每个任务的 `pre_check` 里手动调
- 如果任务需要更精细的前置检查, 可在 `pre_flight` 覆盖默认实现

---

## 5. 最小 Pipeline

### 最小 6 节点骨架

```python
def _build_<task>_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    # 1. 主页基线(必须)
    pipe.add(Node(name="ensure_home", templates=[], action=NoopAction(),
                  next=["find_entry"], focus="..."))

    # 2. 找入口(必须, ≥ 1 个备选模板)
    pipe.add(Node(name="find_entry", templates=tpls("..._entry.png"),
                  roi=(x,y,w,h), threshold=0.55, action=ClickAction(),
                  next=["do_action"], on_error=["verify_done"],
                  post_delay_ms=1500, focus="..."))

    # 3. 执行主要操作(任务核心)
    pipe.add(Node(name="do_action", templates=tpls("..."), roi=...,
                  action=ClickAction() | OCRAction(),
                  next=["close_popup"], post_delay_ms=1000, focus="..."))

    # 4. 关闭弹窗(必须, 通用 X)
    pipe.add(Node(name="close_popup", templates=tpls("shared/x.png"),
                  roi=(1820, 60, 80, 80), action=ClickAction(),
                  next=["back_to_home"], post_delay_ms=800, focus="..."))

    # 5. 回主页兜底(必须)
    pipe.add(Node(name="back_to_home", templates=tpls("shared/home_button_v3.png"),
                  roi=(30, 700, 100, 80), action=ClickAction(),
                  next=["verify_done"], post_delay_ms=800, focus="..."))

    # 6. 终点(必须)
    pipe.add(Node(name="verify_done", templates=[], action=NoopAction(),
                  next=[], focus="..."))

    return pipe
```

### 节点数参考

| 任务复杂度 | 节点数 | 示例 |
|---|---|---|
| 极简单 | 6-8 | mail, daily_signin |
| 中等 | 10-15 | recruit |
| 复杂 | 25-30 | group_signin(4 子链路) |
| 超复杂 | 30+ | narutomobile Group.json(730 行) |

---

## 6. 测试方法

### 6.1 单元测试(pipeline dry-run)

```python
import pathlib
import sys
sys.path.insert(0, r"D:\火影自动日常")

from tasks.navigator import Navigator, Pipeline
from tasks.<task>_task import _build_<task>_pipeline

# mock ADB
class FakeADB:
    def screenshot(self):
        return None
    def tap(self, x, y): return None
    def swipe(self, x1, y1, x2, y2, duration_ms=300): return None
    def keyevent(self, k): return None

nav = Navigator(FakeADB(), pathlib.Path(r"D:\火影自动日常"),
                templates_root=pathlib.Path(r"D:\火影自动日常\resources\templates\actions"))
pipe = _build_<task>_pipeline(nav)
print(f"Pipeline nodes: {len(pipe)}")
print(f"Entry: {pipe.entry}")
for name in pipe._nodes:
    print(f"  - {name}")
```

### 6.2 集成测试(真机 dry-run)

`dryrun_<task>.py` 脚本必须做:

1. 截图当前画面 → `screenshots/dryrun_<task>/00_home.png`
2. 跑 `pre_flight()` + pipeline
3. 每步截图 → `screenshots/dryrun_<task>/step_NNN.png`
4. 记录 history → 看 pipeline 实际走了哪些节点
5. **不抛异常, best-effort 返回 SUCCESS**

### 6.3 验收清单

- ✅ 节点数符合 §5 预期
- ✅ OCR 节点在真机上能命中关键文字
- ✅ best-effort 不阻塞其他任务
- ✅ recover() 在游戏被切后台时能拉回

---

## 7. 必备依赖与 API

### 必须使用的工具

| 工具 | 用途 | 模块 |
|---|---|---|
| `BaseTask` | 任务基类 | `core.base_task` |
| `TaskResult` | 结果封装 | `core.base_task` |
| `pre_flight()` | 游戏前台守护 | `core.base_task`(默认实现) |
| `recover()` | 失败恢复 | 子类覆盖 |
| `Navigator` | 状态机 runner | `tasks.navigator` |
| `Pipeline` / `Node` | pipeline 节点定义 | `tasks.navigator` |
| `ClickAction` | 点击动作 | `tasks.navigator` |
| `OCRAction` | OCR 动作(优先) | `tasks.navigator` |
| `SwipeAction` | 滑动条 | `tasks.navigator` |
| `PipelineRunner` | pipeline 运行容器 | `tasks.pipeline_runner` |
| `save_image_pil` | 截图存盘(不用 cv2.imwrite) | `core.screenshot_utils` |

### OCR 引擎

- **引擎**: `rapidocr-onnxruntime`(纯 Python, 自动下载模型)
- **首次加载**: ~0.5-1.5s
- **单次全屏 OCR**: ~1.5-2.0s
- **ROI 限制后**: ~0.3-0.5s
- **不要**自己引入 pytesseract / easyocr / paddleocr — 统一用 rapidocr

---

## 8. best-effort 语义

### TaskStatus 边界

| 状态 | 含义 | 何时用 |
|---|---|---|
| `SUCCESS` | 任务主流程执行完毕 | 主流程走完 |
| `SKIP` | 跳过(不需要执行) | pre_check 返 False / pre_flight 失败 |
| `FAIL` | 异常失败 | run() 内部抛异常 / recover 兜不住 |
| `RETRY` | 重试中 | (未使用) |

### 推荐语义

**大多数任务用 best-effort SUCCESS**:

```python
def run(self, ctx):
    # 1. 第一次尝试
    result = self._run_pipeline(...)
    if result.success:
        return TaskResult(status=TaskStatus.SUCCESS, ...)
    # 2. 失败 → recover + 重试
    self.recover(ctx)
    time.sleep(1)
    result2 = self._run_pipeline(...)
    if result2.success:
        return TaskResult(status=TaskStatus.SUCCESS, ...)
    # 3. best-effort: 即使失败也返 SUCCESS
    return TaskResult(
        status=TaskStatus.SUCCESS,  # ← 注意是 SUCCESS 不是 FAIL
        message="best-effort: " + str(result2.error),
    )
```

### 何时用 FAIL

- 真正的异常(代码 bug / ADB 断连)
- 用户关键任务(必须完成的)
- 涉及付费的流程(绝不允许失败后继续)

---

## 9. 模板治理

### 新增模板的步骤

1. **采集**: 用 `capture_<task>.py` 截图(项目根目录已有)
2. **命名**: 按 `子目录/<语义>.png` 命名
3. **质量检查**: 用图片查看器确认内容
4. **更新 manifest**: 跑 `python scripts/generate_template_manifest.py`
5. **代码使用**: 在 task 代码里通过 `nav.templates(...)` 引用

### 模板清单字段

`resources/templates/template_manifest.json`:

```json
{
    "file": "group/copper_pray.png",
    "task": "group",
    "page": "group_pray",
    "purpose": "copper_pray_btn",
    "required": true,
    "recommended_threshold": 0.55,
    "version_sensitive": true,
    "notes": "铜币签到按钮, 注意活动期间可能变色"
}
```

### 模板废弃流程

- 不要直接删除 — 先移到 `templates/deprecated/` 子目录
- 在 manifest 里把 `required` 改为 `false`, `notes` 写"deprecated"
- 在 `docs/game_wiki/<task>.md` 里说明替代模板

---

## 10. 文档规范

### 每个任务必须有 wiki

文件位置: `docs/game_wiki/<task_id>.md`

**必填章节**:

1. 元信息(Task ID / 类 / 状态 / 相关模板数 / 最后更新)
2. 入口在哪(主页 + 备选入口)
3. 页面长什么样(主页 + 任务页 + 弹窗)
4. 常见按钮 / 文字 / 图标(表格)
5. 成功条件(具体)
6. 失败条件(具体)
7. 常见干扰项
8. 当前项目实现(pipeline 节点表)
9. 参考项目实现(narutomobile 节点摘要)
10. 已知问题与 TODO
11. 开发规则(任务特定的"必须/禁止")

### 文档更新触发

- 任何 ROI 改动 → 更新对应 wiki 的 ROI 字段
- 任何模板新增/废弃 → 更新 wiki 的"常见按钮"表格
- 任何 pipeline 节点新增 → 更新 wiki 的"当前实现"节点表

---

## 11. 反模式检查表(提交前自查)

| 反模式 | 表现 | 必须修正 |
|---|---|---|
| **架构蔓延** | 新建 Navigator 子类 / TaskEngine 子类 | ❌ 禁止 |
| **跨任务耦合** | A 任务的 pipeline 引用 B 任务的模板 | ❌ 禁止(共享用 `shared/`) |
| **系统 BACK 键** | `KeyAction(key="BACK")` | ❌ 禁止(用界面 X) |
| **cv2.imwrite 截图** | 静默失败, 不抛异常 | ❌ 禁止(用 `save_image_pil`) |
| **未实现就 commit** | 只有 wiki 没有代码 | ⚠️ 标记 status: 未实现 |
| **ROI 硬编码** | 在 pipeline 里直接写 (900, 580, 220, 160) 而不抽取常量 | ❌ 必须用 `ROI_xxx` 常量 |
| **单模板无备选** | `templates=tpls("only_one.png")` | ❌ 必须 ≥ 2 备选 |
| **未测试就 commit** | 没跑 `dryrun_*.py` | ❌ 必须跑过 |
| **OCR 节点无 ROI** | `ocr_expected=["前往"]` 但没 `ocr_roi` | ❌ 必填 |
| **recover() 单步** | 只点 X 不点主页按钮 | ❌ 必须 ≥ 2 步 |

---

## 12. 提交模板

新任务的 commit message 推荐格式:

```
[任务] <task_id> — <一句话描述>

- Pipeline: <节点数> 节点 (含 <子链路数> 子链路)
- 模板: 新增 <N> 张, 复用 <N> 张 shared/
- OCR: <N> 节点(前往/追击/...)
- Wiki: docs/game_wiki/<task>.md
- 测试: dryrun_<task>.py 跑通

Refs: narutomobile <对应 pipeline>.json
```

---

## 13. 持续维护约定

- **每月**: 跑一次 `python scripts/generate_template_manifest.py`, 对比 diff 看是否需要更新
- **每次游戏大版本**: 重做一次 ROI 校准(`dryrun_<task>.py`)
- **每次新模板**: 更新 `template_manifest.json` + `docs/game_wiki/<task>.md`
- **每次失败案例**: 写入对应 wiki 的"已知问题与 TODO"

---

## 附: 标准目录结构

```
D:\火影自动日常/
├── tasks/
│   ├── __init__.py
│   ├── common_actions.py
│   ├── daily_signin_task.py
│   ├── mail_task.py
│   ├── liveness_task.py
│   ├── group_signin_task.py
│   ├── recruit_task.py
│   ├── weekly_signin_task.py
│   ├── activity_task.py
│   ├── navigator.py              ← 不修改
│   ├── pipeline_runner.py        ← 不修改
│   └── <新任务>_task.py           ← 新建
├── core/
│   ├── base_task.py              ← pre_flight 已加
│   ├── screenshot_utils.py       ← PIL 工具
│   └── ...
├── resources/
│   └── templates/
│       ├── actions/              ← 模板目录(143 张)
│       └── template_manifest.json ← 模板清单
├── docs/
│   ├── game_wiki/                ← 任务知识库(6 份)
│   │   ├── daily_signin.md
│   │   ├── mail.md
│   │   ├── liveness.md
│   │   ├── group_signin.md
│   │   ├── shop.md
│   │   └── recruit.md
│   ├── standards/                ← 开发标准
│   │   └── TASK_STANDARD.md
│   └── ...
├── scripts/
│   └── generate_template_manifest.py
├── dryrun_<task>.py              ← 每个任务一个
└── tests/                        ← 单元测试
```

---

## 14. 实际可运行的命令清单

```bash
# 1. 生成模板清单
python scripts/generate_template_manifest.py

# 2. 单元测试: pipeline 状态机
python -c "from tasks.<新任务>_task import _build_<新任务>_pipeline; print('OK')"

# 3. 真机 dry-run
python dryrun_<新任务>.py

# 4. 截图存盘(必须用 PIL, 不用 cv2.imwrite)
python -c "from core.screenshot_utils import save_image_pil; print(save_image_pil)"
```

---

## 15. 按钮热区偏上规则 (V1.2 §1.2.0 强制)

> 📌 **来源**: 2026-06-26 真机验证(`monthly_sign_button.png` 220×100, 视觉中心 (1780, 920),tap 中心无响应,tap 偏上位置生效,count 25/30 → 26/30)。
> 🎯 **目标**: 让所有 task pipeline 在"找按钮"和"点击按钮"两步之间自动应用偏上偏移,避免 tap 视觉中心失效。

### 15.1 现象

- 截取的按钮模板 (220×100) → 视觉上完整包含按钮
- 但 tap 模板中心 (cx, cy) **无响应**(UI 延迟刷新 / hit area 不在视觉中心)
- tap 模板偏上位置 (cx, cy - 25%) → **生效**

### 15.2 根因(经验性)

- 游戏 UI 用 Cocos/Unity 自定义渲染,按钮的 hit area **比视觉精灵小**
- 通常热区只占视觉区域的上半部分或上半三分之一
- 视觉下半部分可能被阴影/文字装饰/空白占据,不是真正的 click 区域

### 15.3 规则(默认)

| 按钮视觉高度 | 推荐 tap_offset_y | 适用场景 |
|---|---|---|
| 30px 以下(小图标) | -0.15 | 关闭 X、小徽章、tab 切换 |
| 50-100px(普通按钮) | **-0.25** ✅ 默认 | 大多数按钮(每日签到、领取、签到) |
| 150px 以上(大卡片) | -0.33 | 大卡片、活动入口、领奖箱 |
| 不确定 | 从 -0.25 试,失败再往上挪 | 新按钮默认 -0.25 |

### 15.4 实现

#### 工具层(`tools/find_and_tap.py`)

CLI 加 `--tap-offset-y` 参数(默认 `0.0` = 视觉中心,向后兼容):

```bash
# 真机 tap 偏上 25%(推荐作为日常使用)
python tools/find_and_tap.py templates/x.png --tap-offset-y -0.25

# 调试:先 --no-tap 看命中点,再决定要不要加 tap_offset_y
python tools/find_and_tap.py templates/x.png --no-tap --debug
```

API 同样支持:

```python
from tools.find_and_tap import find_and_tap
find_and_tap(
    template_path,
    adb_path=...,
    serial=...,
    tap_offset_y=-0.25,  # 偏上 25%
    do_tap=True,
)
```

#### Task 层(`tasks/common_actions.py`)

`CommonActions.tap_template()` 内部默认应用 `tap_offset_y = -0.25`(可选通过参数覆盖):

```python
# 当前默认: 视觉中心
common.tap_template(tpl, threshold=0.75)
# 等价于
common.tap_template(tpl, threshold=0.75, tap_offset_y=0.0)
# 推荐: 偏上 25%
common.tap_template(tpl, threshold=0.75, tap_offset_y=-0.25)
```

#### Navigator 节点层

`Node` 的 `action=ClickAction()` 默认 tap 模板中心(向后兼容)。**v1.2.1+ 计划**让 `ClickAction()` 自动应用 -0.25,见 TODO。

### 15.5 真机验证案例(2026-06-26)

| 模板 | 尺寸 | 视觉中心 | 偏上 -0.25 | 结果 |
|---|---|---|---|---|
| `monthly_sign_button.png` | 220×100 | (1780, 920) | (1780, 895) | ❌→✅ count 25/30→26/30 |
| `shared/activity_button_v3.png` | 110×110 | (1820, 85) | (1820, 57) | ✅ conf=0.982 |

### 15.6 反模式

| 反模式 | 后果 | 修正 |
|---|---|---|
| 默认 tap 视觉中心 | 大型按钮 30% 概率不响应 | 默认 `tap_offset_y = -0.25` |
| 硬编码偏移像素 | 跨分辨率失效 | 用 `tap_offset_y` 比例,占 tpl_h |
| 同一按钮每次 tap 不同位置 | 真机行为不可预期 | 在 wiki 里固化 `tap_offset_y` 决策 |

### 15.7 调试流程

1. 先 `--no-tap --debug --threshold 0.75` 看 conf
2. conf ≥ 0.75 但 tap 不响应 → 加 `--tap-offset-y -0.25`
3. 还不行 → 试 `--tap-offset-y -0.33`
4. 还不行 → 模板本身偏,重新裁 / 加多模板候选

---

**这份标准是活的, 不是死的。** 每次实战后, 应该回来更新这份文档, 让标准更准确。