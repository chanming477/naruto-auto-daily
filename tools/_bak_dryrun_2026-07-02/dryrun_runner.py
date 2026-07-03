"""tools.dryrun_runner — 通用真机 dry-run 执行器。

设计:
    - 一个 runner 函数 run_task(task_id, max_iters, max_idle) 跑任意 task
    - 7 个 task 各自有 1 行 wrapper (dryrun_<task>.py)
    - 共享 ADBClient / Navigator / Pipeline 装配逻辑
    - 截图存盘 + history 打印 + log 文件记录

用法:
    python tools/dryrun.py mail
    python tools/dryrun.py weekly_signin --max-iters 60

也可以直接调库:
    from tools.dryrun_runner import run_task
    run_task("liveness", max_iters=80)
"""
from __future__ import annotations

import datetime
import pathlib
import sys
import time

PROJECT_ROOT = pathlib.Path(r"D:\火影自动日常")
sys.path.insert(0, str(PROJECT_ROOT))

ADB_PATH = r"D:\LenovoSoftstore\Install\Androws\Application\5.10.6500.6116\adb.exe"
# 2026-06-29 14:00 MuMu 12 端口变更:16384 -> 5555
SERIAL = "127.0.0.1:5555"

# 2026-06-30: 25 个 task_id(7 旧 + 7 战斗 + 11 新=narutomobile 全抄 v1.3.35 merged.json)
TASK_BUILDERS = {
    "mail":         ("tasks.mail_task",         "_build_mail_pipeline"),
    "daily_signin": ("tasks.daily_signin_task", "_build_daily_signin_pipeline"),
    "weekly_signin":("tasks.weekly_signin_task","_build_weekly_signin_pipeline"),
    "liveness":     ("tasks.liveness_task",     "_build_liveness_pipeline"),
    "recruit":      ("tasks.recruit_task",      "_build_recruit_pipeline"),
    "activity":     ("tasks.activity_task",     "_build_activity_pipeline"),
    "group_signin": ("tasks.group_signin_task", "_build_group_signin_pipeline"),
    "monthly_signin": ("tasks.monthly_signin_task", "_build_monthly_signin_pipeline"),
    # 战斗/活动类(2026-06-30 narutomobile 全抄)
    "rich_room":    ("tasks.rich_room_task",    "_build_rich_room_pipeline"),
    "team_dash":    ("tasks.team_dash_task",    "_build_team_dash_pipeline"),
    "secret_realm": ("tasks.secret_realm_task", "_build_secret_realm_pipeline"),
    "survival_challenge": ("tasks.survival_challenge_task", "_build_survival_challenge_pipeline"),
    "shugyou_no_michi": ("tasks.shugyou_no_michi_task", "_build_shugyou_pipeline"),
    "stronghold":   ("tasks.stronghold_task",   "_build_stronghold_pipeline"),
    "mission_office": ("tasks.mission_office_task", "_build_mission_office_pipeline"),
    # 11 个新(2026-06-30 新版 v1.3.35 抄)
    "advanture":          ("tasks.advanture_task",          "_build_advanture_pipeline"),
    "elite_instance":     ("tasks.elite_instance_task",     "_build_elite_instance_pipeline"),
    "point_race":         ("tasks.point_race_task",         "_build_point_race_pipeline"),
    "rebel_ninja":        ("tasks.rebel_ninja_task",        "_build_rebel_ninja_pipeline"),
    "use_energy":         ("tasks.use_energy_task",         "_build_use_energy_pipeline"),
    "give_energy":        ("tasks.give_energy_task",        "_build_give_energy_pipeline"),
    "leaderboard":        ("tasks.leaderboard_task",        "_build_leaderboard_pipeline"),
    "more_gameplay":      ("tasks.more_gameplay_task",      "_build_more_gameplay_pipeline"),
    "ninja_book":         ("tasks.ninja_book_task",         "_build_ninja_book_pipeline"),
    "weekly_win":         ("tasks.weekly_win_task",         "_build_weekly_win_pipeline"),
    "sky_ground":         ("tasks.sky_ground_task",         "_build_sky_ground_pipeline"),
    # 2 个追加(2026-06-30 21:45)
    "easy_helper":        ("tasks.easy_helper_task",        "_build_easy_helper_pipeline"),
    "hundred_ninja":      ("tasks.hundred_ninja_task",      "_build_hundred_ninja_pipeline"),
}


