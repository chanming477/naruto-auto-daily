# narutomobile 任务操作流程还原

> 逆向对象: `D:\火影自动日常` (本地分支版 narutomobile)
> 还原依据:
> - 任务源码: `tasks/*.py`
> - 模板清单: `resources/templates/**` (按 `actions/<category>/<name>.png` 组织)
> - 共用动作: `tasks/common_actions.py`、`tasks/navigator.py`
> - 状态枚举: `state/game_state.py` (只有 HOME / POPUP / LOADING / UNKNOWN 四态)
> - 屏幕基准分辨率: **1920×1080**,模板按此分辨率匹配;非此分辨率自动 resize

通用约定 (适用于全部任务):
- `pre_check` 通过 `CommonActions.ensure_state(GameState.HOME)` 强校验当前在主页。
- `post_check` 同样 `ensure_state(GameState.HOME)`。
- `recover` 一律使用界面内的 X 按钮或主页橙色按钮 (模板 `shared/x.png` / `shared/home_button_v3.png`),**严禁** `KeyAction("BACK")` —— 会触发"是否退出游戏"系统弹窗。
- `run` 失败时先 `recover` + 1 秒间隔再重试一次,二次仍失败以 `best-effort SUCCESS` 返回 (无奖励是常态,不算故障)。
- 所有 `ClickAction` 点击坐标 = 模板匹配中心点;模板基 1920×1080,实际分辨率下由 `Navigator._unscale_result` 自动回放。
- 阈值(threshold) = 模板匹配置信度阈值,项目里多用 `0.55`(容忍度高)。

---

## 公共前置:启动后到 HOME 的导航 (供所有任务继承)

虽然不在 prompt 的必选任务清单里,但每个任务都以 `ensure_state(GameState.HOME)` 起手,还原流程如下:

**当前画面:** 任意 (POPUP / 加载中 / 战斗结算等)
**寻找:** 无 (不靠模板,靠状态机 `game_sm.current_state`)
**所在区域:** 整个屏幕
**执行:**
1. `CommonActions._is_current_state(HOME)`:截图 → `PageRecognizer.detect_state()` → 已经在 HOME 就立即返 True。
2. 否则按 BACK 键最多 5 次,每次 `safe_back` 后 0.5s 间隔再 detect_state。
3. 仍未到 HOME → 按 1 次 HOME 键 → 再次 detect_state。
4. 失败时 `_reobserve_current_state` 主动重截屏并识别一次 (P1-STABLE-03)。
**成功标志:** `game_sm.current_state == GameState.HOME`。
**失败标志:** 按完 BACK×5 + HOME×1 仍未到 HOME (大概率 ADB 断连,内部抛 fail_streak)。
**恢复:** 各任务自己的 `recover()` 用界面 X 按钮 + 主页按钮兜底。

---

## 公共前置:奖励中心入口 (LivenessTask 与 DailySigninTask 共用)

**当前画面:** HOME (有右上角"奖励"按钮)
**寻找:**
- 模板: `actions/shared/award_button_v3.png`
- 备选: `actions/shared/award_center_entry_v2.png`、`actions/shared/award_center_entry.png`
**所在区域:** `(1170, 290, 130, 100)` (右侧中屏)
**执行:** 点击模板匹配中心点 → `post_delay_ms=1500`
**成功标志:** 出现奖励中心弹窗 (顶部出现"奖励中心"标题 + 横幅 banner_*)。
**失败标志:** 主页背景无变化 / `on_error → verify_done` 直接结束。
**恢复:** 任务级 recover → X + 主页按钮。

---

## MailTask — 邮件一键领取

源码: `tasks/mail_task.py`

### 任务名称
MailTask (`task_id="mail"`, `name="邮件领取"`, `category="daily"`)

