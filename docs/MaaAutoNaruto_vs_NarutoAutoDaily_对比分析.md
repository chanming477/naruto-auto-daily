# MaaAutoNaruto v1.3.35 vs 本项目 — 深度对比分析

> 用户提供 (2026-07-01) — 来源未注明(可能是 Mavis 之前的输出 / 用户自己整理 / 其他 agent 总结)
> 配套阅读: `narutomobile_back_main_screen_analysis.md` (本次会话产出,讲宏观机制)

## 一、架构差异

| 维度 | MaaAutoNaruto v1.3.35 | 本项目 (Naruto Auto Daily) |
|------|----------------------|---------------------------|
| 引擎 | MaaFramework C++ 原生引擎（MFAAvalonia.exe） | 纯 Python Navigator 自研引擎 |
| GUI | C# WPF 桌面应用（任务勾选、日志、调试） | PySide6 桌面应用（Phase 5） |
| Agent | Python 轻量 Agent（仅自定义动作/识别，约 500 行） | Python 全栈（从截图到点击全自己做） |
| Pipeline | JSON 声明式（merged.json 709KB，由引擎解析执行） | Python 代码式（_build_xxx_pipeline() 函数） |
| 识别 | 引擎内置 TemplateMatch + OCR + Color + Custom 并行 | 只有 TemplateMatch（OCR 定义了 OCRAction 但生成任务未使用） |
| 任务配置 | interface.json 141KB，36 个任务 + 80+ 选项 | task_registry.yaml 9 个任务，无选项系统 |

**核心差异一句话：MaaAutoNaruto 是"引擎 + 配置 + 模板"，本项目是"全部自己写"。**

## 二、为什么他能正常完成任务

### 原因 1：786 张模板，全部来自真机实采

MaaAutoNaruto 的 786 张模板不是一次性生成的。它们是社区用户在几百台不同设备、不同分辨率、不同主题下反复采集、验证、替换的产物。每张模板背后有至少几十次真机验证的置信度数据。

本项目 143 张模板大部分直接从 narutomobile 复制过来的——它们是针对别人设备采集的。ROI 相同不代表模板内容能匹配你设备上的实际像素。

### 原因 2：C++ 引擎做了 Python 没做的事

MaaFramework 引擎在每个 pipeline 节点执行时做 4 件事，本项目 Navigator 只做了前 2 件：

| 步骤 | MaaFramework (C++) | 本项目 (Navigator Python) |
|------|---------------------|---------------------------|
| ① 截图 | ✅ screencap -p | ✅ 相同 |
| ② 识别 | ✅ TemplateMatch + OCR + Color + Custom 同时跑，取置信度最高的 | ✅ 只有 TemplateMatch（OCR 仅在 OCRAction 中，未在生成任务中使用） |
| ③ 验证截图 | ✅ 动作后等 200ms → 再截一张 → 比较前后差异 → 确认画面变化 | ❌ 没有。post_delay_ms 是盲等固定值 |
| ④ 冻结检测 | ✅ 连续 3 帧完全相同 → 判定游戏卡死 → 触发恢复 | ❌ 没有 |

### 原因 3：识别方法组合，而非单一模板

看一个 narutomobile pipeline 节点：

```json
{
  "recognition": "TemplateMatch",
  "template": ["SharedNode/check_in_daily_award.png", "SharedNode/check_not_in_daily_award.png"],
  "roi": [37, 172, 130, 47],
  "threshold": 0.7,
  "next": ["group_gameplay_undone", "back_main_screen"]
}
```

**关键点**：
- 一个节点有 2 张模板取最高 conf（已签到 / 未签到都算"我在奖励中心"）
- threshold: 0.7（比我们的 0.55 保守，但模板质量高所以能达到）
- ROI 精确（[37, 172, 130, 47]——不是大区域搜索，是像素级裁剪）

本项目一个节点通常只有 1-2 张模板，threshold 降到 0.55 还是匹不上。

### 原因 4：用户反馈驱动模板迭代

