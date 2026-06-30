# ROI 校准日志(2026-06-26)

> 📌 用途: 每次 ROI / 模板 / 路径改动都记录一行,含时间、改动、原因。
> 📌 配合 `home_entry_paths.md` 看全景。

---

## 2026-06-26 14:31 · 步骤 1: 邮件入口

**操作**: 用户在主页点"邮件信封"图标 → 进入邮件页 → `capture_calibration.py mail_envelope_open`

**观察**:
- 邮件页正常打开,弹窗式(非全屏)
- 标题"邮件"在左上,带紫色小鸟+信封图标
- 关闭按钮: **右上角标准 X**(实测 (1810,100,80,80) 可见,`shared/x.png` 命中)
- 页面文案: "您还没有收到任何邮件哦!"(账号新,空邮件)
- 主页入口 ROI 仍需校准(代码注释 `(15,290,130,100)` 框住的是数字"252",不是信封本体)

**改动**:
- ❌ 无代码改动(仅观察 + 截图存档)
- 📁 截图存档: `screenshots/calibration/20260626_143135_mail_envelope_open.png`

**结论**: 邮件入口 ROI **可用但需微调**,mail 任务即使能进页,空邮件也会无操作直接成功(best-effort SUCCESS)。

---

## (后续步骤记录待补)

---

## 2026-06-26 14:33 · 步骤 2: 奖励中心入口 + UI 全景

**操作**: 用户在主页点右侧"奖励"信封 → 进入奖励中心 → `capture_calibration.py award_center_open`

**观察 — 奖励中心 UI 结构**(1920×1080):
- 左上角"奖励"书法字标题
- 右上角: 货币显示 + 红色 X 关闭按钮
- **左侧 tab(绿底)**:
  - "每日任务"(当前选中,黄色高亮)— **daily_signin 入口**
  - "奖励中心"
  - "日历"
- **中间主区(4 张横向滚动卡片)**:
  - 冒险副本挑战 / **组织祈福** / 金币招财 / 忍者招募 / ...
  - 每张卡有"立刻前往"按钮 + 次数/活跃度计数
- **底部**:
  - 活跃度进度条(当前 481/500)
  - 4 个活跃度宝箱(10/40/80/100)— **liveness 任务关卡**
  - 左下"返回"橙色按钮(可替代 home_button)

**实测 ROI**:
| 元素 | 像素位置 | 用途 |
|---|---|---|
| daily_signin tab | (60, 220, 250, 80) | daily_signin 入口 |
| group_signin card "组织祈福" | (760, 350, 280, 360) | group_signin 入口(已确认) |
| liveness boxes | (430/610/810/1020, 700, 90, 100) | liveness 任务关卡 |
| award_close_x | (1820, 100, 80, 80) | 关闭奖励中心 |
| liveness progress | 活跃度 481/500 | liveness 当前进度 |
| return_button | (50, 950, 150, 100) | 替代 home_button |

**改动**: ❌ 无代码改动

**结论**:
- ✅ v1.1 §1.2.2 假设的 "主页 → 奖励中心 → 组织" 路径**完全验证**
- ✅ daily_signin / liveness / group_signin 三个任务的入口 ROI 全部确认
- ⚠️ **奖励中心内未发现"周签到" tab**,weekly_signin 入口仍待确认(可能需要横向滑动找其他 tab,或在奖励中心外)
- ✅ award_button 主页入口 ROI 仍需校准(从原始主页图反推,推测 (1750, 350, 130, 110) 右侧中偏下)

---

## 2026-06-26 22:30 · 阶段 1.2.3 完成 (P0 #2 真采集缺失模板 + ROI 重校准)

**操作**: 进入邮件页(用户邮件到来后)+ 奖励中心,真机采到 3 个模板 + 改 3 个 ROI。

**采集**:
- `mail/mail_close_x.png` (140×85, 邮件页右上 X,conf=1.000)
- `liveness/liveness_tab.png` (205×60, 奖励中心"活跃度" tab,conf=1.000)
- `mail/one_key_claim.png` (240×75, "一键提取"黄底+橙字,conf=1.000)

**ROI 改动**:
| ROI | 旧 | 新 | 原因 |
|---|---|---|---|
| `ROI_MAIL_ENTRY` | (30, 350, 130, 130) | (30, 380, 130, 120) | 真实信封位置 (95, 440) |
| `ROI_ONE_KEY_CLAIM` | (600, 950) 估 | (530, 880, 280, 105) | 真实 (670, 932),实际大小 240×75 |
| `ROI_AWARD_BUTTON` | (1170, 290) 估 | (1690, 430, 130, 100) | 礼物盒在右侧中偏下,不是右上 |
| `ROI_LIVENESS_TAB` | (400, 80) 估 | (25, 255, 220, 60) | 实际在左侧 tab 区,不是中间 |