### Step1
**当前画面:** HOME
**寻找:**
- 模板: `actions/mail/mail_envelope.png`
- 备选: `actions/home_special/mail_envelope_v2.png`、`actions/home_special/mail_envelope.png` (备选模板**未采集**,此为预留位)
**所在区域:** `(30, 460, 130, 100)` (主页左中偏左 — 截图采集自 `capture_home_entries.py:18` 的 `(60, 475, 100, 100)`)
**执行:** `ClickAction()` 点击信封中心, `post_delay_ms=1500`
**成功标志:** 弹出邮件列表界面。
**失败标志:** 找不到信封 → `on_error → verify_done` (视为"无邮件",直接结束,不抛错)。
**恢复:** 任务级 `recover`:点 `(1826, 84)` 右上 X → 0.5s → 再点 X → 0.5s → 点 `(85, 760)` 左下橙色主页按钮。

### Step2
**当前画面:** 邮件列表页
**寻找:**
- 模板: `actions/mail/one_key_claim.png` (优先,**待采集**)
- 备选: `actions/shared/get.png` (通用领取按钮)
**所在区域:** `(600, 950, 720, 100)` (邮件页底部居中)
**执行:** `ClickAction()` 点击一键提取按钮, `max_hit=3`, `post_delay_ms=1500`
**成功标志:** 出现奖励弹窗 / 附件数量减少 / "已读"标识出现。
**失败标志:** 找不到一键提取 → `on_error → close_mail` (视为"无邮件可领",直接关闭邮件页)。
**恢复:** recover 同 Step1。

### Step3
**当前画面:** 邮件列表页 (Step2 关闭弹窗后回到此页)
**寻找:**
- 模板: `actions/shared/x.png`
- 备选: `actions/shared/green_masked_x.png` (待采集)、`actions/mail/mail_close_x.png` (待采集)
**所在区域:** `(1820, 60, 80, 80)` (邮件页右上角 X)
**执行:** `ClickAction()` 点击关闭按钮, `max_hit=2`, `post_delay_ms=800`
**成功标志:** 邮件页消失,回到 HOME。
**失败标志:** 找不到 X → `on_error → verify_done` (直接结束,通常意味着已在 HOME 或弹窗已自动消失)。

### Task 结束条件
- `verify_done` 节点命中 (= 流水线自然走到终点, 无 `next`)。
- 或重试 2 次仍失败 → 以 `best-effort SUCCESS` 返回 (无邮件奖励是常态,不算异常)。

---

## DailySigninTask — 每日签到

源码: `tasks/daily_signin_task.py`

### 任务名称
DailySigninTask (`task_id="daily_signin"`, `name="每日签到"`, `category="daily"`)

### Step1
**当前画面:** HOME
**寻找:**
- 模板: `actions/shared/award_button_v3.png`
- 备选: `actions/shared/award_center_entry.png`、`actions/shared/award_center_entry_v2.png`
**所在区域:** `(1170, 290, 130, 100)` (右侧中屏)
**执行:** `ClickAction()` 点击"奖励"按钮, `post_delay_ms=1500`
**成功标志:** 进入奖励中心。
**失败标志:** 主页无反应 → `on_error → verify_done`。

### Step2
**当前画面:** 奖励中心
**寻找:**
- 模板: `actions/shared/check_not_in_daily_award.png` (优先 — "未签到"状态,有红点/按钮高亮)
- 备选: `actions/shared/check_in_daily_award.png` ("已签到"灰态)
**所在区域:** `(37, 172, 130, 47)` (奖励中心左上角,沿用 narutomobile 原始 ROI)
**执行:** `ClickAction()` 点击每日签到入口, `post_delay_ms=1000`
**成功标志:** 弹出签到面板 (日历 + 7 天奖励格)。
**失败标志:** 模板未匹配 → `on_error → close_award_center` (跳过签到,直接关奖励中心)。

### Step3
**当前画面:** 签到面板
**寻找:**
- 模板: `actions/shared/x.png`
- 备选: `actions/shared/x_right_top.png`、`actions/shared/green_masked_x.png`、`actions/shared/notice_x.png`
**所在区域:** `(1820, 60, 80, 80)` (面板右上 X)
**执行:** `ClickAction()` 点击关闭, `max_hit=3`, `post_delay_ms=600`
**成功标志:** 签到面板消失,回到奖励中心。
**失败标志:** 模板未匹配 → `on_error → close_award_center` (兜底)。