MaaAutoNaruto 有 GitHub Issues、用户群、使用日志。模板不匹配 → 用户报告 → 开发者补采 → 下一版修复。这是运作了一年多的反馈闭环。本项目没有这个闭环——模板不匹配只能靠自己发现。

## 三、本项目缺失的关键能力

### 缺失 1：动作后验证（最关键的稳定性差异）

MaaFramework 在每个 tap/swipe 后会再截一张图，比较动作前后的画面差异。如果没有变化 → 判定点击无效（可能点到了空白区域或坐标偏移）→ 重试或走 on_error。

本项目 Navigator._execute_node() 的流程是：截图 → 匹配 → 点击 → 盲等 post_delay_ms → 进入下一个节点。从不验证点击是否生效。

**这是"为什么他能完成任务，本项目不行"的最直接原因**。点击偏了 10 像素 → 没点到按钮 → 画面没变化 → 下一个节点的模板匹配必然失败 → pipeline 报"识别失败"。但实际错误是上一步的点击，不是这一步的识别。

### 缺失 2：并行识别方法

MaaFramework 的一个节点可以同时跑 TemplateMatch + OCR + Color 三种识别，取最高置信度。本项目只能跑 TemplateMatch。对于"前往"按钮、"领取"按钮这种文字型 UI，OCR 比模板匹配鲁棒得多——文字不受皮肤、背景、红点影响。

### 缺失 3：游戏冻结/卡死检测

MaaFramework 检测连续 3 帧完全相同的截图 → 判定游戏卡死 → 自动触发 restart_game。本项目如果游戏卡死在加载画面，wait_loading 会一直轮询直到超时（默认 60 秒），中间完全不会截帧比较。

### 缺失 4：选项系统

MaaAutoNaruto 的 interface.json 有 80+ 个用户选项（如"秘境翻牌策略"、"是否用金币招财"、"轻松助手扫荡开关"）。这些选项在运行时注入到 pipeline 节点中，改变模板路径、阈值、next 分支。

本项目没有任何选项系统。所有任务行为硬编码在 _build_xxx_pipeline() 中。

## 四、本项目做得更好的地方

### 优势 1：Python pipeline 可调试

MaaAutoNaruto 的 pipeline JSON 调试极其困难——出错了只能看日志里的节点名称，无法打断点、无法单步执行。

本项目的 Navigator._execute_node() 是纯 Python 函数，可以 pdb 断点、可以单步跟踪、可以在日志里加任意结构化信息。

### 优势 2：RecoveryManager + RetryManager 分层恢复

MaaAutoNaruto 的恢复逻辑分散在 pipeline JSON 的 on_error 链中（例如所有节点 on_error 都指向 back_main_screen），没有统一的恢复管理器。

本项目有 RecoveryManager（4 场景统一恢复）+ RetryManager（指数退避重试）+ make_recovery_chain。只是这些组件还没有在真机上验证过。

### 优势 3：GameStateMachine 页面认知

MaaAutoNaruto 没有"我在哪个页面"的显式状态——它完全依赖 pipeline 节点的识别/不识别来决定跳转。

本项目有 GameStateMachine + PageRecognizer 显式维护页面状态。只是 Navigator 没有利用它——两条线平行运行。

### 优势 4：全套单元测试

MaaAutoNaruto 没有测试。本项目有 375 个通过的测试。虽然都是 mock 测试，但至少 pipeline 结构、异常路径、配置加载是被验证过的。

## 五、值得学习的 5 个关键点

### 学习点 1：动作后必须验证

这是最高优先级的改进。在 Navigator._do_action_with_result() 中，tap/swipe 执行后 sleep 200ms → 再截一张图 → 比较两帧差异。如果差异 < 阈值（画面没变），判定点击无效，重试或走 on_error。

实现成本：在 _execute_node() 中加 ~15 行代码。收益：消除"上一步点击偏移 → 下一步识别失败"的错误链。

### 学习点 2：多识别方法并行

