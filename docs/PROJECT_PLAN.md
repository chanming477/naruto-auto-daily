# 火影手游自动日常 — 项目执行计划书 v1.2

> **核心目标**: 把 `D:\火影自动日常` 从"代码已写完但跑不通"变成"6 个核心任务真机稳定跑通 + 可持续维护扩展"
>
> **使用方式**: 本文件是**自包含**的执行计划,新对话里只读这一份就能准确执行。每个阶段都有明确的输入 / 任务清单 / 输出 / 验收 / 工作量。
>
> **创建日期**: 2026-06-25
> **最新更新**: 2026-06-26(v1.2 — 全图模板匹配定为标准方案 + 按钮热区偏上规则)
> **预计总工作量**: 8-12 工作日
> **执行模式**: 顺序执行(强依赖) + 阶段内可并行

---

## 第 0 阶段 · 项目压缩上下文

> 📌 **新对话必读**: 这一节是整个项目的"压缩快照",执行任何阶段前都要先读这一节。

### 0.1 项目是什么

- **目标**: 火影忍者手游"日常任务"自动点击工具,在 MuMu 模拟器上跑
- **路径**: `D:\火影自动日常`
- **入口**: `main.py`(`python main.py --task <task_id>`)
- **风格**: Python + ADB 截图 + OpenCV 模板匹配 + (新加)rapidocr OCR + (新加)PIL 截图
- **参考项目**: `D:\自动日常源码带\narutomobile-main`(MaaFramework JSON pipeline,我们移植成 Python)

### 0.2 现状(2026-06-26)

| 维度 | 状态 |
|---|---|
| **代码逻辑** | ✅ 7 个任务全部写完(mail / daily_signin / liveness / group_signin / recruit / activity_task / weekly_signin) |
| **Pipeline 节点数** | 6-28 节点/任务 |
| **P0 守护** | ✅ `pre_flight()` + `ensure_game_in_foreground()` 已加 |
| **OCR 接入** | ✅ `OCRAction` + `rapidocr-onnxruntime` lazy load 已加(但游戏文本召回低,**降级为辅助**) |
| **green_mask** | ✅ `Node.green_mask` + `_match_green_channel()` 已加 |
| **PIL 截图工具** | ✅ `core/screenshot_utils.save_image_pil()` 已加(绕开 cv2.imwrite iCCP bug) |
| **通用找按钮工具** | ✅ `tools/find_and_tap.py` 已加(全图模板匹配 + ADB tap,**v1.2 起为标准方案**) |
| **全图模板匹配** | ✅ 多尺度 0.85-1.15 + threshold 0.75,跨分辨率鲁棒,对菜单滚动/位置变化鲁棒 |
| **知识库** | ✅ `docs/game_wiki/*.md` × 7 已写完 |
| **开发标准** | ✅ `docs/standards/TASK_STANDARD.md` 已写完 |
| **模板清单** | ✅ `resources/templates/template_manifest.json` (143 张) + 真机重裁 `screenshots/calibration/templates/*.png` |
| **真机跑通** | ✅ **2 任务真机跑通**(weekly_signin 6/26 + group_signin 入口段 6/26 22:56 双节点 conf=0.99/1.00); 其余 5 任务待 §2 阶段全量回归 |
| **OCR 召回率** | ⚠️ 全屏 OCR 命中 22 条,但"组织/前往/追击/签到/奖励/铜币/宝箱/活跃"目标字全部未命中(**v1.2 起主方案改为全图模板匹配**) |
| **按钮热区偏上规则** | ✅ **真机验证**(2026-06-26): 橙色签到按钮热区比视觉小约 50%,tap 点要落在裁图范围的上半部分(详见 §1.2.0) |
| **裁图精度工作流** | ✅ **裁图分工**: 粗裁(菜单项)→ 自己裁;精度敏感(按钮热区)→ 喊用户帮忙裁 |

### 0.3 核心阻塞问题(必须先解决)

1. **入口 ROI 全部失真** — 用户当前游戏主页底部 tab 没有"忍界指引"(只有 忍者/天赋/装备/通灵/秘卷/装扮)
2. **关键模板内容错误**:
   - `shared/ninja_guide_v3.png` 实际是场景背景图
   - `group/group_list.png` 实际是排行榜文字
   - `group/copper_pray.png` 实际是铜币图标
   - `group/group_gameplay_undone.png` 实际是橙色分隔条
3. **OCR 模型召回率低** — rapidocr 默认模型对游戏装饰字体识别精度不够
4. **每周签到入口路径错误** — ~~假设的"主页→奖励中心→周签到 tab"路径不存在~~ ✅ **已修复**(2026-06-26): 真实路径是"主页右上角活动图标 → 活动页 → 左侧菜单每月签到";narutomobile 的 5 个 `monthly_sign_*` 模板是**节日变体**,当前 7 月非节日 UI 不匹配
5. **按钮热区比视觉小** — ✅ **已识别**(2026-06-26): 真机验证橙色签到按钮热区比截取范围小约 50%,实际可点区域只在裁图的上半部分;详见 §1.2.0 规则

### 0.4 真机关键事实

- **设备**: `127.0.0.1:16384`(MuMu 模拟器 v12)
- **ADB 路径**: `D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe`
- **游戏包名**: `com.tencent.KiHan`
- **启动 Activity**: `com.tencent.KiHan.MainActivity`
- **模拟器物理**: 1080×1920(竖屏)
- **游戏输出**: 1920×1080(横屏)— 参考分辨率统一用这个
- **关键真机截图**: `screenshots/dryrun_current.png`(主页) / `screenshots/dryrun_v2/00_with_rois.png`(ROI 框图) / `screenshots/dryrun_v3/test_pil.png`

### 0.5 参考资源