### Step4
**当前画面:** 奖励中心
**寻找:**
- 模板: `actions/shared/x.png`
- 备选: `actions/shared/green_masked_x.png`、`actions/shared/notice_x.png`
**所在区域:** `(1820, 60, 80, 80)` (奖励中心右上 X)
**执行:** `ClickAction()` 点击关闭, `max_hit=2`, `post_delay_ms=600`
**成功标志:** 奖励中心消失,回到 HOME。
**失败标志:** 模板未匹配 → `on_error → back_to_home`。

### Step5
**当前画面:** HOME (兜底)
**寻找:**
- 模板: `actions/shared/home_button_v3.png`
**所在区域:** `(30, 700, 100, 80)` (主页左下橙色房子按钮)
**执行:** `ClickAction()` 点击主页按钮, `post_delay_ms=800`
**成功标志:** 回到主页 (HOME state)。
**失败标志:** 模板未匹配 → `on_error → verify_done` (已在 HOME 也算完成)。

### Task 结束条件
- `verify_done` 节点命中。
- 或 `check_in_daily_award.png` ("已签到"态) 命中代替 `check_not_in_daily_award.png` 时,说明今日已签过,Step2 仍然会点一次但无副作用。

---

## LivenessTask — 活跃度宝箱 + 周度活跃奖励

源码: `tasks/liveness_task.py`

### 任务名称
LivenessTask (`task_id="liveness"`, `name="活跃度宝箱"`, `category="daily"`)

### 模板清单 (来自 `resources/templates/actions/liveness/`)

| 模板 | 用途 | 在流水线中的角色 |
|---|---|---|
| `liveness_tab.png` | 活跃奖励标签 (顶部 tab) | Step2 切换标签 — **待采集** |
| `weekly_award_undone.png` | 周度奖励"未完成"项 (大盒,带红点) | Step3 周度入口 |
| `confirm_weekly_award.png` | 周度奖励确认按钮 | Step4 确认弹窗 |
| `award_box_all.png` | 一键领取总按钮 (底栏) | Step5 优先 |
| `award_box_100.png` | 100 活跃宝箱 (单点) | Step5 备选 |
| `award_box_80.png` | 80 活跃宝箱 (单点) | Step5 备选 |
| `award_box_40.png` | 40 活跃宝箱 (单点) | 模板存在,**未挂入流水线** |
| `award_box_10.png` | 10 活跃宝箱 (单点) | 模板存在,**未挂入流水线** |
| `box_1_done.png` / `box_1_locked.png` | 1 段奖励格 状态 | 模板存在,**未挂入流水线** |
| `box_2_done.png` / `box_2_locked.png` | 2 段奖励格 状态 | 模板存在,**未挂入流水线** |
| `box_3_done.png` / `box_3_locked.png` | 3 段奖励格 状态 | 模板存在,**未挂入流水线** |
| `box_4_done.png` / `box_4_locked.png` | 4 段奖励格 状态 | 模板存在,**未挂入流水线** |
| `background.png` | 活跃奖励背景 | 模板存在,**未挂入流水线** |

### 点击顺序 (源码 line 64-217 推导)
1. 进奖励中心 (Step1)
2. 切到"活跃奖励"tab (Step2) — 失败则跳到 Step5
3. 点周度未完成大盒 (Step3) — 失败则跳到 Step5
4. 点周度奖励确认 (Step4) — 失败则跳到 Step5
5. 一键领取 (Step5) — 优先 `award_box_all.png`,降级 `award_box_100.png` → `award_box_80.png`
6. 关奖励中心 (Step6)
7. 主页按钮兜底 (Step7)

> 10/40/80/100 单点宝箱模板虽然存在,但**当前流水线只通过 `award_box_all` 一键领取**,不会逐个点 10/40/80/100。要拆开逐点,需要在 Step5 增加 4 个 Click 节点按 ROI 顺序点。

