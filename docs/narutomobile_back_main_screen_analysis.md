# narutomobile back_main_screen 机制深度分析

> 来源: `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\resource\base\pipeline\merged.json`
> 分析者: Mavis 2026-07-01
> 关键发现: **main_green_masked.png 模板匹配从来就没真正成功过,但任务能完成**

## 1. 核心谜题

`main_green_masked.png`(1263×716 的"主页绿色掩码"合成图,96.5% 纯绿)在所有测试中匹配分数 = 0(包括用户 narutomobile 2026-06-30 debug 截图,已经实测 SQDIFF_NORMED min=1.0000,similarity=0)。

但用户日常用 narutomobile 跑日常任务全部能完成。**机制是什么?**

## 2. back_main_screen 完整节点链

```json
{
  "recognition": "TemplateMatch",
  "template": ["Startup/main_green_masked.png"],
  "method": 10001,
  "inverse": true,                  ← 关键
  "threshold": 0.9,
  "action": "DoNothing",
  "green_mask": true,
  "next": [
    "[JumpBack]leave_the_team",     ← OCR
    "[JumpBack]check_has_x",        ← Or 复合
    "[JumpBack]close_notice",       ← TemplateMatch notice_x
    "check_main_screen",            ← TemplateMatch main_green_masked
    "[JumpBack]weekly_sign",        ← TemplateMatch weekly_sign
    "[JumpBack]close_chat",         ← TemplateMatch chat_close
    "[JumpBack]close_friend_rank",  ← TemplateMatch friend_rank
    "[JumpBack]direct_hit_quit",    ← OCR "点击"
    "[JumpBack]naruto_club_x",      ← TemplateMatch close_club
    "[JumpBack]text_notice",        ← Or 复合
    "[JumpBack]group_notice",       ← Or 复合
    "[JumpBack]im_come_back",       ← OCR "我回来了"
    "[JumpBack]im_come_back_award", ← OCR "领取礼物"
    "[JumpBack]christmas_stocking", ← TemplateMatch christmas_stocking
    "[JumpBack]level_up",           ← OCR "等级达到"
    "[JumpBack]shut_social_media"   ← StopApp
  ],
  "timeout": 5000,
  "on_error": ["retry_failed"]
}
```

**17 个 next 节点**+ retry_failed 兜底。

## 3. inverse=true 的真正含义

MaaFramework 的 `inverse: true` **不是"反转匹配结果"**,而是 **"反转 next/on_error 语义"**:
- 普通节点: 匹配成功 → 走 next; 失败 → 走 on_error
- **inverse 节点: 匹配失败 → 走 next; 成功 → 走 on_error**

所以 `back_main_screen` 的真实语义:
- 模板匹配 **失败**(不在主页) → 走 next → 尝试各种 close 操作
- 模板匹配 **成功**(在主页) → 走 on_error → retry_failed → StopTask

**因为模板永远匹配不上,所以 back_main_screen 永远走 next,永远尝试 close 操作**。

## 4. 17 个 next 节点的真实作用

| 节点 | recognition | 作用 | 健壮性 |
|------|------------|------|--------|
| `leave_the_team` | OCR "离开队伍" | 离开组队界面 | ⭐⭐⭐ OCR 不依赖模板 |
| `close_notice` | TplMatch notice_x | 关闭公告弹窗 X | ⭐⭐ 局部 ROI 模板 |
| `weekly_sign` | TplMatch weekly_sign | 点周签到 | ⭐⭐ |
| `close_chat` | TplMatch chat_close | 关闭聊天框 | ⭐⭐ |
| `close_friend_rank` | TplMatch friend_rank | 关闭好友排名 | ⭐⭐ |
| `direct_hit_quit` | OCR "点击" | 通用"点任意处退出" | ⭐⭐⭐ |
| `naruto_club_x` | TplMatch close_club | 关闭情报社 | ⭐⭐ |
| `im_come_back` | OCR "我回来了" | 回归弹窗 | ⭐⭐⭐ |
| `im_come_back_award` | OCR "领取礼物" | 领回归礼物 | ⭐⭐⭐ |
| `christmas_stocking` | TplMatch christmas_stocking | 圣诞活动关 | ⭐ |
| `level_up` | OCR "等级达到" | 升级提示关 | ⭐⭐⭐ |
| `shut_social_media` | **StopApp** | 杀 QQ/微信 | ⭐⭐⭐ |
| `check_has_x` / `text_notice` / `group_notice` | Or 复合 | 多个识别任一命中 | 取决于子节点 |
| `check_main_screen` | TplMatch main_green_masked | **永远不命中** | ❌ |