| 类型 | 路径 | 用途 |
|---|---|---|
| **narutomobile 源码** | `D:\自动日常源码带\narutomobile-main\` | pipeline 设计参考 |
| **narutomobile 真机运行日志** | `D:\自动日常源码带\运行日志\log_20260625_204044.zip\` | 实跑截图 + 错误截图 |
| **narutomobile 6/18 组织任务运行日志** | `logs/log-20260618.log` | 组织任务成功案例(可参考的"组织玩法未完成"等节点名) |
| **narutomobile 6/18 组织祈福页截图** | `debug/on_error/2026.06.18-22.30.56.728_close_second_group_award_box.png` | 真实组织祈福页 UI(可作为 ROI 校准参考) |
| **narutomobile 6/19 招募页截图** | `debug/on_error/2026.06.19-10.36.49.972_no_free_headhunt.png` | 招募页 UI 参考 |
| **本项目任务 wiki** | `docs/game_wiki/*.md` × 6 | 任务详细说明 |
| **本项目开发标准** | `docs/standards/TASK_STANDARD.md` | 任务开发必读 |
| **本项目模板清单** | `resources/templates/template_manifest.json` | 143 张模板元数据 |

### 0.6 必须遵守的硬约束(所有阶段)

| 约束 | 来源 |
|---|---|
| ❌ 永不使用系统 BACK 键(`KeyAction(key="BACK")`) | 触发"是否退出游戏"弹窗 |
| ✅ 用 `shared/x.png` 关弹窗, 用 `shared/home_button_v3.png` 回主页 | 当前项目惯例 |
| ✅ 所有截图落盘用 `core.screenshot_utils.save_image_pil()`, 不用 `cv2.imwrite` | iCCP bug |
| ✅ 所有真机调试截图也用 `save_image_pil()` | 统一截图工具链 |
| ✅ **找按钮默认用 `tools/find_and_tap.py` 全图模板匹配**(v1.2 起为标准) | 游戏 UI 非标准控件,OCR 召回低,模板匹配跨分辨率鲁棒 |
| ✅ OCR 仅作为辅助(rapidocr-onnxruntime, 不引入 pytesseract) | 当前项目决策 |
| ✅ **按钮热区偏上: 实际 tap 点要落在裁图范围的上半部分**,不能点视觉中心 | 2026-06-26 真机验证: 橙色签到按钮热区比视觉小约 50% |
| ✅ **裁图分工**: 粗裁(菜单项,容差 ±20px)→ 自己裁;精度敏感(按钮热区,容差 ±10px)→ 喊用户帮忙裁 | 用户原话: "你裁剪的不准确,用我裁剪的,需要裁剪的时候可以让我帮忙" |
| ✅ 修改 Navigator / TaskEngine / TemplateMatcher / RecoveryManager 前需先确认 | 用户明确禁止重构 |
| ✅ 修改任何 ROI / 模板必须在对应 wiki 里记录 | 知识库约束 |
| ✅ best-effort SUCCESS: 大多数任务找不到入口 / 已完成也返回 SUCCESS | 当前惯例 |
| ❌ 不重写 TaskEngine / Navigator | 用户明确禁止 |
| ❌ 不引入新框架 | 用户明确禁止 |

---

## 第 1 阶段 · 真机 ROI 重校准 + 关键模板重采集

> 📌 **触发**: 完成第 0 阶段(已完成)
> 🎯 **目标**: 把 6 个任务的入口 ROI 全部校准到用户当前游戏, 重新采集错位的关键模板
> ⏱️ **工作量**: 3-5 工作日
> 🔗 **依赖**: 无(基于已完成的 P0 工具)
> ✅ **验收**: `dryrun_<task>.py` 在真机上能走到"操作按钮点击"步骤(不一定到完成,但至少进入任务页)

### 1.1 输入

- 当前主页截图(`screenshots/dryrun_current.png` 或重新截一张)
- 当前 6 任务的代码(已存在)
- 模板清单 + 命名约定(已存在)
- capture_* 工具(已存在:`tools/capture_template.py` 等)

### 1.2 任务清单(按优先级)

#### 1.2.0 [P0, 0.5 天] find_and_tap 通用工具 + 按钮热区偏上规则(v1.2 核心)

> 📌 **为什么这是 v1.2 第一个任务**: 之前所有 ROI 校准都用"估坐标 + 单尺度模板匹配",跨分辨率失效 / 菜单滚动后失效;OCR 也召回低。本节定下两个**硬规则**,所有后续 ROI/模板工作都按这两条来。

**1) `tools/find_and_tap.py` 通用工具**(已实现,2026-06-26)

**用法**:

```bash
# 干跑(只找位置不点)
python tools/find_and_tap.py screenshots/calibration/templates/<name>.png --no-tap --debug

# 真点(默认)
python tools/find_and_tap.py screenshots/calibration/templates/<name>.png

# 自定义多尺度(默认 0.85,0.9,0.95,1.0,1.05,1.1,1.15)
python tools/find_and_tap.py <tpl>.png --scales 0.95,1.0,1.05 --threshold 0.75

# 找不到先 swipe 再找(滑动菜单场景)
python tools/find_and_tap.py <tpl>.png --swipe-before 800,400,200,400 --swipe-retry 3
```

**核心参数**:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--threshold` | 0.75 | 匹配置信度阈值(0.0-1.0);真机验证 0.75 是稳定基线 |
| `--scales` | 0.85..1.15(7 档) | 多尺度列表,跨分辨率鲁棒 |
| `--max-retries` | 3 | 找不到时的最大重试次数 |
| `--swipe-before x1,y1,x2,y2,duration` | — | 先 swipe 再找(菜单未展开场景) |
| `--swipe-retry N` | 0 | swipe 后重试匹配次数 |
| `--no-tap` | False | 只匹配不点击 |
| `--debug` | False | 把匹配框画到截图上(注:debug 图走 cv2.imwrite 有 iCCP bug,实际不可见,仅日志有 conf) |

**匹配算法**:

- 用 `cv2.matchTemplate` (TM_CCOEFF_NORMED) 在全图扫
- 7 档 scale × 7 档 scale,对模板 resize 后匹配
- 取所有 scale 中的 max_val,若 ≥ threshold 则返回 (cx, cy, scale)
- 内部走 `recognition.template_matcher.load_template`(PIL fallback,绕 cv2.imread iCCP bug)

**产出位置**:

- 工具: `tools/find_and_tap.py`
- 模板: `screenshots/calibration/templates/<name>_<context>.png`(每个按钮单独裁图)
- 命名规范: `<domain>_<context>.png`,例如 `monthly_signin_menu_item.png` / `monthly_sign_button.png`

**已知 bug**:

- `save_debug()` 用 cv2.imwrite → 静默失败(路径返回但文件不存在)。不影响匹配/点击功能,只是 debug 图看不到。如需 debug 图,手动跑 `python -c "from core.screenshot_utils import save_image_pil; ..."` 走 PIL 写。

---

**2) 按钮热区偏上规则**(真机验证,2026-06-26)

**现象**:

- 截取的按钮模板(220×100)→ 视觉上完整包含按钮
- 但 tap 模板中心 (cx, cy) **无响应**
- tap 模板偏上位置 (cx, cy - 25%) → **生效**

**根因(猜测)**:

- 游戏 UI 用 Cocos/Unity 自定义渲染,按钮的 hit area **比视觉精灵小**
- 通常热区只占视觉区域的上半部分或上半三分之一
- 视觉下半部分可能被阴影/文字装饰/空白占据,不是真正的 click 区域

**规则**:

| 按钮视觉高度 | 实际 tap y 偏移 |
|---|---|
| 30px 以下(小图标) | -5px(顶上一格) |
| 50-100px(普通按钮) | **-25% 高度**(上半中心) |
| 150px 以上(大卡片) | -33% 高度(上 1/3 中心) |
| 不确定 | **从偏上 25% 开始试**,不响应再往上挪 |

**`find_and_tap.py` 的 `tap_offset_y` 参数**(待加):

```bash
# 让 tap 自动偏上 25%(推荐作为默认行为)
python tools/find_and_tap.py <tpl>.png --tap-offset-y -0.25
```

> 📌 **TODO**: `find_and_tap.py` 当前版本没有 `tap_offset_y` 参数,需要时手动算坐标(tap 时 `cy = match_cy - int(tpl_h * 0.25)`)。后续 PR 加这个参数并设为默认。

**真机验证案例**(2026-06-26):

- 模板 `monthly_sign_button.png` (220×100, 中心 (1780, 920))
- tap (1780, 920) → ❌ 无响应(我先 tap 中心)
- tap (1770, 895) → ⚠️ 看似无响应,但实际已生效(UI 延迟刷新)
- 最终确认: tap 偏上位置 **生效**,count 从 25/30 → 26/30,day 26 出现"已签"红章

---

**任务清单** (§1.2.0 内):

- [x] 实现 `tools/find_and_tap.py`(多尺度 + ADB tap)
- [x] 真机验证: weekly_signin 入口(每月签到菜单项)和签到按钮
- [ ] `find_and_tap.py` 加 `tap_offset_y` 参数并默认 -0.25
- [ ] 把"按钮热区偏上规则"加进 `docs/standards/TASK_STANDARD.md`
- [ ] 现有 6 个任务的 `_build_*_pipeline()` 全部改用 `find_and_tap` 调用(替代固定 ROI)

#### 1.2.1 [P0, 1 天] 主页入口全部任务路径勘察

**做什么**: 在用户当前游戏里**实际走一遍**所有任务的入口路径,记录每一步的:

- 模板视觉描述(是什么图标 / 文字)
- 像素坐标(精确到 ±20px)
- 截图(`screenshots/calibration/home_<入口名>.png`)

**具体路径**(2026-06-26 真机勘察版):

| 任务 | 主页入口 | 备注 |
|---|---|---|
| `mail` | 主页左中部"邮箱"图标 | 真实坐标待 §1.2.3 校准;ROI 估不准,改用 `mail/mail_envelope_template.png` 模板 + find_and_tap |
| `daily_signin` | 主页右上"奖励"信封 | 真实坐标待 §1.2.3 校准;**禁止用 OCR**找"签到"字 |
| `liveness` | 主页右上"奖励"信封 → 奖励中心 → 活跃度宝箱 | 横向 swipe 路径待测;改用模板 + swipe-before 找宝箱图标 |
| `group_signin` | **⚠️ 当前 UI 没有"忍界指引", 必须从奖励中心 → 组织 tab** | **完全重新设计** |
| `recruit` | 主页右上"招募"图标 | 已识别在 (1770, 180, 100, 110) 区域;改用 `recruit/recruit_button_template.png` 模板 |
| `activity_task` | 主页右上"活动"图标 (1835, 70) | ✅ **真机验证 2026-06-26**: 主页右上角横向并排两图标,左"功夫季"(1680, 70) + 右"活动"(1835, 70);**注意 (1820, 80) 是忍界指引弹窗的 X 关闭按钮,容易误点** |
| `weekly_signin` | **主页右上"活动"(1835, 70) → 活动页 → 左侧菜单"每月签到" → 中间事件区"签到"按钮** | ✅ **真机跑通 2026-06-26**: 不是"奖励中心 → 周签到 tab";narutomobile 5 个 `monthly_sign_*` 是**节日变体**,当前 7 月非节日 UI 已改版,需用真机重裁模板 |

**主页右上角布局关键发现**(2026-06-26):

```
(1680, 70) 功夫季 (1820, 80) X关闭 (1835, 70) 活动
       ←—— 横向并排 ——→
```

- **不能点 (1820, 80)** — 那是忍界指引弹窗的 X 关闭按钮,容易和活动图标位置重叠
- "活动"图标的视觉中心是 **(1835, 70)**,但热区可能在更靠上的位置(用 find_and_tap + tap_offset_y=-0.25)

**活动页左侧菜单**(swipe 后可见,2026-06-26 真机):

```
龙舟送礼 → 决赛报名 → 每月福袋 → 疾风传登录 → 分级单挑
↓ swipe
→ 每月签到(本次真机签到入口) → 节日日历 → 登录送Sign → ...
```

**产出**:

- `docs/calibration/home_entry_paths.md`(新增)
- `screenshots/calibration/` 目录(每任务 3-5 张截图)

**模板**:

- `tools/capture_template.py` 加新任务入口截图
- 修正 `shared/recruit_button_v3.png` / `shared/award_button_v3.png` / `shared/right_shop_v3.png` 等的 ROI

#### 1.2.2 [P0, 1 天] group_signin 入口完全重构 ✅

**状态**: ✅ 2026-06-26 22:58 完成(代码 + 测试 + 真机 dryrun 双节点命中)

**为什么优先**: narutomobile 假设的"主页 → 忍界指引 → 组织"路径在用户当前 UI **完全不存在**。

**新入口路径**(实测真机):

```
主页 → 奖励中心 → 组织祈福卡片 → (已加组织) 组织祈福页 / (未加组织) 详情弹窗
```

**降级方案**: 如果用户未加入组织:
- ✅ `group_signin_task.pre_check()` 行为:进"详情弹窗", `check_no_group` 节点短路,后续节点 fail 兜底 best-effort SUCCESS
- ✅ 不阻塞其他任务
- ⏳ 待用户加入组织后跑 4 子链路真机回归(`try_copper_pray` / `confirm_copper_pray` / `try_pursuit_entry` / ...)

**v1.2 实现**(实测真机):

- ✅ 不用手算 ROI 坐标,用全图模板匹配(多尺度 scale=[0.85..1.15], threshold=0.55 节点级 / 0.75 全图)
- ✅ 新模板清单(全部真机裁切):
  - `shared/award_button_v4_real.png` (130×170 真机裁切深蓝礼物盒,**注意**: 旧 `award_button_v3.png` 实际是鼬头像)
  - `group/group_pray_card_undone.png` (340×505 真机裁切整张卡片,含"立刻前往"按钮)
- ✅ ROI 校准:
  - `ROI_AWARD_BUTTON = (1760, 460, 200, 180)` — **起点左移 10px** (避免命中点 (1760, 470) 落在 ROI 外)
  - `ROI_GROUP_PRAY_CARD = (340, 165, 380, 530)`
- ✅ ClickAction 应用 V1.2 §1.2.0 tap 偏上规则: `y_offset=-37` (find_award_button ROI h=150 × -0.25) / `y_offset=-132` (find_group_pray_card ROI h=530 × -0.25)
- ✅ 同步 3 task 的 ROI_AWARD_BUTTON: group_signin / liveness / daily_signin

**真机 dryrun 结果**(2026-06-26 22:56):
```
[ensure_home] ✓
[find_award_button] matched 'award_button_v4_real.png' at (1760, 470) conf=0.990 → tap (1825, 518) → 进奖励中心 ✅
[find_group_pray_card] matched 'group_pray_card_undone.png' at (360, 175) conf=1.000 → tap (530, 295) → 弹组织祈福详情弹窗 ✅
[check_no_group] not matched → 短路(用户当前未加组织,预期行为)
[4 子链路] 待用户加组织后跑
```

**产出**:

- ✅ `group_signin_task.py` 的 `_build_group_signin_pipeline()` 重写入口段(保留 4 子链路,改入口)
- ✅ 调用全图模板匹配 + ClickAction(y_offset=V1.2 §1.2.0)
- ✅ 98/98 测试通过
- ⏳ 用户加入组织后跑 4 子链路真机回归
- 删除或重命名错误模板(移到 `templates/deprecated/`)

#### 1.2.3 [P1, 半天] 邮件 / 招募 / 活跃度 ROI 微调

**做什么**: 校准 3 个入口已识别但 ROI 可能漂移的任务。**v1.2 起全部改用 find_and_tap 全图匹配**,不维护 ROI 字段。

**邮件**:

- 主页邮箱入口: 用 `mail/mail_envelope_template.png`(真机重裁) + find_and_tap
- ~~`mail/mail_envelope.png` 用 OCR 替代模板~~ **v1.2 取消**: OCR 召回低,改用模板匹配更稳

**招募**:

- 主页招募入口: 用 `recruit/recruit_button_template.png` + find_and_tap(1770, 180 坐标仅作参考,实际匹配位置由工具决定)
- 招募页内"免费 1 抽"按钮: `recruit/free_headhunt_template.png` + find_and_tap

**活跃度**:

- 主页奖励入口: `shared/award_button_template.png` + find_and_tap
- 奖励中心 → 活跃度宝箱: 用 `swipe-before` 横向 swipe 后找 `liveness/box_template.png`

**产出**:

- 3 个任务的 `_build_*_pipeline()` 中所有 TapClick 节点改用 `find_and_tap` 调用
- 真机重裁模板 4-6 张
- `template_manifest.json` 不再维护 ROI 字段(改记 `template_path` + `context`)

#### 1.2.4 [P2, 不推荐] OCR 模型升级(可选, v1.2 起降级)

**为什么降级**: v1.2 起主方案已改为全图模板匹配,**OCR 不再是必备**。OCR 升级只在"实在找不到可裁的模板"时才考虑。

**方案 A(若需, 1 小时)**: 改用更精准的 PP-OCRv3 模型:

```python
# rapidocr 支持 params 切换
from rapidocr_onnxruntime import RapidOCR
engine = RapidOCR(
    det_model_path="ch_PP-OCRv3_det_infer.onnx",
    rec_model_path="ch_PP-OCRv3_rec_infer.onnx",
)
```

**方案 B(若需, 更简单)**: 在每个 OCR 节点加 ROI 限制 + 多个 OCR 阈值尝试:

```python
# 跑全屏 OCR 找到 ROI 内匹配位置
# 不直接改引擎
```

**产出**: OCR 召回率从"目标 8 字 0 命中"提升到 ≥ 6/8 命中(如果做)。

**v1.2 现状**: `OCRAction` 保留作为辅助,但所有新代码不再默认调用 OCR 节点。

#### 1.2.5 [P1, 半天] dryrun_<task>.py 7 个任务各跑一次

**做什么**: 每个任务写一个 `dryrun_<task>.py` 脚本(参照已存在的 `dryrun_v3.py`),在真机跑一次,截图存盘。

**产出**:

- `dryrun_mail.py` / `dryrun_daily_signin.py` / `dryrun_liveness.py` / `dryrun_group_signin.py` / `dryrun_recruit.py` / `dryrun_activity.py` / **`dryrun_weekly_signin.py`**(v1.2 新增)
- 每个脚本输出 "成功走到 N 步" / "失败原因: 模板 conf<0.75 / OCR 未命中"
- 7 个脚本统一调用 `find_and_tap` 替代直接 `TapClick`
- **weekly_signin 已经有真机记录**(2026-06-26, count 25/30→26/30,day 26 红章)

### 1.3 输出物

| 文件 | 描述 |
|---|---|
| `docs/calibration/home_entry_paths.md` | 主页入口路径勘察记录 |
| `docs/calibration/roi_calibration_log.md` | ROI 校准日志(每次改动记录时间/原因) |
| `screenshots/calibration/` | 校准用截图集 |
| 6 个任务的 `dryrun_*.py` | 验证脚本 |
| `templates/deprecated/` | 错误模板归档 |
| `resources/templates/template_manifest.json` | 更新后的清单 |
| 6 个 `docs/game_wiki/*.md` | 更新 ROI 字段 |

### 1.4 验收标准

✅ **必须满足**:

- **✅ weekly_signin 已真机跑通**(2026-06-26): 活动页入口+签到按钮 tap 都成功
- 7 个 dryrun_*.py 都能跑完(不抛异常)
- 至少 5 个任务能进到任务页(走完 find_entry 节点)
- 至少 3 个任务能完成主操作(成功领取/签到/招募)
- 所有任务入口都用 `find_and_tap` 全图匹配调用,**不再用固定 ROI 坐标**
- `template_manifest.json` 中 `captured_at` 字段填入(校准日期)
- 7 个 wiki 的 `template_path` 字段全部更新到最新值(ROI 字段可废弃)

❌ **未满足**:

- 任何 dryrun 跑不到 find_entry 节点 = 没进任务页 = 任务失败
- 模板内容与命名不符(例如 `group/copper_pray.png` 还是图标) = 重采不彻底
- 用 ROI 坐标代替 find_and_tap = 违反 v1.2 标准

### 1.5 工作量明细

| 子任务 | 工作量 |
|---|---|
| 1.2.0 find_and_tap 工具 + 热区偏上规则 | 0.5 天 ✅(已实现 6/26) |
| 1.2.1 主页入口勘察 | 1 天 ✅(已实现 6/26 22:30) |
| 1.2.2 group_signin 入口重构 | 1 天 ✅(已实现 6/26 22:58) |
| 1.2.3 mail/recruit/liveness ROI 微调 | 0.5 天 ✅(已在 P0 #2 完成) |
| 1.2.4 OCR 模型升级(可选,已降级) | 跳过 |
| 1.2.5 7 个 dryrun 脚本 | 0.5 天 ✅(已实现 6/26 22:20) |
| **总计** | **3-3.5 天**(已完成 3 天工作量,**阶段 1 主线完成**) |

### 1.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 用户当前游戏确实没有"组织"入口 | group_signin 无法实现 | 改从奖励中心进,或文档标记为"需用户加入组织" |
| **OCR 召回率低** | ~~原计划用 OCR 找文本节点失败~~ | ✅ **v1.2 已解决**: 主方案改全图模板匹配,OCR 仅辅助;rapidocr 模型升级不再是必备 |
| 新采集的模板仍然失真 | ROI 漂移 | 在 capture 脚本里加"截图后人工确认内容"步骤;**v1.2 起由用户帮忙裁精度敏感模板** |
| 模拟器分辨率变化 | 所有 ROI 失效 | ~~已支持 `set_resolution_scale`~~ v1.2 起 ROI 不是主方案,**改用多尺度模板匹配**(0.85-1.15)天然跨分辨率鲁棒 |
| **按钮热区比视觉小** | tap 中心不响应 | ✅ **v1.2 已识别**: tap_offset_y=-0.25 规则(见 §1.2.0),真机验证 weekly_signin |
| 节日/版本更新导致模板失效 | UI 改版,模板匹配 conf < 0.75 | 保留 narutomobile 节日变体模板作参考;UI 改版后用真机重裁;**主流程永远用真实截图模板,不用 narutomobile 老模板** |

---

## 第 2 阶段 · 全部任务真机回归测试

> 📌 **触发**: 第 1 阶段验收通过(至少 4 个任务能进任务页)
> 🎯 **目标**: 6 个任务在真机上**稳定跑完主流程**,每个任务至少 5 次连续成功
> ⏱️ **工作量**: 2-3 工作日
> 🔗 **依赖**: 第 1 阶段 ROI 已校准
> ✅ **验收**: 6 个任务各跑 5 次,成功率 ≥ 80%

### 2.1 输入

- 第 1 阶段 ROI 已校准
- `pre_flight()` + `ensure_game_in_foreground()` 已生效
- PIL 截图工具可用
- OCR 引擎可用
- **已有资产可复用**:
  - `tests/test_phase6_integration.py` — 4 个真机集成测试(可直接扩展为回归脚本)
  - `recovery/RecoveryManager` — 4 场景恢复(recover_unknown / recover_popup / recover_loading_timeout / recover_adb_error),建议每个 dryrun 前后调用

### 2.2 任务清单

#### 2.2.1 [P0, 0.5 天] 单元测试: pipeline 状态机回归

**做什么**: 给 6 个任务的 `_build_<task>_pipeline()` 各写一个 mock dry-run,验证:

- 节点数符合预期
- entry 节点存在
- 所有 `next` 链能到达终点
- `on_error` 链覆盖常见失败

**产出**:

- `tests/test_pipeline_<task>.py` × 6
- 在 `tests/__init__.py` 加测试 runner 脚本

**验收**: 6 个测试通过(`pytest tests/`)

#### 2.2.2 [P0, 1 天] 真机回归: 6 个任务各跑 5 次

**做什么**: 写 `tests/regression_real.py`,依次跑 7 个任务,每个任务 5 次连续执行,记录每次成功率 / 失败原因。

**流程**:

```python
# tests/regression_real.py
from recovery.recovery_manager import RecoveryManager

for task in [mail, daily_signin, liveness, group_signin, recruit, activity, weekly_signin]:
    for attempt in range(5):
        # 每任务前:用 RecoveryManager 确保在 HOME
        if game_sm.current_state == GameState.UNKNOWN:
            recovery_mgr.recover_unknown()
        result = run_task(task, ctx)
        log.info(f"{task} attempt {attempt+1}: {result.status}")
        # 每任务后:确保回到主页
        common.go_home()
```

**产出**:

- `logs/regression_<日期>.log` 7 任务 × 5 次 = 35 次记录
- 每任务成功率统计

**验收**: 每个任务成功率 ≥ 80%

#### 2.2.3 [P1, 0.5 天] 修复回归发现的问题

**做什么**: 把回归测试中失败的任务逐个修复:

- ROI 再校准
- 模板再采集
- Pipeline 节点增加/调整
- OCR 阈值调整

**最常见的修复**:

- 节点 `post_delay_ms` 不够 → 加大
- `max_hit` 不够 → 加到 3
- `on_error` 链不全 → 补上
- OCR 没命中 → 阈值降到 0.3 或换模板

**顺便清理的 5 项遗留 P0**(低风险低成本的已知 bug):

| 编号 | 文件 | 问题 |
|---|---|---|
| P0-BUG-01 | `core/screenshot_manager.py:235` | `[:,:,::1]` 无效 copy + BGR 转换错误 |
| P0-BUG-02 | `core/screenshot_manager.py:100` | PrintWindow 失败返回不可靠图像 |
| P0-REG-01 | `core/scheduler.py:238` | `run_single` 文档与实现不一致 |
| P0-BUG-04 | `tasks/common_actions.py:158` | `safe_back(max_retries)` 参数死代码 |
| P0-STABLE-01 | `ui/log_panel.py:167` | `_append_colored_line` 行限制只删一个字符 |

**验收**: 重跑回归,全部 ≥ 80%

#### 2.2.4 [P1, 0.5 天] 集成测试: 任务链(多个任务连续跑)

**做什么**: 写 `tests/integration.py`,模拟用户一天的实际操作流程:

```python
# 任务链(参考 narutomobile 6/25 运行日志)
sequence = [
    "mail", "daily_signin", "recruit",  # 早上:邮件 + 签到 + 招募
    "liveness", "group_signin",         # 中午:活跃度 + 组织
    "activity_task", "weekly_signin",   # 晚上:活动 + 周签到
]
for task in sequence:
    run_task(task, ctx)
    sleep(2)  # 任务间隔
```

**特别关注**:

- 任务间状态是否污染(narutomobile 6/25 教训)
- `pre_flight` 是否真的把游戏带回前台
- 任务结束是否真的回到主页

**验收**: 完整任务链跑通 1 次无异常

### 2.3 输出物

| 文件 | 描述 |
|---|---|
| `tests/test_pipeline_<task>.py` × 6 | 单元测试 |
| `tests/regression_real.py` | 真机回归脚本 |
| `tests/integration.py` | 集成测试脚本 |
| `logs/regression_<日期>.log` | 回归日志 |
| `docs/standards/TROUBLESHOOTING.md` | 常见问题排查手册(从回归失败经验提炼) |

### 2.4 验收标准

✅ **必须满足**:

- 6 个任务各 5 次连续成功率 ≥ 80%
- 集成测试(任务链)1 次跑通
- `tests/regression_real.py` 在 `pytest` 里可调用
- `TROUBLESHOOTING.md` 至少 5 个真实失败案例 + 修复方法

❌ **未满足**:

- 任何任务成功率 < 80% = 阶段未完成
- 集成测试中间抛异常 = 任务间状态污染没解决

### 2.5 工作量明细

| 子任务 | 工作量 |
|---|---|
| 2.2.1 单元测试 | 0.5 天 |
| 2.2.2 真机回归 | 1 天 |
| 2.2.3 修复问题 | 0.5 天 |
| 2.2.4 集成测试 | 0.5 天 |
| **总计** | **2.5 天** |

### 2.6 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 任务间状态污染(6/25 教训) | 后续任务找不到主页 | pre_flight + 任务结束 ensure_state(HOME) |
| 模拟器内存累积崩溃 | 长时间跑后崩溃 | 集成测试加 watchdog(每 N 任务重启模拟器) |
| OCR 阈值漂移(白天 vs 晚上) | 不同光照下识别率不同 | OCR 节点加 `time_of_day` 配置, 阈值自适应 |

---

## 第 3 阶段 · ShopTask 实现

> 📌 **触发**: 第 2 阶段验收通过(6 任务跑通)
> 🎯 **目标**: 实现 wiki 先行但代码缺失的 ShopTask
> ⏱️ **工作量**: 半天 - 1 天
> 🔗 **依赖**: 阶段 2 (其他奖励中心类任务已跑通)
> ✅ **验收**: ShopTask 真机跑通(特权商店 tab → 铜币兑换 → 关闭 → 主页)

### 3.1 输入

- `docs/game_wiki/shop.md` 已写完(节点设计已规划)
- narutomobile `Activity.json` 特权商店节点可参考
- 已有的奖励中心任务(liveness / daily_signin)可作为参考

### 3.2 任务清单

#### 3.2.1 [P0, 0.5 天] 模板采集 + 入口勘察

**做什么**:

- 在用户当前游戏里找到商城入口(`shared/right_shop_v3.png` 是否还有效?)
- 进特权商店,采集:
  - `Shop/shop_entry.png` (如果有入口页)
  - `Shop/privilege_points.png` (铜币兑换按钮)
  - `Shop/privilege_points_without_recharge.png` (无充值态)
- OCR 文字位置: "特权商店" / "商店" / "领取" / "立即充值"

**产出**: 模板 2-4 张(有些可能用 OCR 替代)

#### 3.2.2 [P0, 半天] 创建 `tasks/shop_task.py`

**做什么**: 按 `docs/game_wiki/shop.md` 的设计实现:

```python
class ShopTask(BaseTask):
    task_id = "shop"
    # ... pre_check / post_check / recover / run 同其他任务

def _build_shop_pipeline(nav):
    # 8 节点骨架(参考 liveness_task.py)
```

**关键设计点**(已写进 wiki):

- OCR "特权商店" / "商店" 切 tab
- OCR "领取" 兑奖
- OCR "立即充值" 判定不可领
- 用 `Shop/privilege_points.png` 半图模板避开红色充值按钮

**产出**: `tasks/shop_task.py`

#### 3.2.3 [P1, 0.5 天] 真机测试 + dryrun 脚本

**做什么**: `dryrun_shop.py` 跑一次,修复 ROI/OCR 问题。

**产出**:

- `dryrun_shop.py`
- 更新 `template_manifest.json` task=shop 部分

### 3.3 输出物

| 文件 | 描述 |
|---|---|
| `tasks/shop_task.py` | ShopTask 实现 |
| `resources/templates/actions/Shop/*.png` | 新增模板 2-4 张 |
| `dryrun_shop.py` | 验证脚本 |
| `resources/templates/template_manifest.json` | 更新 |

### 3.4 验收标准

✅ ShopTask 真机跑通(成功进入特权商店 + 找到领取按钮 + 关闭)
✅ `template_manifest.json` 中 task=shop 部分齐全

### 3.5 工作量

0.5 - 1 天

### 3.6 风险

- 特权商店 VIP 等级限制 → 用 OCR "立即充值" 判定跳过
- 商城改版 → OCR 兜底

---

## 第 4 阶段 · 持续维护机制建立

> 📌 **触发**: 第 2 阶段验收通过(6 任务稳定)
> 🎯 **目标**: 让项目可以**长期被接手**,建立工具和流程
> ⏱️ **工作量**: 1 天
> 🔗 **依赖**: 阶段 2 任务稳定
> ✅ **验收**: 接手者读 1 份 onboarding 文档就能跑通 + 修改 ROI

### 4.1 任务清单

#### 4.1.1 [P0, 0.5 天] 工具脚本完整化

**做什么**:

- 完善 `tools/generate_template_manifest.py`(已存在,加 captured_at 字段自动填充 mtime)
- 新增 `tools/check_template_drift.py`(扫描模板,标记 30 天未更新的)
- 新增 `tools/roi_calibration_helper.py`(输入截图 + 模板,自动算 ROI 候选)

**产出**: `tools/` 目录工具体系

#### 4.1.2 [P0, 半天] ONBOARDING.md

**做什么**: 给接手者写一份 30 分钟跑通的指南:

- 环境要求(Python 版本 / ADB 路径 / 模拟器)
- 第一次跑通的完整步骤(从 git clone 到任务成功)
- 常见踩坑
- 关键文件位置索引

**产出**: `docs/ONBOARDING.md`

#### 4.1.3 [P1, 0.5 天] 模板治理细则

**做什么**:

- 新增 `templates/deprecated/` 子目录(已规划,实际创建)
- 新增 `templates/DEPRECATION.md`: 模板废弃流程
- 新增 `templates/CHANGELOG.md`: 模板变更记录(自动生成)

**产出**: 模板治理细则

### 4.2 输出物

- `tools/` 完整工具集
- `docs/ONBOARDING.md`
- `templates/DEPRECATION.md`
- `templates/CHANGELOG.md`(自动生成脚本)

### 4.3 验收

接手者(可以是其他 AI 模型)只读 `ONBOARDING.md` 就能:

1. 配置环境
2. 跑一个任务到成功
3. 修改 ROI 并验证
4. 新增一个任务(参考 wiki + TASK_STANDARD)

### 4.4 工作量

1 天

---

## 第 5 阶段 · 高级扩展(可选)

> 📌 **触发**: 第 1-4 阶段全部完成 + 用户明确同意扩展
> 🎯 **目标**: 让项目从"日常工具"升级为"完整工具集"
> ⏱️ **工作量**: 5+ 工作日(可拆分)
> 🔗 **依赖**: 阶段 4 维护机制已建立
> ✅ **验收**: 用户自定义指标

### 5.1 可选扩展清单

| 优先级 | 扩展项 | 工作量 | 价值 |
|---|---|---|---|
| P0 | ROI 自动校准工具(基于多张截图 + 模板匹配,自动算最佳 ROI) | 1-2 天 | 高 |
| P1 | 支持多账号(配置文件区分不同 adb serial + 不同账号的任务队列) | 1 天 | 中 |
| P1 | 任务执行可视化(Web UI / 截图时间轴) | 2-3 天 | 中 |
| P2 | 异常告警(企业微信 / 钉钉 / 邮件) | 0.5 天 | 低 |
| P2 | 录像功能(每次跑任务录一段视频,失败时回放) | 1 天 | 中 |
| P3 | 智能调度(根据用户活跃时间自动执行) | 2 天 | 低 |
| P3 | 游戏版本检测(自动检测 UI 变化提示重新校准) | 1 天 | 中 |

### 5.2 何时启动

- 第 1-4 阶段全部完成 + 用户主动提出需求
- **不要自动启动**, 这是可选的

---

## 工作量汇总

| 阶段 | 内容 | 工作量 | 触发 |
|---|---|---|---|
| 0 | 项目压缩上下文 + 知识库 + 标准 + 模板清单 | ✅ 已完成 | — |
| 1 | ROI 重校准 + 模板重采集(7 任务) | 3-3.5 天 ✅ **主线完成**(1.2.0/1.2.1/1.2.2/1.2.3/1.2.5) | — |
| 2 | 真机回归 + 集成测试 | 2.5 天 ⏳ **待启动** | 用户加组织后 |
| 3 | ShopTask 实现 | 0.5-1 天 | 阶段 2 完成 |
| 4 | 持续维护机制 | 1 天 | 阶段 2 完成 |
| 5 | 高级扩展(可选) | 5+ 天 | 用户主动 |
| **总计** | | **7-13 天** | |

## 里程碑

```
M0 (✅ 已完成): 项目现状诊断 + 知识库 + 标准 + 模板清单
  ↓
M0.5 (✅ 已完成 2026-06-26): find_and_tap 工具 + 按钮热区偏上规则 + weekly_signin 真机跑通
  ↓
M1 (✅ 已完成 2026-06-26 22:58): 阶段 1 主线(1.2.0/1.2.1/1.2.2/1.2.3/1.2.5) + group_signin 入口段双节点真机命中(conf=0.99/1.00); 剩余 group_signin 4 子链路 + 6 任务全量回归待阶段 2
  ↓
M2 (待启动): 7 任务稳定 80%+ 成功率, 集成测试通过
  ↓
M3 (M2 后): ShopTask 跑通, 8 任务覆盖完整日常
  ↓
M4 (M3 后): 持续维护机制建立, 项目可被接手
  ↓
M5 (可选): 高级扩展按需启动
```

---

## 度量指标(每阶段都要检查)

| 指标 | 目标 | 如何测量 |
|---|---|---|
| **任务成功率** | ≥ 80%(5 次连跑) | `tests/regression_real.py` |
| **OCR 召回率** | ≥ 6/8 目标字命中 | 跑全屏 OCR + 关键字搜索 |
| **模板清单完整度** | 100% 任务都有 manifest 字段 | `python tools/generate_template_manifest.py` + diff |
| **wiki 完整度** | 100% 任务都有 wiki | `ls docs/game_wiki/` |
| **P0 守护有效率** | 100% 任务被 pre_flight 覆盖 | 读 `core/base_task.py` |
| **可接手度** | 30 分钟跑通 | 模拟新对话,只看 ONBOARDING.md |

---

## 给新对话的执行建议

### 如果是新对话,只读这一份计划书

1. **先读 §0 阶段"项目压缩上下文"** — 了解项目是什么, 现状如何, 阻塞在哪
2. **确认要执行哪一阶段**(根据用户当前需求)
3. **按该阶段 §任务清单 执行**
4. **对照 §验收标准 自查**
5. **如阶段失败**: 看 §风险与缓解, 调整策略

### 关键命令速查

```bash
# 启动环境
python -c "from device.adb_client import ADBClient; a = ADBClient(adb_path=r'D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe', serial='127.0.0.1:16384'); print(a.connect())"

# 截图
python -c "from device.adb_client import ADBClient; from core.screenshot_utils import save_image_pil; a = ADBClient(adb_path=r'D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe', serial='127.0.0.1:16384'); r = a.screenshot(); save_image_pil(r.payload, 'screenshots/_check.png')"

# 跑任务
python main.py --task <task_id>

# 验证 pipeline
python -c "from tasks.<task>_task import _build_<task>_pipeline; print(_build_<task>_pipeline(Navigator(FakeADB(), ...)))"

# 生成 manifest
python tools/generate_template_manifest.py
```

### 不要做的事情

- ❌ 重写 Navigator / TaskEngine / TemplateMatcher / RecoveryManager
- ❌ 引入新框架(pytesseract / easyocr / paddleocr / MaaFramework)
- ❌ 用 `cv2.imwrite`(用 `save_image_pil`)
- ❌ 用 `KeyAction(key="BACK")`
- ❌ 不读这一份就直接动手
- ❌ 重新创建 `scripts/` 目录(所有工具已统一到 `tools/`)

---

## 修订记录

| 日期 | 版本 | 改动 |
|---|---|---|
| 2026-06-25 | 1.0 | 初版,基于 6/25 长期可维护改造完成报告 |
| 2026-06-25 | 1.1 | 路径修正(scripts/→tools/)、任务数 6→7 补充 weekly_signin、补充 RecoveryManager 复用建议、补充 group_signin 降级方案、补充 5 项遗留 P0、硬约束增补 PIL 截图、更新 daily.json 任务数 |
| 2026-06-26 | 1.2 | **核心架构变更**: OCR/固定ROI → **全图模板匹配**(标准方案);新增 `tools/find_and_tap.py`;新增 **§1.2.0** find_and_tap 工具 + **按钮热区偏上规则**(tap_offset_y=-0.25,真机验证);weekly_signin 真机跑通(活动页 → 每月签到 → 偏上 tap 橙色按钮,count 25/30→26/30);OCR 降级为辅助;真机重裁模板 `screenshots/calibration/templates/*.png`;narutomobile 节日变体模板归档 `narutomobile_ref/Activity/`;主页右上角布局勘察(功夫季/活动/忍界指引X);活动页左侧菜单含"每月签到";"裁图请用户帮忙"写入硬约束;里程碑新增 M0.5 |
| 2026-06-26 22:58 | 1.3 | **V1.2 §1.2.2 完成**: group_signin 入口段重构(`find_ninja_guide→find_award_button` + `find_group_entry→find_group_pray_card`);新模板 `shared/award_button_v4_real.png` (130×170 真机裁切深蓝礼物盒,**注意**: 旧 `award_button_v3.png` 实际是鼬头像);ROI_AWARD_BUTTON 修正 `(1760, 460, 200, 180)` (起点左移 10px 避免命中点落在 ROI 外);3 task 同步;ClickAction 应用 y_offset V1.2 §1.2.0;dryrun 入口段双节点真机 conf=0.99/1.00 命中; **M1 里程碑达成**(阶段 1 主线全部完成) |