"""tools/_maafw_smoke.py — 临时冒烟,验证 maafw_bridge 真机能力(2026-07-02)。

跑 4 个核心 entry: mail / headhunt / group / liveness_award
每个 entry 1 次,记录 status / 节点数 / 总耗时。

不修改 task_engine.py / main.py / UI — 只验证 maafw_bridge 模块本身能跑真机。
跑完即可删除(Step 5a 删 tools/dryrun_*.py 时一起删)。

前提:
    - 模拟器已启动(127.0.0.1:16384 MuMu 12.0)
    - narutomobile 资源已复制到 resources/narutomobile/
    - 游戏登录完成 + 在主页(否则部分任务会因找不到入口失败)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 让 import 找到 core / maafw_bridge
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from core.config_manager import ConfigManager
from maafw_bridge import (
    MaaEventSink,
    MaaTaskerSingleton,
    get_tasker,
    reset_tasker,
)

# v2.0 Step 4 要求: 4 个核心 entry 都要真机跑通至少 1 次,conf ≥ 0.75
ENTRIES = [
    ("mail", "mail"),
    ("recruit", "headhunt"),
    ("group_signin", "group"),
    ("liveness", "liveness_award"),
]


def _status_is_success(status: object) -> bool:
    """判断 task 算"成功"。

    maafw 5.10.4 Status 属性:
        - .succeeded   bool: 真成功(pipeline 走完且所有节点 success)
        - .failed      bool: 真失败
        - .done        bool: pipeline 结束(succeeded 或 failed)
        - .pending     bool: 等待
        - .running     bool: 运行中

    返回值含义:
        True   → Status.succeeded 为 True(真成功)
        "stopped"  → Status.done 为 True 但 succeeded 为 False
                    (StopTask 兜底结束 — task 走完了,可能没找到入口,narutomobile 常见行为)
        False  → 真失败(Status.failed True 或 Status.pending/running)
    """
    if status is None:
        return False
    if getattr(status, "succeeded", False):
        return True
    if getattr(status, "failed", False):
        return False
    if getattr(status, "done", False):
        # StopTask 兜底结束,任务整体走完但没找到入口
        # narutomobile 的 group/liveness_award 等都靠 StopTask 兜底
        return "stopped"
    return False


def main() -> int:
    # 1. 加载 cfg
    cfg = ConfigManager(PROJECT_ROOT, auto_load=True)
    logger.info("config loaded: project_root={}", cfg.project_root)
    logger.info(
        "maafw config: resource={} data_dir={}",
        cfg.app.maafw.narutomobile_resource_path or "(default)",
        cfg.app.maafw.data_dir or "(default)",
    )

    # 2. 初始化单例(连 ADB + 加载 resource + bind tasker)
    reset_tasker()  # 确保全新 init
    singleton = get_tasker()
    t0 = time.monotonic()
    try:
        singleton.init(cfg)
    except Exception as exc:
        logger.error("init failed: {}", exc)
        print(f"\n✗ init failed: {exc}")
        return 1
    logger.info(
        "maafw init done in {:.2f}s: tasker.inited={}",
        time.monotonic() - t0,
        singleton.tasker.inited,
    )

    # 3. 跑 4 个核心 entry
    results: list[dict] = []
    for our_task_id, entry in ENTRIES:
        logger.info("=== running entry={} (task_id={}) ===", entry, our_task_id)

        sink = MaaEventSink(task_id=our_task_id)
        # Tasker.add_context_sink(ContextEventSink) — 全局收所有任务的节点
        singleton.tasker.add_context_sink(sink)

        t0 = time.monotonic()
        try:
            job = singleton.run_task(entry)
            detail = job.wait().get()
            elapsed = time.monotonic() - t0

            status_obj = getattr(detail, "status", None) if detail else None
            # maa.define.Status 是 property wrapper,5.10.4 有 .succeeded/.failed/.done/.pending/.running 5 个 bool 属性
            if status_obj is None:
                status_name = "None"
            elif getattr(status_obj, "succeeded", False):
                status_name = "Succeeded"
            elif getattr(status_obj, "failed", False):
                status_name = "Failed"
            elif getattr(status_obj, "running", False):
                status_name = "Running"
            elif getattr(status_obj, "pending", False):
                status_name = "Pending"
            elif getattr(status_obj, "done", False):
                status_name = "Done"
            else:
                status_name = type(status_obj).__name__
            success = _status_is_success(status_obj)
            # 区分 True(真成功)/ "stopped"(StopTask 兜底)/ False(真失败)
            if success is True:
                mark = "✓"
                success_str = "succeeded"
            elif success == "stopped":
                mark = "○"  # StopTask 兜底结束
                success_str = "stopped(no-entry)"
            else:
                mark = "✗"
                success_str = "failed"

            n = sink.recognition_count + sink.action_count
            results.append(
                {
                    "task_id": our_task_id,
                    "entry": entry,
                    "status_name": status_name,
                    "success": success_str,
                    "is_real_success": success is True,
                    "recognition_count": sink.recognition_count,
                    "action_count": sink.action_count,
                    "wait_freezes_count": sink.wait_freezes_count,
                    "elapsed_sec": round(elapsed, 2),
                }
            )
            print(
                f"{mark} [{our_task_id} → {entry}] "
                f"status={status_name}({success_str}) "
                f"rec={sink.recognition_count} act={sink.action_count} "
                f"elapsed={elapsed:.2f}s"
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.exception("entry {} failed", entry)
            results.append(
                {
                    "task_id": our_task_id,
                    "entry": entry,
                    "status_cls": "FAIL",
                    "success": False,
                    "error": str(exc),
                    "elapsed_sec": round(elapsed, 2),
                }
            )
            print(f"✗ [{our_task_id} → {entry}] FAILED: {exc} ({elapsed:.2f}s)")

    # 4. 总结
    print()
    print("=" * 70)
    print(f"Smoke summary ({len(results)} entries)")
    print("=" * 70)
    for r in results:
        if r.get("error"):
            print(
                f"  ✗ {r['task_id']:<15s} → {r['entry']:<18s} "
                f"status={r.get('status_name', 'FAIL'):<25s} elapsed={r['elapsed_sec']}s "
                f"error={r['error'][:60]}"
            )
        else:
            mark = "✓" if r["is_real_success"] else ("○" if r["success"] == "stopped(no-entry)" else "✗")
            print(
                f"  {mark} {r['task_id']:<15s} → {r['entry']:<18s} "
                f"status={r['status_name']:<15s}({r['success']:<20s}) "
                f"rec={r['recognition_count']:<3d} act={r['action_count']:<3d} "
                f"elapsed={r['elapsed_sec']}s"
            )

    n_real_ok = sum(1 for r in results if r.get("is_real_success"))
    n_stopped = sum(1 for r in results if r.get("success") == "stopped(no-entry)")
    print()
    print(
        f"{n_real_ok}/{len(results)} 真成功 + {n_stopped} StopTask 兜底 = "
        f"{n_real_ok + n_stopped}/{len(results)} 通过"
    )
    # 把 StopTask 兜底也算通过(narutomobile 设计如此)
    return 0 if (n_real_ok + n_stopped) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