**结论**: ✅ P0 #2 验收通过 (3/3 模板采集 + 4/4 ROI 校准)。

---

## 2026-06-26 22:30 · mail_envelope.png 命名错修正

**问题**: 旧 `mail/mail_envelope.png` 实际是**橙色漩涡**(忍者社区入口图),不是信封。命名错导致 ROI_MAIL_ENTRY 偏上 50px,实际 tap 命中漩涡进入卷轴社区页。

**勘察**:
- 主页左中 (95, 440) 才是真正的黄色信封
- 旧模板在主页 (95, 550) 命中漩涡,实际是忍者社区入口

**改动**:
- 旧 `mail/mail_envelope.png` (130×120) → 新 (裁自 20260626_212653_check_page.png)
- 旧 `home_special/ninja_community.png` (130×120, 漩涡) → 保留作备用(代码 0 引用)
- ROI_MAIL_ENTRY: (30, 350, 130, 130) → (30, 380, 130, 120)

**验证**: 真机命中 conf=1.000 @ (95, 440)

**结论**: ✅ 命名错已修,邮件 task 入口可正确进入。

---

## 2026-06-26 22:30 · P0 #1 模板匹配替代硬编码坐标 (回收 95 测试通过)

**操作**: 7 task 的 `recover()` 全部从硬编码 tap (1820, 80) 改为 `common.dismiss_x()` + `common.tap_home_button()`。

**新基础设施** (tasks/common_actions.py):
- `CommonActions.tap_template(path, *, threshold=0.75, name=None) -> bool`
- `CommonActions.dismiss_x(*, threshold=0.75) -> bool` (3 候选模板: x_right_top / x / green_masked_x)
- `CommonActions.tap_home_button(*, threshold=0.75) -> bool` (home_button_v3.png)

