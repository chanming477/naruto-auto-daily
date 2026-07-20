# 使用说明

## 下载

前往 [Releases](https://github.com/chanming477/naruto-auto-daily/releases) 下载最新版本。

## 安装

1. 解压下载的 zip 到任意目录（**不要**放在 `C:\Program Files\` 等需要管理员权限的目录）
2. 双击 `start.bat` 启动 MFAAvalonia GUI
3. 首次启动会自动初始化 Python 运行环境（如果失败，参考 [faq.md](faq.md)）

## 配置

1. 打开 `config/instances/default.json`
2. 设置 `AdbDevice`:
   - `AdbPath`: MuMu 模拟器自带的 adb.exe 路径
   - `AdbSerial`: 一般是 `127.0.0.1:16384` (MuMu 12 默认端口)
3. 勾选需要自动执行的任务
4. 保存

## 使用

1. 启动 MuMu 模拟器并打开火影手游
2. 启动 MFAAvalonia.exe
3. 点击"一键执行"或单独选择任务运行

## 常见问题

见 [faq.md](faq.md)。