### Step1
**当前画面:** HOME
**寻找:**
- 模板: `actions/shared/award_button_v3.png`
- 备选: `actions/shared/award_center_entry_v2.png`、`actions/shared/award_center_entry.png`
**所在区域:** `(1170, 290, 130, 100)`
**执行:** `ClickAction()` 点击奖励入口, `max_hit=3`, `post_delay_ms=1500`
**成功标志:** 进入奖励中心。
**失败标志:** 找不到 → `on_error → verify_done`。

### Step2
**当前画面:** 奖励中心 (默认在"日常"tab)
**寻找:**
- 模板: `actions/liveness/liveness_tab.png` (优先 — **待采集**)
- 备选: `actions/shared/check_in_daily_award.png`
**所在区域:** `(400, 80, 300, 80)` (顶部 tab 栏左侧)
**执行:** `ClickAction()` 切到活跃奖励标签, `max_hit=2`, `post_delay_ms=1000`
**成功标志:** 标签高亮切到"活跃奖励",下方出现宝箱格。
**失败标志:** 模板未匹配 → `on_error → try_one_click_claim` (跳过切 tab,直接尝试一键领取)。

### Step3
**当前画面:** 活跃奖励 tab
**寻找:**
- 模板: `actions/liveness/weekly_award_undone.png`
**所在区域:** `(1125, 633, 145, 87)` (屏幕右侧偏中部,周度大盒)
**执行:** `ClickAction()` 点击周度未完成大盒, `max_hit=2`, `post_delay_ms=1000`
**成功标志:** 弹出周度奖励确认弹窗。
**失败标志:** 模板未匹配 (本周已领) → `on_error → try_one_click_claim`。

### Step4
**当前画面:** 周度奖励确认弹窗
**寻找:**
- 模板: `actions/liveness/confirm_weekly_award.png`
**所在区域:** `(597, 431, 91, 58)` (弹窗中央偏左,确认按钮)
**执行:** `ClickAction()` 点击确认, `max_hit=2`, `post_delay_ms=800`
**成功标志:** 弹窗消失,周度盒变为已领状态。
**失败标志:** 模板未匹配 → `on_error → try_one_click_claim`。

### Step5 — 一键领取
**当前画面:** 活跃奖励 tab (周度已处理完)
**寻找:**
- 模板: `actions/liveness/award_box_all.png` (优先)
- 备选: `actions/liveness/award_box_100.png`、`actions/liveness/award_box_80.png`
**所在区域:** `(720, 720, 480, 100)` (活跃奖励页底部居中,一键领取按钮)
**执行:** `ClickAction()` 点击一键领取, `max_hit=2`, `post_delay_ms=1200`
**成功标志:** 全部宝箱状态从"未领"变为"已领",底部弹出获得道具提示。
**失败标志:** 模板未匹配 (无活跃度可领) → `on_error → close_award_center`。

### Step6
**当前画面:** 活跃奖励 tab
**寻找:**
- 模板: `actions/shared/x.png`
- 备选: `actions/shared/x_right_top.png`
**所在区域:** `(1820, 60, 80, 80)` (奖励中心右上 X)
**执行:** `ClickAction()` 关闭, `max_hit=2`, `post_delay_ms=800`
**成功标志:** 奖励中心消失,回到 HOME。

### Step7
**当前画面:** HOME (兜底)
**寻找:**
- 模板: `actions/shared/home_button_v3.png`
**所在区域:** `(30, 700, 100, 80)`
**执行:** `ClickAction()` 点主页按钮, `max_hit=2`, `post_delay_ms=800`

### Task 结束条件
- `verify_done` 节点命中。
- 或重试 2 次仍失败 → `best-effort SUCCESS` (无活跃度可领是常态)。

---

## GroupSigninTask — 组织签到

源码: `tasks/group_signin_task.py`

### 任务名称
GroupSigninTask (`task_id="group_signin"`, `name="组织签到"`, `category="daily"`)