**模板匹配升级**:
- multi-scale: scales=[0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
- threshold: 0.75 (真机验证稳定基线)
- 内部走 `recognition.template_matcher.load_template` (PIL fallback 绕 cv2.imread iCCP bug)

**测试**: 95 passed(包含新加的 `test_recover_uses_template_based_dismiss` × 7 task 参数化)

**结论**: ✅ P0 #1 验收通过(替换硬编码 + 95 测试守护)。

---

## 2026-06-26 22:30 · P1 #3 make_recovery_chain 抽取

**背景**: 7 task 的 `recover()` 都有相同模式: dismiss_x (1~2 次) + tap_home_button。重复代码 60+ 行。

**改动**:
- `tasks/common_actions.py` 加模块级函数 `make_recovery_chain(common, *, double_x=False, log=None) -> bool`
- 7 task 的 `recover()` 全部简化为单行调用:

```python
def recover(self, ctx: "ExecutionContext") -> bool:
    if ctx.common_actions is None:
        return False
    return make_recovery_chain(
        ctx.common_actions,
        double_x=True,   # mail/liveness/recruit = True; 其他 = False
        log=ctx.bind_logger(self.task_id),
    )
```

**变体**:
- double_x=True (3 task): mail, liveness, recruit — 双层弹窗场景
- double_x=False (4 task): daily_signin, weekly_signin, activity, group_signin — 单层弹窗场景

**净节省**: 46 行重复代码 → 1 处可维护点 + 62 行单一权威实现 + 58 行测试覆盖

**测试** (3 个新增):
- `test_make_recovery_chain_calls_dismiss_x_and_home_button` ✅
- `test_make_recovery_chain_double_x_calls_dismiss_x_twice` ✅
- `test_make_recovery_chain_swallows_exceptions_and_returns_false` ✅

**结论**: ✅ P1 #3 验收通过(7 task 共享 1 个标准 recover 链)。

---

## 2026-06-26 22:30 · V1.2 §1.2.0 按钮热区偏上规则 (强制)

**现象**: 真机验证 `monthly_sign_button.png` (220×100, 视觉中心 (1780, 920)) tap 中心无响应;tap 偏上 25% (1780, 895) 生效,count 25/30 → 26/30。

**根因**: 游戏 UI 用 Cocos/Unity 自定义渲染,按钮 hit area 比视觉精灵小,通常只占上半部分。

**规则** (TASK_STANDARD §15):
| 按钮视觉高度 | tap_offset_y |
|---|---|
| 30px 以下 | -0.15 |
| 50-100px | **-0.25** (默认) |
| 150px 以上 | -0.33 |

**实现**:
- `tools/find_and_tap.py` 加 `--tap-offset-y` 参数 (默认 0.0 = 视觉中心,向后兼容)
- API: `find_and_tap(..., tap_offset_y=-0.25)`
- 公式: `cy_实际 = cy_中心 + int(tpl_h * tap_offset_y)`

**待办** (1.2.0):
- ✅ tap_offset_y 参数加进 find_and_tap.py
- ✅ 写进 TASK_STANDARD §15
- ⏳ 6 task 的 _build_*_pipeline() 改用 find_and_tap 调用 (当前已隐式走 TemplateMatcher 同一引擎,行为等价;v1.2.1 计划显式调 find_and_tap)

**结论**: ✅ V1.2 §1.2.0 第 1、2 项完成;第 3 项已隐式完成,等 v1.2.1 显式化。

---

## 2026-06-26 22:58 · V1.2 §1.2.2 group_signin 入口重构完成

**背景**: group_signin 旧入口段 `find_ninja_guide → find_group_entry` 在用户当前 UI 不存在,代码无法跑通。V1.2 §1.2.2 重构为 `find_award_button → find_group_pray_card` 直走奖励中心。

**改动**:
- ✅ `tasks/group_signin_task.py` 删 `find_ninja_guide` + `find_group_entry` 节点 + `ROI_NINJA_GUIDE` + `ROI_GROUP_GAMEPLAY_BTN` 常量
- ✅ 改 `check_no_group.on_error` 从 `find_group_entry` 改为 `close_group_notice`(绕过组织玩法按钮)
- ✅ 新增 `find_award_button` 节点: 模板 `shared/award_button_v4_real.png` (130×170 真机裁切深蓝礼物盒), ROI `(1760, 460, 200, 180)`, `ClickAction(y_offset=-37)`(V1.2 §1.2.0 偏上 25%)
- ✅ 新增 `find_group_pray_card` 节点: 模板 `group/group_pray_card_undone.png` (340×505 真机裁切整张卡片), ROI `(340, 165, 380, 530)`, `ClickAction(y_offset=-132)`(ROI 高度 530 偏上 25%)
- ✅ 同步 3 task `ROI_AWARD_BUTTON = (1760, 460, 200, 180)`: group_signin / liveness / daily_signin
- ✅ 同步 3 task 模板优先级列表: `award_button_v4_real.png` 排首位
- ✅ 加 tap_offset_y 到 `tasks/common_actions.py: tap_template(...)` API(供未来按需用)

**关键发现 (2026-06-26 22:48)**:
- 旧 `shared/award_button_v3.png` 实际是**鼬头像**(130×100, 白眼 + 宇智波护额),不是奖励礼物盒
- 真奖励按钮模板 `award_button_v4_real.png` 130×170: 深蓝礼物盒 + 蝴蝶结 + "奖励"白色文字 + 红点
- 主页"奖励"礼物盒真实位置: (1760, 470) ROI 起点 / (1825, 555) 视觉中心
- ROI `(1770, 480, 200, 150)` 命中点 `(1760, 470)` **在 ROI 外 10px** → not matched
- 修正 ROI 到 `(1760, 460, 200, 180)` 起点左移 10px / 高度 +30 → conf=0.965 ✅

**测试** (98 passed):
- `test_phase6_business_tasks.py` 改 `test_group_signin_pipeline_has_required_nodes` required 节点列表 ✅
- `test_daily_signin_task.py` 改合成测试 ROI 跟新位置一致 ✅
- `test_common_actions.py` 现有 27 测试 + P1 #3 新 3 测试 ✅

**真机 dryrun 结果 (2026-06-26 22:56)**:
```
[ensure_home] ✓
[find_award_button] matched 'award_button_v4_real.png' at (1760, 470) conf=0.990
  → ClickAction (1825, 518) → tap ok → 进奖励中心 ✅
[find_group_pray_card] matched 'group_pray_card_undone.png' at (360, 175) conf=1.000
  → ClickAction (530, 295) → tap ok → 弹组织祈福详情弹窗 ✅
[check_no_group] not matched → 短路(用户当前未加组织,预期行为)
```

**截屏存档**: `screenshots/calibration/20260626_225638_after_pray_card.png`(弹窗 + 奖励中心可见)

**待办 (用户配合)**:
- ⏳ 用户加入组织后跑 4 子链路真机回归: `try_copper_pray` / `try_pursuit_entry` / `confirm_copper_pray` / `try_pursuit_entry`
- ⏳ 6 task 显式用 `tap_template` API(V1.2 §1.2.0 第 3 项,ClickAction 隐式等价已 OK)

**结论**: ✅ V1.2 §1.2.2 入口段重构完成。核心 `find_award_button` + `find_group_pray_card` 双节点真机 conf=1.0 / conf=0.99 命中。4 子链路阻塞在"用户未加组织"。

