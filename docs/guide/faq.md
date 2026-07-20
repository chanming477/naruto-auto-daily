# 常见问题

## 启动类

### MFAAvalonia.exe 打不开
- 确认已安装 .NET 10 Desktop Runtime
- 如果 Windows Defender 拦截，请点"更多信息" → "仍要运行"
- 检查 `get_cli.bat` 是否执行过（复制 .NET native DLL）

### 提示缺少 Python
- 发布包自带 Python 运行时，无需单独安装
- 如果仍然报错，请重新下载最新发布包

### 启动后 agent 立即退出
- 检查 `debug/custom/` 下的日志
- 确认没有 `UnicodeEncodeError`（已通过 `sys.stdout.reconfigure(encoding='utf-8')` 修复）
- 确认 maa 模块能正常 import

## 模拟器类

### 无法连接模拟器
- 确认模拟器已开启 ADB 调试
- 确认 `default.json` 中 `AdbDevice.AdbPath` 配置正确
- 确认 `AdbDevice.AdbSerial` 是 `127.0.0.1:<port>` 格式

### 任务无法启动 / 立即停止
- `AspectRatioChecker` 启用了 16:9 分辨率检查
- 确认模拟器分辨率设为 1920×1080（平板模式）或 1280×720
- 确认屏幕旋转锁定为横屏

### 识别失败 / 任务中途停止
- 检查 `resources/narutomobile/image/` 是否完整（870 张图）
- 确认游戏 UI 没有改版（活动期间 UI 变化是常态）
- 查看 `debug/custom/YYYY-MM-DD.log` 找具体失败节点

## 任务类

### 秘境 / 送体力 / 每日分享跑挂
- **秘境**: 开启 `从奖励中心进入` option（推荐）或保持默认走忍者指南
- **送体力** (give_energy): 如果你的好友只有 QQ/微信好友，开启 `选择账号后好友送体力` option
- **每日分享** (share): 开启 `主页能否跳过每日分享` 可关闭

### 任务完成后想看 log
- 任务 log: `debug/custom/YYYY-MM-DD.log` (每日轮转，2 周后自动清理)
- 截图: `debug/screenshot/` (失败时自动保存)

## 反馈

- 提 Issue: [GitHub Issues](https://github.com/chanming477/naruto-auto-daily/issues)
