@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Naruto Auto Daily -- Python CLI 后端
echo 使用: start_cli.bat [参数]
echo 示例: start_cli.bat --mail-real
echo.
python main.py %*
pause
