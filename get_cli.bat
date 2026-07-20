@echo off
REM get_cli.bat — 复制 .NET native DLL 到 exe 同级目录
REM (移植自 MaaAutoNaruto v1.3.41, 解决部分 Windows 启动失败)
for /d %%a in (runtimes\*) do copy /y "%%a\native\*" .