一个节点不应只依赖一种识别方法。narutomobile 的做法是 TemplateMatch + OCR + Color 同时跑，取最高置信度。本项目已经有 OCRAction 类，只需要让 Node 支持 ocr_templates 字段，在识别阶段并行调用。

实现成本：在 Node 加 ocr_patterns: list[str] 字段，在 _execute_node() 识别阶段如果 OCR 命中则优先使用。收益：文字型按钮（"前往"/"领取"/"确认"）不受皮肤影响。

### 学习点 3：保守的阈值 + 精确的 ROI

narutomobile 的默认阈值是 0.7（比我们的 0.55 高），但能通过是因为模板质量高 + ROI 精确。模板和 ROI 是迭代出来的，不是一次性设定的。

本项目应该把 threshold 调回 0.7，然后把不通过的模板逐个补采——而不是降到 0.55 来妥协。

正确做法：以 narutomobile 的 ROI 为参考，在用户设备上重新采集每一张关键模板。阶段 2 的真机回归本质上就是在做这件事。

### 学习点 4：pipeline 节点要有"已完成"的正面识别

narutomobile 每个子流程的终点节点都有正面验证——例如 monthly_sign_done.png 确认签到已完成。本项目所有任务的 verify_done 都是 Noop。

正确做法：每个任务的最后一个节点应该匹配一个"已完成"标志（如签到后的勾、领取后的灰色按钮）。

## 六、差距总结

| 差距 | 严重度 | 修复成本 | 修复后收益 |
|------|--------|---------|-----------|
| 动作后无验证 | 🔴 致命 | 低（~15 行代码） | 消除最大稳定性故障源 |
| 无并行识别（OCR+模板） | 🟡 重要 | 中（改 Node + Navigator） | 文字按钮匹配率大幅提升 |
| 模板来自参考项目非真机 | 🔴 致命 | 高（逐张补采） | 真机能跑的前提 |
| 无游戏冻结检测 | 🟡 重要 | 低（~20 行代码） | 长时间运行不卡死 |
| 无用户选项系统 | 🟢 改善 | 高（需新模块） | 灵活性和可维护性 |
| verify() 全是空实现 | 🟡 重要 | 低（加模板匹配） | SUCCESS 可信度 |
| 无反馈闭环 | 🟡 重要 | 非代码问题 | 模板持续改进 |

**结论：MaaAutoNaruto 能正常完成任务不是因为架构更"先进"——我们的 Python Navigator + RecoveryManager 架构在灵活性上甚至更优。它之所以能跑，是因为 786 张真机验证过的模板 + 动作后验证 + 一年多的用户反馈迭代。这三个要素本项目一个都没有——这就是差距的根源。**

---

## 七、与本次会话 back_main_screen 分析的合并视角

把这两份分析合起来看，narutomobile 能跑通的完整机制是**5 层健壮性**:

| 层 | 内容 | 本项目状态 |
|----|------|-----------|
| 1. 模板匹配层 | main_green_masked.png 等(脆弱,模板已过时) | ❌ 抄了但匹配不上 |
| 2. OCR 健壮层 | 5 个 OCR 节点(离开队伍/点击/我回来了/领取礼物/等级达到) | ❌ 没集成到 task pipeline |
| 3. 局部 ROI 模板层 | 弹窗 X / 聊天关闭等局部 UI | ⚠️ 部分有,但 ROI 未对齐 |
| 4. StopApp / StopTask 层 | 杀外部 app + 强制结束任务 | ❌ 没有 |
| 5. **动作后验证**层 | tap 后再截图对比,确认画面变化 | ❌ 没有 |

**第 5 层(动作后验证)是用户这份分析强调的最高优先级修复点**——它能在"上一步点击偏移"时立刻发现,而不是等下一步识别失败才暴露。

如果我们只能改一个地方,**改第 5 层** — 它能让所有 pipeline 的稳定性提升一档,且实现成本极低(~15 行)。

如果改两个,**第 5 层 + 第 2 层(OCR 集成)** — 让所有文字型按钮变成 OCR 优先,皮肤/红点不再影响识别。