> **重要:** 源码里 `group_signin_task.py` 注释和 ROI 都画好了,但流水线**没有真正点"签到"按钮** —— 只走到"进入组织页"就 `confirm_in_group` (Noop) + 关弹窗回主页。当前实现是"打开看一眼"语义,**真正的签到按钮 / 15/20/25 人奖励 / 红包点击都未实现**。下面按源码逐 Step 还原,**实事求是不夸大**。

### Step1
**当前画面:** HOME
**寻找:**
- 模板: `actions/shared/ninja_guide_v3.png`
- 备选: `actions/shared/in_ninja_guide.png` (待采集)、`actions/shared/guide.png` (待采集)
**所在区域:** `(900, 580, 220, 160)` (主页中下部,忍界指引大按钮)
**执行:** `ClickAction()` 点击忍界指引, `post_delay_ms=1500`
**成功标志:** 弹出忍界指引面板 (左侧导航栏 + 右侧内容)。
**失败标志:** 模板未匹配 → `on_error → verify_done`。

### Step2
**当前画面:** 忍界指引面板
**寻找:**
- 模板: `actions/group/group_nav_entry.png` (**待采集**)
- 备选: `actions/shared/in_ninja_guide.png` (用"已在忍界指引"作为 fallback,实际上不会触发点击)
**所在区域:** `(0, 60, 280, 700)` (忍界指引左侧导航栏,从顶到底)
**执行:** `ClickAction()` 点击"组织"导航项, `max_hit=3`, `post_delay_ms=1200`
**成功标志:** 右侧内容区切到组织页 (顶部出现"组织"标题 + 组织签到大盒)。
**失败标志:** 模板未匹配 → `on_error → close_through_pages`。

### Step3
**当前画面:** 组织页 (期望)
**寻找:**
- 模板: `actions/group/in_group_page.png` (**待采集**,用作"确认进入"的标识)
**所在区域:** `(0, 0, 1920, 400)` (顶部标题区)
**执行:** `NoopAction()` — **不点任何东西**,只校验当前画面属于组织页。
**成功标志:** 模板匹配 → 走 `close_through_pages` (仍然没有签到动作)。
**失败标志:** 模板未匹配 → `on_error → close_through_pages`。

### Step4 — 组织签到 + 15/20/25 人奖励 + 红包 (源码中**未实现**)
源码注释提到需要以下模板,但实际 `tpls(...)` 调用里**没有传入任何**:
- 组织签到按钮模板 — 不存在
- 15 人奖励模板 — 不存在
- 20 人奖励模板 — 不存在
- 25 人奖励模板 — 不存在
- 红包模板 — 不存在

要在源码里补上,需要新增 ClickAction 节点,顺序:**签到按钮 → 15 人奖励 → 20 人奖励 → 25 人奖励 → 红包 → 关闭**。当前 `tasks/group_signin_task.py` **没有这些节点**,Step3 之后直接进入关闭流程。

### Step5
**当前画面:** 任意 (兜底关弹窗)
**寻找:**
- 模板: `actions/shared/x.png`
- 备选: `actions/shared/x_right_top.png`、`actions/shared/green_masked_x.png`、`actions/shared/notice_x.png`
**所在区域:** `(1820, 60, 80, 80)`
**执行:** `ClickAction()` 关闭所有弹窗, `max_hit=3`, `post_delay_ms=500`
**成功标志:** 回到 HOME 或无弹窗态。

### Step6
**当前画面:** HOME (兜底)
**寻找:**
- 模板: `actions/shared/home_button_v3.png`
**所在区域:** `(30, 700, 100, 80)`
**执行:** `ClickAction()` 点主页按钮, `post_delay_ms=800`

### Task 结束条件
- `verify_done` 节点命中。
- 重试 2 次仍失败 → `best-effort SUCCESS`。

---

## ShopTask — 商店 (已废弃)

