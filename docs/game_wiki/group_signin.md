# 组织签到 / GroupSigninTask

> **Task ID**: `group_signin`
> **Task 类**: `tasks.group_signin_task.GroupSigninTask`
> **Category**: daily
> **状态**: 代码完成 (P9-GRP 4 子链路), 真机 dry-run 受 ROI 漂移阻塞
> **最后更新**: 2026-06-25
> **相关模板**: 43 张 (group/* 整个目录)
> **P0 已修复**: green_mask + OCR "前往"/"追击" + pre_flight 守护

---

## 1. 入口在哪

### 主页入口(从 narutomobile 假设)

- **路径**: 主页 → 忍界指引(底部圆形 tab 之一) → "组织" → 组织玩法按钮 → 签到
- **当前项目模板**: `shared/ninja_guide_v3.png` (忍界指引) — ROI `(900, 580, 220, 160)`
- **实际情况**: 用户当前主页**底部 tab 不含"忍界指引"** (只有 忍者/天赋/装备/通灵/秘卷/装扮)
- ⚠️ **ROI 漂移严重** — 需要重新校准入口路径

### 备选入口(从奖励中心)

- **路径**: 主页 → 奖励中心 → 组织 tab
- **模板**: `group/group_ac_undone.png` (奖励中心内的"组织祈福"图标) ROI `[180, 288, 1100, 225]` 带 `green_mask: true`
- ⚠️ 当前项目未实现此入口

### 关键观察(narutomobile 6/18 实测截图)

- narutomobile 在 6/18 跑组织任务成功走完 5 步(进入组织任务 → 组织玩法未完成 → 确认选中 → 进入组织签到 → 铜币签到)
- 6/18 on_error 截图 `2026.06.18-22.30.56.728_close_second_group_award_box.png` 显示**真实的组织祈福页 UI**(橙色"组织祈福"标题 + 寺庙场景 + 15/20/25 人宝箱在右侧)
- 6/25 因为 close_qq_app 把游戏切后台,组织任务在入口就失败

---

## 2. 页面长什么样

### 组织玩法主页(`group_main`)

- **左侧列表**: 多个玩法入口(图标+文字)
  - 组织玩法(竖向图标, ROI `[44, 382, 177, 118]`)
  - 公告(顶部可能)
- **顶部**: 公告弹窗(常见) — 用 `notice_x.png` 关

### 组织祈福页(`group_pray`)— 核心子任务所在

基于 narutomobile 6/18 22:30:56 实跑截图:

- **左上角**: 橙色大字"组织祈福"(标题)
- **左中部**: 第 N 层 / 加持 / 功勋收益 / 上周密令 / 本周密令
- **左中下**: **前往追击晓组织**(蓝色文字按钮)
- **左下**: 祈福日志(图标) / 返回(黄色三角)
- **中央**: 寺庙祈福场景(佛塔 + 灯笼 + 蒲团)
- **底部**: 焚香祈福 / 纳贡祈福 / 虔诚祈福 / **超影免费祈福**
- **右侧**(竖向排列):
  - **15 人宝箱** — ROI `(1154, 374, 85, 80)`(可领) / `(1158, 380, 68, 59)`(已领)
  - **20 人宝箱** — ROI `(1166, 268, 77, 66)`(可领) / `(1171, 279, 59, 44)`(已领)
  - **25 人宝箱** — ROI `(1153, 154, 88, 83)`(可领) / `(1155, 161, 61, 59)`(已领)
- **右上角**: 红色 X 关闭按钮

### 追击晓组织页(`group_pursuit`)

- **左中**: "追击"文字按钮(OCR) — ROI `(59, 444, 311, 118)`
- **中部**: 每日/每周奖励可领(竖向排列) — `dawn_organization_award_waiting.png`
- **右下**: **一键领取** — `one_key_dawn_organization_award.png` — 注意:这是**滑动条, 用 SwipeAction 不是 ClickAction**

---

## 3. 常见按钮 / 文字 / 图标

### 入口层

| 元素 | 模板/文字 | ROI | 用途 |
|---|---|---|---|
| 忍界指引(旧) | `shared/ninja_guide_v3.png` | (900, 580, 220, 160) | ⚠️ 当前 UI 不存在 |
| 组织玩法按钮 | `group/group_gameplay_undone.png` | (44, 382, 177, 118) | 进组织页 |
| 未加组织判定 | `group/group_list.png` | (94, 30, 474, 173) | 短路跳过 |
| 公告弹窗 | `group/notice_x.png` | (706, 157, 274, 172) | 关公告 |

### 签到层

| 元素 | 模板/文字 | ROI | 用途 |
|---|---|---|---|
| **"前往"按钮** | **OCR "前往"** (替代 `selected_group_gameplay_undone_button.png`) | (239, 533, 178, 144) | 进签到页 |
| 铜币签到 | `group/copper_pray.png` | (476, 542, 200, 80) | 铜币签到按钮 |
| 超影签到 | `group/above_kage_pray.png` | (753, 550, 44, 42) | 超影签到(可选) |
| 签到确认 | `group/confirm_group_pray.png` + `confirm_copper_pray_done.png` | (657, 477, 605, 175) | Click 确认 |

### 宝箱层(15/20/25 人宝箱)

| 元素 | 模板 | ROI |
|---|---|---|
| 15 人可领 | `first_box_wait.png` | (1154, 374, 85, 80) |
| 15 人已领 | `first_box_done.png` | (1158, 380, 68, 59) |
| 20 人可领 | `second_box_wait.png` | (1166, 268, 77, 66) |
| 20 人已领 | `second_box_done.png` × 3 变体 | (1171, 279, 59, 44) |
| 20 人红包 | `group_pray_red_packet.png` | (585, 181, 102, 80) |
| 20 人红包已开 | `group_pray_red_packet_done.png` | (627, 182, 27, 32) |
| 20 人红包文字 | `group_pray_red_packet_text.png` | (555, 124, 170, 48) |
| 25 人可领 | `third_box_wait.png` | (1153, 154, 88, 83) |
| 25 人已领 | `third_box_done.png` | (1155, 161, 61, 59) |

### 追击晓层

| 元素 | 模板/文字 | ROI | 用途 |
|---|---|---|---|
| "追击"按钮 | **OCR "追击"** (替代 `group_pray_to_pursuit_dawn_organization.png`) | (59, 444, 311, 118) | 进追击页 |
| 奖励可领 | `dawn_organization_award_undone.png` | (496, 594, 61, 54) | Click 领取 |
| 奖励已领 | `dawn_organization_award_done.png` | (496, 589, 59, 54) | Noop 跳过 |
| 奖励堆叠 | `dawn_organization_award_waiting.png` | (985, 175, 143, 474) | 一列多个 |
| **一键领取(Swipe)** | `one_key_dawn_organization_award.png` | (454, 429, 71, 47) | **SwipeAction 不是 Click** |

### 昨日奖励层

| 元素 | 模板 | ROI | 备注 |
|---|---|---|---|
| 昨日奖励入口 | `yesterday_award.png` | (402, 135, 200, 175) | **`green_mask: true`** (避开红点) |
| 领取按钮 | `get_yesterday_award.png` | (722, 185, 149, 444) | |
| 关闭 | `yesterday_award_done.png` | (983, 191, 181, 158) | |

---

## 4. 成功条件

### 子链路 4: 昨日奖励
- `yesterday_award.png` 未命中 → 无奖励 → 直接跳到铜币签到
- 命中 → 点 `get_yesterday_award.png` → 关闭弹窗 → 进入铜币签到

### 子链路 1: 铜币签到
- `copper_pray.png` 命中 → Click → 弹窗 → `confirm_group_pray.png` / `confirm_copper_pray_done.png` 命中 → Click
- 找不到铜币 → 跳到 15 人宝箱

### 子链路 2: 15 / 20 / 25 人宝箱
- 每个 box_N 有 3 状态(可领/已领/锁定),**独立状态机**
- `box_N_done.png` 命中(Noop) → 跳下一个 box
- `box_N_wait.png` 命中(Click) → 弹窗 → 关闭 → 跳下一个 box
- 找不到 wait → 跳过该 box

### 子链路 3: 追击晓组织
- "追击" 文字 OCR 命中 → Click → 进追击页
- `dawn_organization_award_undone.png` 命中 → Click → 检查 waiting 堆叠 → `one_key_dawn_organization_award.png` 用 **SwipeAction duration=30**

### 任务结束
- 全部子链路完成后 → 关闭所有弹窗 → 主页按钮兜底 → `verify_done`

---

## 5. 失败条件

- **找不到入口**: 主页 UI 改版 / 没加组织 → `verify_done` 短路
- **未加组织**: `group_list.png` 命中 → 任务 SKIP (用户没组织)
- **公告弹窗挡**: `notice_x.png` 命中 → Click
- **20 人红包关不掉**: narutomobile 6/18/6/20 两次都在 `close_second_group_award_box` 失败 — 这是**真实 bug**
- **追击晓入口不存在**: "追击" OCR 未命中 → 关闭弹窗兜底
- **游戏被切到后台**: P0 守护 → 任务 SKIP

---

## 6. 常见干扰项

| 干扰 | 描述 | 处理 |
|---|---|---|
| **公告弹窗** | 进入组织后顶部有公告 | `notice_x.png` 关 |
| **"前往"按钮文字可能变** | 版本更新可能改"前往"为"进入"等 | OCR 兜底已配置 |
| **20 人红包弹窗** | 领取 20 人宝箱后弹红包 | `group_pray_red_packet_text.png` 重定向点击弹窗 X |
| **25 人宝箱无弹窗** | 25 人宝箱领取后**直接关闭**(不像 20 人) | `close_third_box_popup` 用 `yesterday_award_done.png` |
| **追击晓入口可能未开放** | 等级/资格限制 | OCR "追击" 未命中 → 关闭兜底 |
| **一键领取是滑动条不是按钮** | narutomobile `one_key_dawn_organization_award.png` 是 **Swipe 不是 Click** | `SwipeAction(x1=454, y1=429, x2=454, y2=429, duration_ms=30)` |
| **昨日奖励有红点变色** | 活动期间红点颜色变化 | `green_mask: true` 避开红点 |

---

## 7. 当前项目实现

**Pipeline**: 28 节点(完整 4 子链路)

### 主链路骨架

```
ensure_home → find_ninja_guide → check_no_group → find_group_entry
  → close_group_notice → click_go_to_signin [OCR 前往]
  → [子链路 4 昨日奖励] → [子链路 1 铜币签到]
  → [子链路 2 15/20/25 宝箱] → [子链路 3 追击晓]
  → close_through_pages → back_to_home → verify_done
```

### 4 子链路展开

**子链路 4 昨日奖励** (4 节点):
- `check_yesterday_present` (Noop, `green_mask`) → `try_yesterday_award` (Click) → `check_yesterday_gettable` (Click) → `close_yesterday_popup` (Click)

**子链路 1 铜币签到** (2 节点):
- `try_copper_pray` (Click) → `confirm_copper_pray` (Click)

**子链路 2 15/20/25 宝箱** (9 节点, 含 20 人红包特殊处理):
- `check_first_box_done` (Noop) → `try_first_box` (Click) → `close_first_box_popup`
- `check_second_box_done` → `try_second_box` → `check_red_packet_present` → `close_second_box_popup`
- `check_third_box_done` → `try_third_box` → `close_third_box_popup`

**子链路 3 追击晓** (3 节点):
- `try_pursuit_entry` (OCRAction) → `check_dawn_award_undone` (Click) → `try_dawn_swipe_one_key` (**SwipeAction**)

### 入口与短路

- `check_no_group`: 用 `group/group_list.png` 判定未加组织 → 直接 `verify_done`

### 代码位置

- `tasks/group_signin_task.py`
- 类: `GroupSigninTask`

### 模板与 OCR 接入

- `click_go_to_signin` 节点: `ocr_expected=["前往"]` + 模板 fallback
- `try_pursuit_entry` 节点: `ocr_expected=["追击"]` + 模板 fallback
- `try_yesterday_award` 等: `green_mask=True` (避开红点)

---

## 8. 参考项目实现(narutomobile)

**Pipeline**: `Group.json` (730 行, **30+ 节点**)

**核心节点链**:
```
group (entry)
  → ninja_guide_returning_player
  → ninja_guide_in_ninja_guide
  → [JumpBack] open_ninja_guide (custom action)
  → [JumpBack] back_main_screen_before_task
  → goto_group_by_guide (custom_recognition + custom_action)
  → group_gameplay_undone (Noop or Click)
  → check_selected_group_gameplay (Noop)
  → OCR "前往" → group_pray (Click)
  → above_kage_group_pray (Click)
  → copper_group_pray (Click)
  → confirm_copper_group_pray (Click)
  → first/second/third_group_award (状态机)
  → yesterday_award_entry (green_mask)
  → group_pray_to_pursuit_dawn_organization (OCR "追击")
  → pursuit_dawn_organization_award
  → swipe_for_pursuit_dawn_organization_award
```

**narutomobile 6/18 实跑结果** (从 `log-20260618.log`):
- 22:30:30 进入组织任务 ✓
- 22:30:35 组织玩法未完成 ✓
- 22:30:36 确认选中 ✓
- 22:30:36 进入组织签到 (OCR "前往" 命中) ✓
- 22:30:41 铜币签到 ✓
- 22:30:56 close_second_group_award_box ❌ (20 人红包关弹窗失败)

**关键自定义 action**:
- `IsInNinjaGuide`: 自定义识别, 判定是否在忍界指引页内
- `GoIntoEntryByGuide(entry_name="组织")`: 自定义动作, 按文本点入口

**关键设计**:
- 用 `[JumpBack]` 失败回退到原 next 链
- 多个 done 状态都 `next: 下一个 box_done` 形成状态机链
- `inverse: true` 校验"没看到 undone 图"(已领取)

---

## 9. 已知问题与 TODO

### P0 已修复
- ✅ green_mask: `Node.green_mask` + `_match_green_channel()`
- ✅ OCR "前往" / "追击": `OCRAction` + `Node.ocr_expected`
- ✅ pre_flight: ensure_game_in_foreground()
- ✅ 未加组织短路: `check_no_group`
- ✅ 4 子链路全部实现(28 节点)

### P1 真机待验证(ROI 漂移)
- ⚠️ **入口 ROI 完全失效** — 用户当前主页无"忍界指引"
- ⚠️ `group/group_list.png` 实际是排行榜图(命名错)
- ⚠️ `group/copper_pray.png` 实际是铜币图标(不是按钮)
- ⚠️ `group/group_gameplay_undone.png` 实际是橙色分隔条(不是按钮)
- ⚠️ `shared/ninja_guide_v3.png` 实际是场景背景图

### P1 改进(强烈建议)
- [ ] **重新设计入口路径** — 用户当前游戏从奖励中心 → 组织 tab, 不是从忍界指引
- [ ] **重新采集模板** — 用 6/18 22:30:56 截图(真实组织祈福页)做对照重新截图
- [ ] **close_second_group_award_box 增强** — narutomobile 2 次失败, 改用 target_offset 重定向点击弹窗外

### P2 改进
- [ ] 区分超影签到和铜币签到(可选触发)
- [ ] 25 人宝箱确认无弹窗逻辑独立测试
- [ ] "前往追击晓组织"文字位置如果变了,OCR 需要重新校准 ROI

---

## 10. 开发规则

### 必须遵循

1. **4 子链路必须独立、可单独测试** — 不要混在主流程里
2. **每个 box_N 都有独立状态机** — `check_box_N_done` (Noop) + `try_box_N` (Click)
3. **OCR 文字位置变化概率低** — 比模板稳定, 但 ROI 仍需校准
4. **滑动条用 SwipeAction 不是 ClickAction** — narutomobile `one_key_dawn_organization_award.png` 是滑动条
5. **红点图标用 green_mask** — `yesterday_award.png` 必须加 `green_mask=True`
6. **"未加组织"是合理 SKIP 状态** — 用 `group_list.png` 判定, **不要**让任务因为没组织而 fail

### 禁止

- ❌ 把"前往"按钮当模板固定(必须 OCR 兜底)
- ❌ 在 box_N_done 节点上做 Click 操作(应该是 Noop)
- ❌ 把 4 个宝箱的判断逻辑合并(丢失独立状态信息)
- ❌ 用 BACK 键关闭任何弹窗

### 测试

- 验证脚本: `dryrun_group_signin.py` / `dryrun_v3.py`
- 检查点: (a) 未加组织短路正确 (b) 4 子链路按序执行 (c) OCR "前往""追击"命中 (d) SwipeAction duration 正确
- 历史教训: narutomobile 6/25 close_qq_app 把游戏切后台 → 必须确保游戏在前台(`pre_flight`)

---

## 附: 相关文件路径

- **代码**: `tasks/group_signin_task.py`
- **模板**: `resources/templates/actions/group/` (43 张)
- **manifest**: `resources/templates/template_manifest.json` (task=group 部分)
- **真机截图**: `screenshots/dryrun_v2/00_with_rois.png` (当前用户主页)
- **参考截图**: `D:/自动日常源码带/运行日志/log_20260625_204044_extracted/debug/on_error/2026.06.18-22.30.56.728_close_second_group_award_box.png` (narutomobile 6/18 实跑组织祈福页)
- **参考**: narutomobile `assets/resource/base/pipeline/Group.json` (730 行)
- **运行日志**: `D:/自动日常源码带/运行日志/log_20260625_204044_extracted/logs/log-20260618.log` (组织任务成功案例)