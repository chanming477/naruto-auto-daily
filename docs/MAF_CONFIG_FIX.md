# MFAAvalonia interface.json option 块修复

**2026-07-14** · 关联: on_error 截图 `up_swipe_for_ninja_guide_find_funtion_entry` × 3 + `energy_entry` × 1

## 问题现象

跑批时 4 张 on_error 截图, 但任务报告 `任务已全部完成! (用时 0h 2m 0s)`。

### on_error 截图暴露的状态

| 截图 | 截图时游戏状态 | 任务预期状态 |
|---|---|---|
| `13.17.41.749_up_swipe_*.png` | 已在"组织争霸赛"tab(忍界指引页) | 期望找"组织"入口 |
| `13.18.25.237_energy_entry.png` | 已在好友页 | 期望找"赠送体力"入口 |
| `13.19.04.985_up_swipe_*.png` | 仍在"组织争霸赛"tab | 期望找"组织"入口 |
| `13.19.06.32_up_swipe_*.png` | 仍在"组织争霸赛"tab | 期望找"组织"入口 |

## 根因

对比 `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.41\interface.json` (141 KB) 与本项目 `frontend/MFAAvalonia/interface.json` (2.3 KB):

- **merged.json**: 完全相同 (708,915 字节, 模板/ROI/pipeline 全对得上)
- **image/ 模板**: 完全相同
- **`option` 块**: 本项目 `{}` 空, MaaAutoNaruto 138 KB 完整 ← **唯一区别**

`option` 块缺失意味着 `merged.json` 里 `ninja_guide_find_funtion_entry` 节点使用**默认 expected** `"装备"`, 但实际游戏 UI 当前位置是"组织争霸赛", **OCR 找不到"装备"** → 走 swipe 兜底 15 次 → `[JumpBack]back_main_screen` → 任务报"成功"。

## 修复

选择性复制 10 个相关 option 到 `frontend/MFAAvalonia/interface.json` 顶部 (AGPL-3.0 同许可证):

| Option | 覆盖的 task |
|---|---|
| 忍界指引寻找排行榜 | (通用, 给排行榜任务用) |
| 忍界指引寻找组织 | group_signin |
| 忍界指引寻找积分赛 | point_race |
| 忍界指引寻找任务集会所 | mission_office |
| 忍界指引寻找秘境 | secret_realm |
| 忍界指引寻找周胜 | weekly_win |
| 忍界指引寻找叛忍 | rebel_ninja |
| 忍界指引寻找要塞 | stronghold |
| 选择账号好友送体力 | give_energy |
| 从奖励中心进入 | (多任务: group/point_race/mission_office/weekly_win/secret_realm/...) |

**效果**: `ninja_guide_find_funtion_entry.expected` 从 `["装备"]` 动态覆盖为实际任务入口文字(如 `["组织"]` / `["积分赛"]` / `["秘境"]` 等), 加上 `roi: [120, 68, 98, 585]` 窄 ROI 聚焦左侧菜单 + 完整 `next` 链。

## 8 个 select option 强制开

前 8 个 `忍界指引寻找X` option 是 `type: select`, `cases: [{"name": "开", "pipeline_override": {...}}]` (cases 只有 1 个, 描述写"注意这个选项你没法选择") — **强制开启, 无需用户在 GUI 操作**。

## 2 个 switch option 需用户在 GUI 启用

- `选择账号好友送体力`: 给 give_energy 任务用"QQ/微信好友"而非"游戏好友"。默认 No, 需在 GUI 选项里手动切 Yes。
- `从奖励中心进入`: 走奖励中心入口(替代忍界指引), 适用于 group/point_race/mission_office/weekly_win/secret_realm/... 默认 No, 需在 GUI 选项里手动切 Yes。

## 文件位置

修复文件: `frontend/MFAAvalonia/interface.json` (从 2,375 字节 → 19,918 字节)

⚠️ **此文件在 `frontend/MFAAvalonia/` 目录下, .gitignore 已排除 (234 MB 二进制)。**

## 重新安装 MFAAvalonia 时要重新应用

如果用户从 MaaFramework releases 重新下载 MFAAvalonia 到 `frontend/MFAAvalonia/`, 新的 `interface.json` 又会回到 2.3 KB 状态(默认无 option 块)。**重新应用修复** 步骤:

1. 备份当前 `frontend/MFAAvalonia/interface.json`
2. 跑 `python D:\tmp\patch_interface.py`(脚本在本仓库外的 D:\tmp, 需先复制一份进 `tools/` 目录? 或重新执行本修复的逻辑)
3. 重启 MFAAvalonia

> **后续改进 (TODO)**: 把 `patch_interface.py` 移到 `tools/` 目录, 写进 README, 避免脚本散落。

## 验证方式

修复后跑批观察:
1. `debug/on_error/` 不再生成 `up_swipe_for_ninja_guide_find_funtion_entry` 截图
2. 任务日志中 `[Record] 进入组织任务` / `[Record] 进入积分赛任务` 等应该正常出现
3. 任务时长从 0h 2m 0s 略微变长(因为真的去做了, 不是 swipe 兜底)

## 关联文档

- 完整根因分析: `D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.41\interface.json` line 838-1145 (10 个相关 option)
- 项目 pipeline: `resources/narutomobile/pipeline/merged.json` line 20322-20460 (ninja_guide_* 节点定义)
- 项目 README: §6 架构图 (Background Layer)
- AGPL-3.0 同许可证合规: LICENSE + pyproject.toml license 字段