> **2026-06-24 状态:** ShopTask 已废弃。用户在实跑时发现商城免费领奖流程不稳定 (Welfare 入口无明显 "免费" tab、商品价格都是点券支付、ROI 难以精确划分),决定删除整个 ShopTask 模块及配套采集脚本。
>
> 删掉的资产:
> - `tasks/shop_task.py` (移到 `C:\tmp\shop_task_removed.py` 备份)
> - `capture_shop_recruit.py` (移到 `C:\tmp\capture_shop_recruit_removed.py` 备份)
> - `capture_one.py` (移到 `C:\tmp\capture_one_removed.py` 备份)
> - `config/task_registry.yaml` 里的 `shop` 条目
> - `config/schedule.json` 里的 `"shop"` 任务 ID
> - `tasks/__init__.py` 里的 `shop_task` 引用
> - `docs/operation_flows.md` 的 ShopTask 章节 (本节)
> - `docs/COMPLETION_REPORT.md` 里的 ShopTask 部分

---

## RecruitTask — 招募

源码: `tasks/recruit_task.py` (Phase 7+ 补全)

### 任务名称
RecruitTask (`task_id="recruit"`, `name="招募"`, `category="daily"`)

> **当前实现状态:** Pipeline 已按规格搭好,RecruitTask 类已挂到 task_registry (`display_order=7`),`config/schedule.json` 已加入 `recruit`。但 `recruit/*` 4 个专属模板未采集,因此当前以"best-effort SUCCESS"模式运行,实际不会进入招募页。

### Step1
**当前画面:** HOME
**寻找:**
- 模板: `actions/shared/recruit_button_v3.png` (采集坐标 `(1770, 180, 100, 110)`)
- 备选: `actions/home_special/recruit.png` (待采集)、`actions/activity/headhunt.png` (复用活动页的招募入口)
**所在区域:** `(1770, 180, 100, 110)` (右侧靠上,排在活动按钮下方)
**执行:** `ClickAction()` 点击招募入口, `post_delay_ms=2000`
**成功标志:** 进入招募页 (顶部出现"招募"标题 + 多个招募按钮)。
**失败标志:** 模板未匹配 → `on_error → verify_done`。

### Step2
**当前画面:** 招募页
**寻找:**
- 模板: `actions/recruit/free_recruit.png` (待采集 — "免费 1 次"角标)
- 备选: `actions/shared/match.png`
**所在区域:** `(600, 720, 300, 120)` (招募页主面板中偏左)
**执行:** `ClickAction()` 点击免费招募按钮, `max_hit=3`, `post_delay_ms=1500`
**成功标志:** 弹出招募确认弹窗。
**失败标志:** 模板未匹配 (已领过) → `on_error → find_discount_recruit` (跳过免费,直接试一折)。

### Step3
**当前画面:** 招募确认弹窗
**寻找:**
- 模板: `actions/recruit/confirm_recruit.png` (待采集)
- 备选: `actions/shared/confrim.png`、`actions/shared/confrim_small.png`、`actions/shared/get.png`
**所在区域:** `(700, 600, 520, 120)` (弹窗中央偏下)
**执行:** `ClickAction()` 点击确认招募, `max_hit=2`, `post_delay_ms=800`
**成功标志:** 弹窗消失,弹出招募动画。
**失败标志:** 模板未匹配 → `on_error → find_discount_recruit`。

### Step4 — 跳过招募动画
**当前画面:** 招募动画播放中
**寻找:**
- 模板: `actions/recruit/recruit_done.png` (待采集 — "跳过"或"完成"标志)
- 备选: `actions/shared/notice_x.png`、`actions/shared/x.png`
**所在区域:** `(900, 980, 200, 80)` (屏幕底部偏中)
**执行:** `ClickAction()` 点击跳过动画, `max_hit=2`, `post_delay_ms=1500`
**成功标志:** 动画跳过,回到招募页。
**失败标志:** 模板未匹配 (无动画或已跳过) → `on_error → find_discount_recruit`。

### Step5
**当前画面:** 招募页
**寻找:**
- 模板: `actions/recruit/discount_recruit.png` (待采集 — "一折/限时"角标)
- 备选: `actions/shared/match.png`
**所在区域:** `(1020, 720, 300, 120)` (招募页主面板中偏右)
**执行:** `ClickAction()` 点击一折招募按钮, `max_hit=2`, `post_delay_ms=1500`
**成功标志:** 弹出招募确认弹窗。
**失败标志:** 模板未匹配 (一折已领) → `on_error → close_recruit`。

