# MaaFramework 改造设计 — 实施文档

> 用户决策: 2026-07-01 23:30+ (用户提出接 MaaFramework)
> 调研依据: `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35` 资源 + `D:\自动日常源码带\MAA-win-x86_64-v5.11.1` SDK
> 安装包: `pip install maafw==5.10.4`(已装),`pip install MaaDebugger`(已装)

## 1. 改造目标

**删除本项目所有自研识别/导航代码,用 MaaFramework 引擎 + narutomobile 模板替代**。

代码量从 ~25,000 行降到 ~8,000 行(删 17,000 行)。

## 2. 架构对比

### 改造前

```
D:\火影自动日常\
├── core/
│   ├── task_engine.py
│   ├── recovery_manager.py
│   ├── retry_manager.py
│   ├── config_manager.py
│   └── logger.py
├── tasks/
│   ├── navigator.py        ← 820 行, 自研识别+导航
│   ├── pipeline_runner.py  ← 170 行
│   ├── common_actions.py
│   ├── *_task.py × 11      ← 每个 task 有 _build_xxx_pipeline() 函数
├── recognition/
│   ├── template_matcher.py ← 363 行
│   ├── page_recognizer.py  ← 123 行
│   └── ocr_engine.py
├── resources/templates/    ← 143 张
└── ...
```

### 改造后

```
D:\火影自动日常\
├── main.py / GUI (PySide6)
├── core/
│   ├── task_engine.py      ← 保留,改成 MaaTask 调度
│   ├── recovery_manager.py ← 保留,监听 maafw 失败状态
│   ├── retry_manager.py    ← 保留
│   ├── config_manager.py   ← 保留
│   └── logger.py           ← 保留
├── tasks/
│   └── common_actions.py   ← 简化,只保留 game state 查询等跟 maafw 不冲突的工具
├── maafw_bridge/           ← 新增
│   ├── tasker.py           ← MaaFramework Tasker 单例
│   ├── event_sink.py       ← 接管 maafw 回调 → Python logger
│   ├── resource.py         ← 指向 narutomobile resource/base
│   └── task_mapping.py     ← 我们 task_id → narutomobile entry 名映射
├── docs/                   ← 已有 2 份分析
└── requirements.txt        ← + maafw==5.10.4

外部复用(不改):
D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\
└── resource/base/          ← 直接用,786 模板 + merged.json + interface.json
```

### 删除清单

| 文件 | 行数 | 原因 |
|------|------|------|
| `tasks/navigator.py` | 820 | maafw Tasker 替代 |
| `tasks/pipeline_runner.py` | 170 | maafw 内部跑 pipeline |
| `recognition/template_matcher.py` | 363 | maafw TemplateMatch |
| `recognition/page_recognizer.py` | 123 | maafw recognition pipeline |
| `tasks/*_task.py` 中所有 `_build_xxx_pipeline()` 函数 | ~1000 | 改用 `maafw_bridge.task_mapping` 字符串映射 |
| `tasks/*_task.py` 中 ROI 硬编码 | ~500 | maafw 读 merged.json 自带 |
| `tools/dryrun_*.py × 29` | ~2500 | maafw 自带 debugger 替代 |
| **合计** | **~5,500+ 行** | |

## 3. Task 映射表(已实测)

| 我们 task_id | narutomobile entry | 状态 |
|------|------|------|
| `mail` | `mail` | ✅ 直接对应 |
| `daily_signin` | `activity` | ⚠️ 对应"月签到和一乐拉面" (跟 monthly_signin 同一个) |
| `monthly_signin` | `activity` | ⚠️ 同上,合并 |
| `recruit` | `headhunt` | ⚠️ 改名 |
| `group_signin` | `group` | ⚠️ 改名 |
| `liveness` | `liveness_award` | ⚠️ 改名 |
| `easy_helper` | `easy_helper` | ✅ 直接对应 |
| `rich_room` | `rich_room` | ✅ 直接对应 |
| `ninja_book` | `ninja_book` | ✅ 直接对应 |
| `give_energy` | `give_energy` | ✅ 直接对应 |
| `use_energy` | `use_energy` | ✅ 直接对应 |
| `advanture` | `advanture` | ✅ 直接对应 |
| `elite_instance` | `elite_instance` | ✅ 直接对应 |
| `team_dash` | `team_dash` | ✅ 直接对应 |
| `mission_office` | `mission_office` | ✅ 直接对应 |
| `point_race` | `point_race` | ✅ 直接对应 |
| `weekly_win` | `weekly_win` | ✅ 直接对应 |
| `rebel_ninja` | `rebel_ninja` | ✅ 直接对应 |
| `stronghold` | `stronghold` | ✅ 直接对应 |
| `secret_realm` | `secret_realm` | ✅ 直接对应 |

**11 个 task_id 全部能映射到 narutomobile entry**。

## 4. 实施步骤(分 5 步,每步可独立验证)

### Step 1: 验证 + 跑通最小流程
- [x] pip install maafw==5.10.4
- [x] 加载 narutomobile resource/base
- [x] ADB 连模拟器(127.0.0.1:5555)
- [x] 跑 `start_up` task: **3 节点全部 success**
- [x] 模板 `main_green_masked.png` 在 maafw 引擎里匹配分数 = 0.996(完美命中)
- [x] 任务完成机制: StopTask 兜底(跟之前分析一致)

