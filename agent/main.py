"""agent.main — AgentServer 入口,MFAAvalonia 启动时 spawn。

用法:
    MFAAvalonia.exe 读 ``interface.json`` 的 ``agent.child_exec = "python/python.exe"``,
    ``agent.child_args = ["-u", "agent/main.py"]``,然后执行::
        python/python.exe -u agent/main.py <socket_id>

其中 ``<socket_id>`` 是 MFAAvalonia 生成的 socket 标识,Python 端用来跟 C# 通信。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_project_root() -> Path:
    """从 __file__ 往上找含 ``maafw_bridge/`` 的目录。

    2026-07-20 扁平化后, ``agent/`` 始终在项目根, dev 和部署都是 1 层:
        - 源码 dev: ``<project_root>/agent/main.py`` → parent = project root
        - MFAAvalonia 部署: ``<project_root>/agent/main.py``(扁平化前曾考虑过把
          agent/ 嵌进 MFAAvalonia 临时目录, 2026-07-20 d5e087e 后不会了)

    找不到时报错(让用户知道 agent/ 复制位置不对)。
    """
    current = Path(__file__).resolve().parent
    for _ in range(5):  # 最多 5 层
        if (current / "maafw_bridge").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(
        f"Cannot find project root with maafw_bridge/. "
        f"agent/main.py __file__={Path(__file__).resolve()}"
    )


# 必须在 import agent.custom.action 之前设置 sys.path(它要 import maafw_bridge)
_PROJECT_ROOT = _find_project_root()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    """Agent 入口 — 启动 AgentServer 等 MFAAvalonia IPC 调用。"""
    # 强制 stdout UTF-8 编码（防止 Windows charmap 编码错误）
    # 2026-07-20 加 — narutomobile 1.3.41 的做法
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    from agent.utils.logger import setup_agent_logger
    log = setup_agent_logger()

    log.info("=== agent starting, cwd={} project_root={} ===", Path.cwd(), _PROJECT_ROOT)

    try:
        from maa.agent.agent_server import AgentServer  # type: ignore
        from maa.toolkit import Toolkit  # type: ignore
    except ImportError as exc:
        log.error("maa 模块导入失败: {}", exc)
        return 1

    Toolkit.init_option("./")

    if len(sys.argv) < 2:
        log.error("缺少 socket_id 参数 (期望: agent/main.py <socket_id>)")
        return 1
    socket_id = sys.argv[-1]
    log.info("Agent 启动, socket_id={}", socket_id)

    try:
        import agent.custom.action  # noqa: F401
        import agent.custom.reco    # noqa: F401
        import agent.custom.sink    # noqa: F401
        log.info("Custom action / recognition / sink 注册完成")
    except ImportError as exc:
        log.error("Custom action / recognition 导入失败: {}", exc)
        return 1

    try:
        AgentServer.start_up(socket_id)
        log.info("AgentServer 启动成功")
    except Exception as exc:  # noqa: BLE001
        log.error("AgentServer.start_up 失败: {}", exc)
        return 1

    try:
        AgentServer.join()
    except KeyboardInterrupt:
        log.info("Agent 收到 SIGINT,准备关闭")
    finally:
        try:
            AgentServer.shut_down()
        except Exception as exc:  # noqa: BLE001
            log.warning("AgentServer.shut_down 抛异常: {}", exc)
        log.info("=== agent 已关闭 ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