**关键洞察**:
- **OCR 节点 5 个** + **StopApp 1 个** = 6 个**不依赖模板**的健壮节点
- **TemplateMatch 节点 7 个** 大多是**局部 ROI 模板**(X 按钮、小图标),受 UI 漂移影响小
- **`check_main_screen` 是唯一用 main_green_masked 的"状态判定节点" — 它永远失败,但任务不靠它完成**

## 5. 任务"完成"的真正机制

```
每个 task 末尾 → back_main_screen (模板失败 → next 链)
  ↓
next 链: 17 个 close/OCR 节点挨个试
  ↓ 哪个节点的 recognition 命中 → 执行 click/stop_app 动作
  ↓ 不命中 → on_error → JumpBack 回到 back_main_screen 重试
  ↓
循环 max_hit(默认 ~5-10)次后
  ↓
retry_failed 兜底
  ↓
try_back_main_screen → back_main_screen_failed → StopTask
  ↓
任务结束,显示 SUCCESS(不管游戏实际在哪)
```

**任务"完成"不是"游戏回到了主页",而是"max_hit 用完被 force stop"**。

而 close 操作(OCR + 局部 ROI 模板)确实有效,因为:
- OCR 对文字 "离开队伍" / "点击" / "我回来了" 健壮
- 局部 ROI 模板(close_x, chat_close_button)针对**弹窗/聊天框的局部 UI**,不依赖主页全屏
- 各种弹窗的 X 按钮位置相对稳定(游戏厂商一般不动)

## 6. 为什么我们的 gen_11_tasks.py 任务"假完成"

**我们抄了什么**:
```python
pipe.add(Node(
    name="back_main_screen",
    templates=tpls("state/main_green_masked.png"),
    roi=(0, 0, 1920, 1080), threshold=0.7,
    green_mask=True, action=NoopAction(),
    next=["verify_done"], on_error=["verify_done"],
    max_hit=5,
))
```

**漏了什么**:
- ❌ 17 个 close 操作节点
- ❌ inverse=true 反转语义
- ❌ OCR 健壮节点(leave_the_team, direct_hit_quit, im_come_back, level_up)
- ❌ StopApp 兜底(shut_social_media)
- ❌ StopTask 兜底(check_main_screen_and_stop)

**导致**:
- 入口节点失败 → on_error → back_main_screen(也是 NoopAction + 直接 verify_done)
- back_main_screen 也失败 → on_error → verify_done → SUCCESS
- **整个过程游戏状态没做任何修正**,只是把任务"假完成"
- 下次 dryrun 从错误状态开始 → 又失败

## 7. 真正修复方向(不实现,只分析)

要让任务"真完成",必须补全 narutomobile 的 back_main_screen 完整机制:

| 必需节点 | 我们的状态 | 修复方案 |
|---------|-----------|---------|
| `back_main_screen` (inverse=true) | ❌ NoopAction | 改用 inverse 语义 + next 链 |
| OCR 节点 ×5 | ❌ 没生成 | 在 gen_11_tasks.py 加 OCR 节点(rapidocr) |
| TemplateMatch 局部节点 ×7 | ⚠️ 部分抄了 | 检查 ROI 是否对齐你游戏实际位置 |
| Or 复合节点 ×3 | ❌ | navigator 需要支持 Or/And 逻辑 |
| `shut_social_media` (StopApp) | ❌ | 加 StopApp action |
| `StopTask` 兜底 | ❌ | 改 verify_done 为 StopTask 语义 |

## 8. 元学习(Meta-lesson)

这个案例的核心教训:

**模板匹配 score = 0 不代表"系统不能用",可能代表"系统的核心不是模板匹配"**。

narutomobile 的精妙之处:
- 模板匹配只用作"状态触发器",即使模板坏了也不影响核心功能
- OCR + 局部 ROI + StopApp + StopTask 才是真正的健壮层
- "force stop" 是最高优先级的兜底,任何情况下任务都会结束

我们抄的时候把"模板匹配"当成了核心,实际上应该抄的是 **"健壮层"**。

---

**关联文件**:
- `D:\火影自动日常\tools\gen_11_tasks.py:85-93` — 我们抄的 back_main_screen
- `D:\火影自动日常\tasks\navigator.py:600-744` — 我们的模板匹配实现(不支持 inverse/Or/OCR 复合)
- `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\resource\base\pipeline\merged.json` — 完整 17 节点 next 链