def run_task(task_id: str, max_iters: int = 80, max_idle: int = 5) -> int:
    """跑指定 task 的 pipeline 在真机上。

    Args:
        task_id: 任务 ID,必须在 TASK_BUILDERS 中。
        max_iters: 最大总迭代数(防卡死)。
        max_idle: 连续无进展最大次数(防漏判)。

    Returns:
        进程退出码:0=成功走到 verify_done, 1=失败, 2=task_id 无效, 3=抛异常。
    """
    if task_id not in TASK_BUILDERS:
        print(f"❌ 未知 task_id: {task_id}")
        print(f"   可用: {', '.join(TASK_BUILDERS.keys())}")
        return 2

    from loguru import logger
    LOGS_DIR = PROJECT_ROOT / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"dryrun_{task_id}_{stamp}.log"
    logger.add(str(log_file), encoding="utf-8", level="DEBUG")
    logger.info(f"=== 真机 dry-run 启动: task={task_id}, ADB={ADB_PATH}, SERIAL={SERIAL} ===")

    print("=" * 60)
    print(f"真机 dry-run: {task_id}")
    print("=" * 60)

    try:
        from device.adb_client import ADBClient
        from tasks.navigator import Navigator

        print("[1] 初始化 ADBClient...")
        adb = ADBClient(adb_path=ADB_PATH, serial=SERIAL)
        r = adb.connect()
        print(f"    connect: success={r.success} msg={r.message}")
        if not r.success:
            print("FAIL: ADB 连接失败")
            return 1

        print("[2] 截图一张检测分辨率...")
        import numpy as np
        shot = adb.screenshot()
        if not shot.success or not isinstance(shot.payload, np.ndarray):
            print("FAIL: 截图失败")
            return 1
        h, w = shot.payload.shape[:2]
        print(f"    截图 {w}x{h}")

        print("[3] 构造 Navigator...")
        nav = Navigator(adb_client=adb, project_root=PROJECT_ROOT)

        # 动态导入 task builder
        module_name, func_name = TASK_BUILDERS[task_id]
        import importlib
        mod = importlib.import_module(module_name)
        build_fn = getattr(mod, func_name)
        pipe = build_fn(nav)
        print(f"[4] pipeline 已构造: 节点数={len(pipe)}, entry={pipe.entry}")

        print()
        print("=" * 60)
        print("开始跑 pipeline...")
        print("=" * 60)

        start = time.time()
        result = nav.run(pipe, max_total_iterations=max_iters, max_idle_iterations=max_idle)
        elapsed = time.time() - start

        print()
        print("=" * 60)
        print("运行结果")
        print("=" * 60)
        print(f"success     : {result.success}")
        print(f"last_node   : {result.last_node}")
        print(f"total_iters : {result.total_iterations}")
        print(f"elapsed     : {elapsed:.1f}s")
        print(f"error       : {result.error}")
        print(f"history:")
        for h in result.history:
            print(f"    -> {h}")

        # 退出码
        return 0 if result.success else 1

    except Exception as e:
        logger.exception("dryrun 异常: {}", e)
        print(f"\n❌ 异常: {e}")
        return 3
    finally:
        print()
        print(f"log file: {log_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="真机 dry-run runner")
    parser.add_argument("task_id", help=f"任务 ID,可选: {', '.join(TASK_BUILDERS.keys())}")
    parser.add_argument("--max-iters", type=int, default=80, help="最大总迭代数")
    parser.add_argument("--max-idle", type=int, default=5, help="最大无进展次数")
    args = parser.parse_args()
    sys.exit(run_task(args.task_id, args.max_iters, args.max_idle))