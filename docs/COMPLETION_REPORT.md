# RecruitTask 补全报告

> 规格输入: `docs/operation_flows.md`
> 实施日期: 2026-06-24
> 实施范围: 按规格文档补全招募任务(商城 shop 已废弃,见末尾)
>
> **变更记录 (2026-06-24 22:57):**
> ShopTask 由用户决定废弃(商城流程 ROI 不稳 / 无明显"免费"tab / 全部是点券商品)。
> 删掉的资产备份在 `C:\tmp\` 下 (`shop_task_removed.py` / `capture_shop_recruit_removed.py` /
> `capture_one_removed.py`),`task_registry.yaml` 与 `schemes/daily.json` 已同步移除 shop 条目。

---

## 一、目标

按照 `docs/operation_flows.md` 的规格,把"现状:未实现"的招募任务(RecruitTask)从纯文档变成真正可执行的业务模块。

完成后任务满足:
1. 有独立 `tasks/recruit_task.py` 文件 + `RecruitTask` 类(继承 `BaseTask`)。
2. 有完整的 Pipeline 节点 + ROI + 模板路径清单。
3. 已注册到 `config/task_registry.yaml`,会被 `Scheduler` 按 `display_order=6` 自动加载。
4. 已加入 `schemes/daily.json`,按顺序执行。
5. 失败/模板缺失时返回 `best-effort SUCCESS`,不阻塞后续任务。
6. 与现有任务一致使用 `PipelineRunner` + `Navigator` + `CommonActions`。

---

## 二、文件清单

### 新增 (1)
| 文件 | 行数 | 说明 |
|---|---|---|
| `tasks/recruit_task.py` | ~340 | RecruitTask 类 + `_build_recruit_pipeline` + 6 ROI + 4 待采集模板 |

### 修改 (3)
| 文件 | 变更 |
|---|---|
| `config/task_registry.yaml` | 追加 `recruit` (order=6) 任务条目;补 Phase 7+ 注释 |
| `schemes/daily.json` | 在 `task_ids` 末尾追加 `"recruit"` |
| `tasks/__init__.py` | `__all__` 加上 `recruit_task`,版本号 0.3.1 → 0.3.2 |
| `docs/operation_flows.md` | RecruitTask 章节按完整规格输出;ShopTask 章节替换为废弃说明;结论章节更新 |

---

## 三、Pipeline 结构 (RecruitTask — 10 节点)

```
ensure_home
  └─> find_recruit_entry      [ClickAction, ROI=右侧 (1770,180,100,110)]
        └─> find_free_recruit     [ClickAction, ROI=主面板中偏左]
              └─> confirm_recruit    [ClickAction, ROI=弹窗中央]
                    └─> find_skip_anim   [ClickAction, ROI=屏幕底部偏中]
                          └─> find_discount_recruit  [ClickAction, ROI=主面板中偏右]
                                └─> confirm_discount   [ClickAction, ROI=弹窗中央]
                                      └─> close_recruit       [ClickAction, X 按钮]
                                            └─> back_to_home        [ClickAction, 主页按钮]
                                                  └─> verify_done
```

降级路径(全部 `on_error`):
- `find_recruit_entry` 失败 → `verify_done` (入口找不到就放弃)
- `find_free_recruit` 失败 → `find_discount_recruit` (跳过免费,直接试一折)
- `confirm_recruit` / `find_skip_anim` 失败 → `find_discount_recruit`
- `find_discount_recruit` 失败 → `close_recruit` (一折也领过,关掉)
- `confirm_discount` 失败 → `close_recruit`
- `close_recruit` 失败 → `back_to_home`
- `back_to_home` 失败 → `verify_done`

---

## 四、模板依赖

### RecruitTask (4 个待采集)
| 路径 | 描述 | ROI |
|---|---|---|
| `recruit/free_recruit.png` | 免费招募按钮 | (600, 720, 300, 120) |
| `recruit/discount_recruit.png` | 一折招募按钮 | (1020, 720, 300, 120) |
| `recruit/confirm_recruit.png` | 招募确认 | (700, 600, 520, 120) |
| `recruit/recruit_done.png` | 跳过动画 | (900, 980, 200, 80) |

入口 `shared/recruit_button_v3.png` **已存在**,实跑只需要采集上述 4 个。

采集脚本可参考 `capture_all_templates.py` / `capture_award_center.py`,按 ROI 切图存到 `resources/templates/actions/recruit/` 即可。脚本会自动被 `Navigator.templates(...)` 找到。

---

## 五、行为契约

### 与现有任务一致 (沿用 Phase 6 约定)
- `pre_check` 调 `CommonActions.ensure_state(HOME)`
- `post_check` 同样 `ensure_state(HOME)`
- `recover` 用 `(1826, 84)` X + `(85, 760)` 主页按钮兜底,**不调系统 BACK**
- `run` 失败时先 `recover` + 1s 间隔,再 `_run_pipeline` 一次
- 二次仍失败 → `best-effort SUCCESS` 返回,无奖励 / 模板缺失是常态

### 与现有任务差异
- `category = "daily"`(沿用 mail / liveness / group_signin 的分类)
- `max_retries = 0`(避免 BaseTask 模板方法的双层重试叠加 `run` 内部的 recover+重试)
- `task_id` / `name` / `display_order` 见 `task_registry.yaml`

---

## 六、ShopTask 废弃记录 (2026-06-24)

| 资产 | 状态 |
|---|---|
| `tasks/shop_task.py` | 移到 `C:\tmp\shop_task_removed.py` 备份 |
| `capture_shop_recruit.py` | 移到 `C:\tmp\capture_shop_recruit_removed.py` 备份 |
| `capture_one.py` | 移到 `C:\tmp\capture_one_removed.py` 备份 |
| `task_registry.yaml` shop 条目 | 已删除 |
| `schemes/daily.json` shop 任务 | 已删除 |
| `tasks/__init__.py` shop_task | 已从 `__all__` 移除 |
| `docs/operation_flows.md` ShopTask 章节 | 替换为废弃说明 |

废弃原因(用户决定):
- 商城免费领奖流程 ROI 不稳定(顶部 tab 是按忍者等级分,不是按价格)
- Welfare 入口没有明显的"免费"标签
- 所有商品都是点券支付,与"一键领取"假设不符
- 整套 ROI 难以精确划分

---

## 七、验证清单

| 项 | 期望 | 实际 |
|---|---|---|
| RecruitTask 模块能 import | 无异常 | ✅ `python -c "from tasks.recruit_task import RecruitTask"` 通过 |
| Pipeline 节点结构 | 10 节点 | ✅ `pipe.entry == "ensure_home"`,节点序列与设计一致 |
| task_registry.yaml 加载 | 5 个任务(无 shop) | ✅ mail / liveness / group_signin / daily_signin / recruit |
| schemes/daily.json 加载 | 顺序正确 | ✅ `["mail", "liveness", "group_signin", "daily_signin", "recruit"]` |
| ShopTask 不可 import | ImportError | ✅ `from tasks.shop_task import ShopTask` 抛 ImportError |
| recover 不调 BACK | recover() 只用 tap | ✅ 全部为 `adb.tap(...)`,无 `keyevent("BACK")` |

---

## 八、给后续接手同学的一句话

> **RecruitTask 代码已落地,采集完 4 个模板即可实跑。** 任务以"best-effort SUCCESS"模式安全运行,不阻塞其它日常任务,也不会误触发"退出游戏"系统弹窗(全部用界面 X 按钮)。ShopTask 已废弃,如需恢复请从 `C:\tmp\shop_task_removed.py` 还原并重新设计 ROI。