"""agent — MFAAvalonia 子进程 (Agent 模式)。

启动方式:
    MFAAvalonia.exe 启动时读 ``interface.json`` 的 ``agent`` 块,自动 spawn:
        python -u agent/main.py <socket_id>

然后通过 MaaAgentServer/MaaAgentClient IPC 调 ``agent/custom/`` 下的 custom action/recognition。

Python 端只做 3 件事:
    1. 启动 AgentServer 接 socket
    2. 注册 custom action (NonlinearSwipe / GoIntoEntryByGuide) — 用装饰器
    3. 等 C# 调

不做的事:
    - 不连 ADB (C# side)
    - 不加载资源 (C# side)
    - 不跑 pipeline (C# side)
    - 不收集 task 结果 (C# side)

**Direct API 模式兼容** (2026-07-19 OPT-2 后):
    CLI 端 --run-task / --daily-all 已删,主入口是 MFAAvalonia 桌面 GUI 走 agent 模式。
    Direct API 模式保留 ``maafw_bridge.tasker.MaaTaskerSingleton`` 给 unit test / 调试用,
    跟 agent 模式共享 ``maafw_bridge._actions_core`` 核心逻辑(方案 A 抽出来的)。
"""
