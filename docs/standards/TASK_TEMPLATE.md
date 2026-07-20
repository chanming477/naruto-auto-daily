# TASK_TEMPLATE.md — Task 文件生成规范

> 28 个业务 task(`tasks/*_task.py`)统一通过 **`tools/gen_11_tasks.py` 模板生成器**产出。**禁止手写** task 文件。

## 1. 生成器架构

```python
# tools/gen_11_tasks.py
TASK_TEMPLATE = '''...'''  # 8 节点 pipeline Python 源码模板
TASKS = [..., make_task(...), ...]  # 每任务一个配置字典
```

每个 task 配置字段(13 个):

| 字段 | 含义 |
|------|------|
| `tid` | task_id (snake_case,如 `rich_room`) |
| `classname` | 类名 (PascalCase,如 `RichRoom`) |
| `cname` | 中文显示名(如 `丰饶之间`) |
| `category` | 分类(`daily` / `weekly` / `monthly` / `combat` / `social`) |
| `cname_desc` | 中间描述文字 |
| `flow_doc` | 流程描述(从 MaaAutoNaruto 抄) |
| `entry_node` | 第 1 关节点名(进任务入口) |
| `entry_desc` | 入口说明 |
| `card_node/roi_py/templates/action_node/fight_node/win_node` | 5 个核心节点的配置 |
| `card_extras` | 如 `green_mask=True,\n        ` 插入到节点 |

## 2. 8 节点标准 Pipeline

每个 task 强制 8 节点:

```
1. ensure_home               Noop(基线)
2. {entry_node}              进任务入口(headhunt / award_center / ninja_guide / 直点)
3. {card_node}               找任务卡(ac_undone / entry / via menu)
4. {action_node}             出战 / 立即前往 / 扫荡 / 点赞
5. {fight_node}              自动战斗中(检测 challenge.png 或 battle_emoji.png)
6. {win_node}                胜利 / 扫荡完成 / 关闭
7. back_main_screen          main_green_masked.png + 绿通道(状态/UI 抗干扰)
8. verify_done               Noop(终点)
```

**back_main_screen 是关键**:用 `state/main_green_masked.png` 在 ROI `(0, 0, 1920, 1080)` 绿通道匹配,作为统一回主页标识。

## 3. ROI 来源

**唯一权威源**: `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.41\resource\base\pipeline\merged.json`

提取方式:
```python
import json
with open(r'D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.41\resource\base\pipeline\merged.json') as f:
    data = json.load(f)
# 例如:找 rich_room 入口
v = data['rich_room_ac_entry_undone']
print(v['roi'], v['template'])
# [180, 288, 1100, 225], Rich_room/rich_room_ac_undone.png
```

**禁止**:
- ❌ 自己推断 ROI(总是错)
- ❌ 用 `cv2.imread`(MaaAutoNaruto PNG iCCP chunks 不规范会让 headless cv2 报 can't open/read file)
- ✅ 用 `recognition.template_matcher.load_template`(用 `cv2.imdecode` + PIL fallback)

## 4. 新增一个 Task 的步骤

```powershell
# 1. 从 merged.json 抽 ROI,加到 gen_11_tasks.py 的 make_task 调用
#    字段:entry_node/entry_desc/entry_templates/entry_roi_py/entry_threshold/...
# 2. 运行
python tools\gen_11_tasks.py
# 3. 加到 tools/dryrun_runner.py 的 TASK_BUILDERS 字典
'new_task': ('tasks.new_task_task', '_build_new_task_pipeline'),
# 4. 创建 wrapper tools/dryrun_new_task.py
# 5. 写 test_new_task_task.py
# 6. 更新 config/task_registry.yaml(display_order / enabled / description)
```

## 5. on_error 规范

**禁止** `on_error=['verify_done']` — 这掩盖真实失败。

正确模式:
```python
# 找不到模板时,尝试回主页而不是静默 SUCCESS
on_error=['back_main_screen'],
# 找不到回主页的 template,真失败(不再 best-effort SUCCESS)
on_error=['verify_done'],  # 仅当 back_main_screen 也通过回主页 ROI 才 ok
```

**2026-06-30 起**:所有 on_error 都应该至少 try `back_main_screen` 回主页验证。

## 6. 命名约定

| 元素 | 规则 | 例子 |
|------|------|------|
| 文件名 | `<tid>_task.py` snake_case | `rich_room_task.py` |
| 类名 | PascalCase + Task 后缀 | `RichRoomTask` |
| task_id | snake_case,MaaAutoNaruto 同名 | `rich_room` |
| category | 枚举:`daily`/`weekly`/`monthly`/`combat`/`social` | `combat` |
| name | 中文显示名 | `丰饶之间` |

## 7. 测试

每个 task 必须有 `tests/test_<tid>_task.py`:
- mock ADBClient 不接真模拟器
- 校验 pipeline 节点结构
- 校验 ROI 在合理范围
- 校验 on_error 不指向 `verify_done` 静默成功
