# naruto-auto-daily

> 火影忍者手游日常任务全自动执行工具 — 基于 MaaFramework 前端 + narutomobile 参考实现

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)](https://www.gnu.org/licenses/agpl-3.0.html)
[![GUI](https://img.shields.io/badge/GUI-MFAAvalonia-purple)](https://github.com/MaaXYZ/MaaFramework)

---

## 快速开始

在 [Releases](https://github.com/naruto-auto-daily/naruto-auto-daily/releases) 页面下载最新版本。

**模拟器设置**：分辨率调整为 **1920×1080（平板）**，锁定屏幕旋转为**横屏**以达到最佳运行效果。

**启动方式**：

| 方式 | 说明 |
|------|------|
| GUI 启动（推荐） | 双击 `start.bat`，勾选任务后点击「开始」 |
| CLI 启动 | `python main.py --help` |
| CLI 自检 | `python main.py --check` |

---

## 主要功能

### 日常

- 启动游戏
- 每日签到（月签到 + 拉面）
- 每日招财
- 排行榜点赞
- 送体力（赠送 + 领取）
- 每日分享
- 组织祈福
- 积分赛 *（已知限制，见下方说明）*
- 任务集会所
- 生存挑战
- 小队突袭
- 免费招募
- 刷体力（精英副本）
- 丰饶之间
- 活跃宝箱领奖
- 邮箱领奖
- 情报社
- 忍法帖
- 日志清理

### 战斗类

- 冒险模式推关
- 精英副本推关
- 刷周胜
- 秘境探险 *（已知限制，见下方说明）*
- 组织要塞
- 叛忍追击

### 功能类

- 日志清理
- 关闭火影

> 完整任务列表见 `frontend/MFAAvalonia/config/instances/default.json`。

### 已知限制

- `point_race`（积分赛）/ `secret_realm`（秘境）：忍者指引导航已修复，但业务层模板匹配仍在排查，如果无法正常完成请检查日志是否存在 `recognition failed`。

---

## 架构

```
┌──────────────────────────────────────────────┐
│         UI 层 — MFAAvalonia 桌面 GUI          │
│     双击 start.bat 启动，勾选任务一键执行        │
└─────────────────────┬────────────────────────┘
                      │ MaaFramework C# binding
                      ▼
┌──────────────────────────────────────────────┐
│      资源层 — MaaFramework pipeline           │
│  merged.json（1554 节点）+ 786 张 PNG 模板     │
│  + OCR 模型（DBNet + CRNN）                   │
└─────────────────────┬────────────────────────┘
                      │ Python maafw_bridge
                      ▼
┌──────────────────────────────────────────────┐
│       后端层 — Python CLI + 自定义 Agent       │
│   6 自定义 Action + 3 自定义 Recognition       │
│   OpenCV 模板匹配（TM_CCOEFF_NORMED）+ ADB      │
└─────────────────────┬────────────────────────┘
                      │ ADB
                      ▼
┌──────────────────────────────────────────────┐
│            MuMu 12 模拟器                      │
│          1920×1080 横屏                        │
└──────────────────────────────────────────────┘
```

---

## 常见问题

**Q: 任务执行后显示成功但实际没做？**
A: 请检查日志。可能是模板匹配阈值不足或 ninja guide 导航失败，可尝试重新截图生成模板。

**Q: 资源加载失败？**
A: 确保 `resources/narutomobile/pipeline/` 目录下**只有** `merged.json` 一个文件。MaaFramework 会加载该目录下所有 JSON 文件，多余文件会导致 key 冲突。

**Q: Agent 注册失败 "No module named 'agent.custom.sink'"？**
A: 确保本项目根目录 `agent/` 下的四个文件为最新版本：`custom/sink.py`、`custom/reco.py`、`custom/action.py`、`main.py`。

---

## 鸣谢

本项目由 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 强力驱动！

前端使用 [MFAAvalonia](https://github.com/MaaXYZ/MaaFramework)（MaaFramework 官方 Avalonia 桌面客户端）。

项目在开发过程中参考了 [narutomobile](https://github.com/MaaXYZ/narutomobile) 的代码与设计。

---

## 如何参与开发

请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

本项目使用 **AGPL-3.0** 开源协议，详见 [LICENSE](./LICENSE)。

联系作者：<chanshiming@foxmail.com>

---

**Built with ❤️ by naruto-auto-daily contributors · 2026**