### Step6
**当前画面:** 招募确认弹窗
**寻找:**
- 模板: `actions/recruit/confirm_recruit.png` (待采集)
- 备选: `actions/shared/confrim.png`、`actions/shared/confrim_small.png`、`actions/shared/get.png`
**所在区域:** `(700, 600, 520, 120)`
**执行:** `ClickAction()` 点击确认一折招募, `max_hit=2`, `post_delay_ms=800`
**成功标志:** 弹窗消失,弹出动画。
**失败标志:** 模板未匹配 → `on_error → close_recruit`。

### Step7
**当前画面:** 招募页(动画后)
**寻找:**
- 模板: `actions/shared/x.png`
- 备选: `actions/shared/x_right_top.png`、`actions/shared/green_masked_x.png`、`actions/shared/notice_x.png`
**所在区域:** `(1820, 60, 80, 80)`
**执行:** `ClickAction()` 关闭招募页, `max_hit=2`, `post_delay_ms=800`
**成功标志:** 招募页消失,回到 HOME。

### Step8
**当前画面:** HOME (兜底)
**寻找:**
- 模板: `actions/shared/home_button_v3.png`
**所在区域:** `(30, 700, 100, 80)`
**执行:** `ClickAction()` 点主页按钮, `max_hit=2`, `post_delay_ms=800`

### Task 结束条件
- `verify_done` 节点命中。
- 重试 2 次仍失败 → `best-effort SUCCESS`。

### 待采集模板 (模块顶部 `MISSING_TEMPLATES`)
| 模板路径 | 描述 | ROI |
|---|---|---|
| `recruit/free_recruit.png` | 免费招募按钮 | (600, 720, 300, 120) |
| `recruit/discount_recruit.png` | 一折招募按钮 | (1020, 720, 300, 120) |
| `recruit/confirm_recruit.png` | 招募确认 | (700, 600, 520, 120) |
| `recruit/recruit_done.png` | 跳过动画 | (900, 980, 200, 80) |

---

## 横向汇总:模板与 ROI 速查表

(1920×1080 屏幕基准;ROI = `(x, y, w, h)`)

