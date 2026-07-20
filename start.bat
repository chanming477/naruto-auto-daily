@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "MFA=MFAAvalonia.exe"

if not exist "%MFA%" (
    echo [错误] MFAAvalonia.exe 未找到
    echo 请确认已正确解压发布包
    echo 下载地址: https://github.com/MaaXYZ/MaaFramework/releases
    pause
    exit /b 1
)

:: 检测 .NET Desktop Runtime 10.0
dotnet --list-runtimes 2>nul | findstr /C:"Microsoft.NETCore.App 10." >nul
if %errorlevel% neq 0 (
    echo [提示] 未检测到 .NET 10 Desktop Runtime
    echo 正在运行依赖安装脚本（需要管理员权限 + 联网）...
    echo.
    call "DependencySetup_依赖库安装_win.bat"
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        echo 请手动安装 .NET 10 Desktop Runtime:
        echo   https://dotnet.microsoft.com/download/dotnet/10.0
        pause
        exit /b 1
    )
)

echo 正在启动 Naruto Auto Daily...
start "" "%MFA%"
exit /b 0