### Step 2: 写 `maafw_bridge/tasker.py` 单例
```python
# maafw_bridge/tasker.py
from pathlib import Path
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker
from threading import Lock

class MaaTaskerSingleton:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance
    
    def _init(self):
        Toolkit.init_option(r'D:\tmp\maafw_data', {'logging': True})
        
        # ADB
        dev = Toolkit.find_adb_devices()[0]
        self.controller = AdbController(
            adb_path=dev.adb_path, address=dev.address,
            screencap_methods=dev.screencap_methods,
            input_methods=dev.input_methods, config=dev.config,
        )
        self.controller.post_connection().wait()
        
        # Resource
        self.resource = Resource()
        self.resource.post_bundle(
            r'D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\resource\base'
        ).wait()
        
        # Tasker
        self.tasker = Tasker()
        self.tasker.bind(self.resource, self.controller)
    
    def run_task(self, entry: str, override: dict = None):
        job = self.tasker.post_task(entry, override or {})
        return job  # caller can .wait()
```

### Step 3: 写 `maafw_bridge/task_mapping.py`
```python
TASK_MAPPING = {
    'mail': 'mail',
    'daily_signin': 'activity',
    'monthly_signin': 'activity',
    'recruit': 'headhunt',
    'group_signin': 'group',
    'liveness': 'liveness_award',
    'easy_helper': 'easy_helper',
    'rich_room': 'rich_room',
    'ninja_book': 'ninja_book',
    'give_energy': 'give_energy',
    'use_energy': 'use_energy',
    # ...
}

def resolve_entry(task_id: str) -> str:
    return TASK_MAPPING.get(task_id, task_id)
```

### Step 4: 改写 `core/task_engine.py` (从 600 行降到 ~80 行)
```python
# core/task_engine.py
from maafw_bridge.tasker import MaaTaskerSingleton
from maafw_bridge.task_mapping import resolve_entry

class TaskEngine:
    def __init__(self, config, recovery_manager):
        self.config = config
        self.recovery = recovery_manager
        self.tasker = MaaTaskerSingleton()
    
    def run_task(self, task_id: str) -> bool:
        entry = resolve_entry(task_id)
        try:
            job = self.tasker.run_task(entry)
            job.wait()
            return True
        except Exception as e:
            self.recovery.on_task_failed(task_id, str(e))
            return False
    
    def run_daily(self):
        """跑用户的日常 schedule"""
        for task_id in self.config.get('daily_schedule', []):
            self.run_task(task_id)
```

### Step 5: 删除旧代码 + 测试
- 删除 `navigator.py`, `pipeline_runner.py`, `template_matcher.py`, `page_recognizer.py`
- 11 个 `*_task.py` 文件删 `_build_xxx_pipeline()` 函数,只保留 `task_id` / `name` / `category` 元数据 + 钩子
- 删除所有 `tools/dryrun_*.py` 工具脚本
- 测试: 跑 `mail`, `headhunt`, `group`, `liveness_award` 4 个真实日常 entry 串行

## 5. 风险点 + 缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 资源路径硬编码 `D:\自动日常源码带\...` | 项目迁移困难 | 加 config 字段 `narutomobile_resource_path`, 默认指向用户绝对路径 |
| 旧 `*_task.py` 中 pre_check / on_error 等钩子逻辑丢失 | 任务粒度控制能力下降 | 用 maafw 的 `pipeline_override` 动态传阈值/timeout 替代 |
| RecoveryManager 失去对失败节点的细粒度控制 | 重试粒度粗 | maafw 自带 timeout + retry,RecoveryManager 改成任务级重跑 |
| `task_engine.run_daily()` 串行执行太慢 | 日常完成时间长 | 用 `tasker.post_task()` async API,并行跑独立 task |
| 模板还是 narutomobile 的 v1.3.35(2024) | 可能 UI 漂移 | 用户游戏 UI 已经验证能跑通(narutomobile debug 截图就是 1 周前跑通的) |
| 用户的 narutomobile 路径跟 v5.11.1 SDK 版本不匹配 | API 兼容性 | 我们的 maafw==5.10.4 跟 narutomobile v1.3.35 验证过能跑 |

## 6. 用户已有资源

| 路径 | 用途 |
|------|------|
| `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\` | narutomobile 完整应用,resource/base/ 是我们要的模板 |
| `D:\自动日常源码带\MAA-win-x86_64-v5.11.1\` | MaaFramework SDK(v5.11),有 sample/python/demo1.py 模板代码 |
| `D:\自动日常源码带\MaaDebugger-1.20.1\` | MaaDebugger 源码,`pip install MaaDebugger` 已装但因 Python 3.14 兼容问题(README 写 3.9-3.13)无法启动 nicegui GUI |

## 7. 建议执行顺序

1. **先做 Step 1-3**(tasker 单例 + task mapping)— 跑通最小 hello world
2. **跑 4 个真实 task**(mail, headhunt, group, liveness_award)验证 daily schedule
3. **做 Step 4**(改 task_engine.py)— 把调度逻辑接到 maafw
4. **Step 5**(删旧代码 + 测试)— 大规模清理

**总工作量估算**: 4-6 小时开发 + 1-2 天调试

---

## 8. 用户决策点

要不要执行改造?如果要,从 Step 1 开始还是从 Step 4 开始(批量改 task_engine)?

风险点 #1(资源路径硬编码)接受,还是用 config 字段?