| 用途 | 模板路径 | ROI | 出现位置 |
|---|---|---|---|
| HOME 15 张基线 | `home/theme1_01_.png` ~ `theme1_15_.png` | 全图 | `state/game_state.py:30` 用于 `detect_state` 投票 |
| 关闭按钮 (右上 X) | `actions/shared/x.png` | (1820, 60, 80, 80) | 任何弹窗 / 子页 |
| 主页按钮 (兜底) | `actions/shared/home_button_v3.png` | (30, 700, 100, 80) | 任何非 HOME 页 |
| 奖励入口 | `actions/shared/award_button_v3.png` | (1170, 290, 130, 100) | HOME 右侧中屏 |
| 活动入口 (右上) | `actions/shared/activity_button_v3.png` | (1770, 30, 100, 110) | HOME 右上 |
| 招募入口 (右上) | `actions/shared/recruit_button_v3.png` | (1770, 180, 100, 110) | HOME 右上 |
| 商店入口 (右侧) | `actions/shared/right_shop_v3.png` | (1770, 340, 100, 110) | HOME 右侧 |
| 商店免费 tab | `actions/shop/free_tab.png` | (0, 200, 1920, 200) | 商店页 (待采集) |
| 商店免费商品卡 | `actions/shop/free_goods_card.png` | (200, 400, 1520, 600) | 商店页 (待采集) |
| 商店一键领取 | `actions/shop/one_key_get.png` | (600, 950, 720, 100) | 商店页 (待采集) |
| 商店购买确认 | `actions/shop/buy_dialog_confirm.png` | (700, 600, 520, 100) | 商店弹窗 (待采集) |
| 招募免费按钮 | `actions/recruit/free_recruit.png` | (600, 720, 300, 120) | 招募页 (待采集) |
| 招募一折按钮 | `actions/recruit/discount_recruit.png` | (1020, 720, 300, 120) | 招募页 (待采集) |
| 招募确认弹窗 | `actions/recruit/confirm_recruit.png` | (700, 600, 520, 120) | 招募弹窗 (待采集) |
| 招募跳过动画 | `actions/recruit/recruit_done.png` | (900, 980, 200, 80) | 招募动画 (待采集) |
| 忍界指引入口 | `actions/shared/ninja_guide_v3.png` | (900, 580, 220, 160) | HOME 中下 |
| 每周签到入口 | `actions/shared/weekly_sign_v3.png` | (510, 540, 250, 110) | HOME 中部 |
| 邮件信封入口 | `actions/mail/mail_envelope.png` | (30, 460, 130, 100) | HOME 左中 |
| 每日签到入口 | `actions/shared/check_not_in_daily_award.png` | (37, 172, 130, 47) | 奖励中心 |
| 周度活跃未领 | `actions/liveness/weekly_award_undone.png` | (1125, 633, 145, 87) | 活跃奖励 tab |
| 周度奖励确认 | `actions/liveness/confirm_weekly_award.png` | (597, 431, 91, 58) | 周度奖励弹窗 |
| 一键领取 (活跃) | `actions/liveness/award_box_all.png` | (720, 720, 480, 100) | 活跃奖励 tab 底部 |
| 100 活跃宝箱 | `actions/liveness/award_box_100.png` | 同上 ROI | 活跃奖励 tab |
| 80 活跃宝箱 | `actions/liveness/award_box_80.png` | 同上 ROI | 活跃奖励 tab |
| 40 活跃宝箱 | `actions/liveness/award_box_40.png` | (未挂入流水线) | 活跃奖励 tab |
| 10 活跃宝箱 | `actions/liveness/award_box_10.png` | (未挂入流水线) | 活跃奖励 tab |
| 通用领取 | `actions/shared/get.png` | 弹窗底部 | 任意领取弹窗 |
| 通用确认 | `actions/shared/confrim.png` | 弹窗中央 | 任意确认弹窗 |
| 通用确认 (小) | `actions/shared/confrim_small.png` | 弹窗中央 | 任意确认弹窗 |
| 取消 | `actions/shared/cancel.png` | 弹窗底部 | 任意弹窗 |
| 启动 logo | `actions/startup/naruto_logo.png` | — | 启动屏 |
| 启动主界面 | `actions/startup/main.png` | — | 启动后 |
| 进入游戏 | `actions/startup/start_game.png` | — | 启动后 |
| 青少年弹窗 | `actions/startup/teenager_page.png` | — | 启动后首次 |
| 弹窗关闭 | `popup/close_x.png` | — | 任意弹窗 |

---

## 结论

- **5 个已实现:** MailTask / DailySigninTask / LivenessTask / GroupSigninTask / RecruitTask。
- **ShopTask 已废弃:** 商城免费领奖流程不稳定 (Welfare 入口无明显"免费"tab、商品价格都是点券、ROI 难划),模块已删除,备份在 `C:\tmp\shop_task_removed.py`。
- **额外实现:** WeeklySigninTask (每周签到)、ActivityTask (一乐外卖/体力追回) — 不在 prompt 必选清单,但代码里已落地。
- **GroupSigninTask 半成品:** 走到"打开组织页"为止,真正的签到按钮 / 15-20-25 人奖励 / 红包点击都没接 (`tpls(...)` 只留了占位)。
- **RecruitTask 已落地为业务模块:** Pipeline / 类 / 注册表 / scheme 全部就位,但 `recruit/*` 4 个专属模板待采集,当前仍以"best-effort SUCCESS"模式运行。
- 真实流水线**只用模板匹配** (`TemplateMatcher`),**没有 OCR** — prompt 例子里的 "OCR文字" 在当前实现里**不适用**,全部依赖视觉模板。
- 所有任务的 recover 策略统一:界面内 X 按钮 (1820, 60) + 主页橙色按钮 (85, 760),**不调系统 BACK**。
- 详细补全记录见 `docs/COMPLETION_REPORT.md`。