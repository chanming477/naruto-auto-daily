"""生成 template_manifest.json — 模板治理清单。

数据来源:
    - 文件扫描:resources/templates/actions/**.png (143 张)
    - 命名规则推断 task / page / purpose
    - narutomobile 知识 + 当前项目代码(ROI 注释)补充 version_sensitive / threshold

输出:
    resources/templates/template_manifest.json

执行方式:
    python scripts/generate_template_manifest.py
"""
from __future__ import annotations
import json, pathlib, datetime, hashlib

PROJECT_ROOT = pathlib.Path(r"D:\火影自动日常")
TEMPLATES_DIR = PROJECT_ROOT / "resources" / "templates" / "actions"
OUTPUT = PROJECT_ROOT / "resources" / "templates" / "template_manifest.json"


# ============================================================
# 命名规则 → (task, page, purpose, threshold) 推断表
# ============================================================

# 命名规则按优先级排序:第一个命中的文件名匹配规则生效
# (没命中 → 用子目录默认值)

# 文件名包含某些关键字 → 推断 purpose + threshold
NAME_RULES = [
    # mail/
    ("mail_envelope",       "mail", "home", "entry", 0.55, True),
    ("mail_wait",           "mail", "mail_page", "entry", 0.55, True),
    ("mail_done",           "mail", "mail_page", "done_state", 0.55, False),
    ("lingqi",              "mail", "mail_page", "entry_alt", 0.55, True),
    # liveness/
    ("weekly_award_undone", "liveness", "award_center", "entry", 0.55, True),
    ("weekly_award_done",   "liveness", "award_center", "done_state", 0.55, False),
    ("confirm_weekly",      "liveness", "award_center", "confirm", 0.55, False),
    ("liveness_award_undone_masked", "liveness", "award_center", "entry_masked", 0.55, True),
    ("award_box_",          "liveness", "award_center", "box_wait", 0.7, True),
    ("box_1_done",          "liveness", "award_center", "box_done", 0.85, False),
    ("box_2_done",          "liveness", "award_center", "box_done", 0.85, False),
    ("box_3_done",          "liveness", "award_center", "box_done", 0.85, False),
    ("box_4_done",          "liveness", "award_center", "box_done", 0.85, False),
    ("box_1_locked",        "liveness", "award_center", "box_locked", 0.85, False),
    ("box_2_locked",        "liveness", "award_center", "box_locked", 0.85, False),
    ("box_3_locked",        "liveness", "award_center", "box_locked", 0.85, False),
    ("box_4_locked",        "liveness", "award_center", "box_locked", 0.85, False),
    ("background",          "liveness", "award_center", "bg_dismiss", 0.7, False),
    # group/
    ("group_list",          "group", "group_main", "no_group_check", 0.85, True),
    ("group_gameplay_undone", "group", "group_main", "entry", 0.7, True),
    ("group_gameplay_done", "group", "group_main", "done_state", 0.7, False),
    ("group_ac_undone",     "group", "award_center", "entry_alt", 0.7, True),
    ("notice_x",            "group", "group_main", "close_popup", 0.7, False),
    ("selected_group_gameplay_undone_button", "group", "group_main", "go_to_signin", 0.55, True),
    ("selected_group_gameplay_undone", "group", "group_main", "go_to_signin_alt", 0.55, False),
    ("selected_group_gameplay", "group", "group_main", "selected", 0.7, False),
    ("selected_group_gameplay_done_button", "group", "group_main", "done_button", 0.7, False),
    ("copper_pray",         "group", "group_pray", "copper_pray_btn", 0.55, True),
    ("above_kage_pray",     "group", "group_pray", "above_kage_btn", 0.55, True),
    ("confirm_group_pray",  "group", "group_pray", "confirm", 0.55, False),
    ("confirm_copper_pray_done", "group", "group_pray", "confirm_done", 0.55, False),
    ("first_box_wait",      "group", "group_pray", "box15_wait", 0.55, True),
    ("first_box_done",      "group", "group_pray", "box15_done", 0.7, False),
    ("second_box_wait",     "group", "group_pray", "box20_wait", 0.55, True),
    ("second_box_done",     "group", "group_pray", "box20_done", 0.7, False),
    ("second_box_done_1",   "group", "group_pray", "box20_done_alt", 0.7, False),
    ("second_box_done_2",   "group", "group_pray", "box20_done_alt2", 0.7, False),
    ("third_box_wait",      "group", "group_pray", "box25_wait", 0.55, True),
    ("third_box_done",      "group", "group_pray", "box25_done", 0.7, False),
    ("group_pray_red_packet", "group", "group_pray", "box20_redpacket", 0.7, True),
    ("group_pray_red_packet_done", "group", "group_pray", "box20_redpacket_done", 0.55, False),
    ("group_pray_red_packet_text", "group", "group_pray", "box20_redpacket_close", 0.55, False),
    ("group_pray_x",        "group", "group_pray", "close", 0.7, False),
    ("group_pray_undone",   "group", "group_pray", "pray_undone", 0.55, False),
    ("group_pray_to_pursuit_dawn_organization", "group", "group_pray", "pursuit_entry", 0.55, True),
    ("dawn_organization_award_undone", "group", "group_pursuit", "dawn_award_wait", 0.7, True),
    ("dawn_organization_award_done", "group", "group_pursuit", "dawn_award_done", 0.7, False),
    ("dawn_organization_award_check", "group", "group_pursuit", "dawn_award_check", 0.55, False),
    ("dawn_organization_award_waiting", "group", "group_pursuit", "dawn_award_stacked", 0.55, False),
    ("dawn_organization_done", "group", "group_pursuit", "dawn_org_done", 0.7, False),
    ("dawn_organization_undone", "group", "group_pursuit", "dawn_org_undone", 0.7, False),
    ("dawn_organization_entry_group_button", "group", "group_pursuit", "dawn_org_entry", 0.55, False),
    ("one_key_dawn_organization_award", "group", "group_pursuit", "one_key_swipe", 0.55, True),
    ("check_in_dawn_organization_award", "group", "group_pursuit", "check_in", 0.7, False),
    ("yesterday_award",     "group", "group_pray", "yesterday_entry", 0.55, True),
    ("yesterday_award_done", "group", "group_pray", "yesterday_done", 0.55, False),
    ("get_yesterday_award", "group", "group_pray", "yesterday_claim", 0.55, True),
    ("pray_undone",         "group", "group_pray", "pray_undone_alt", 0.7, False),
    ("share_to_friend",     "group", "group_pray", "share", 0.55, False),
    ("close_qq_share",      "group", "group_pray", "close_qq", 0.55, True),
    # recruit/
    ("headhunt_tab",        "recruit", "recruit_page", "tab_high", 0.55, True),
    ("normal_recruit_tab",  "recruit", "recruit_page", "tab_normal", 0.55, True),
    ("headhunt_entry",      "recruit", "home", "entry", 0.55, True),
    ("free_headhunt",       "recruit", "recruit_page", "free_btn", 0.55, True),
    ("free_headhunt_1",     "recruit", "recruit_page", "free_btn_alt", 0.55, False),
    ("no_free_headhunt",    "recruit", "recruit_page", "no_free", 0.55, False),
    ("discount_recruit",    "recruit", "recruit_page", "ten_btn", 0.55, True),
    ("recruit_done",        "recruit", "recruit_page", "skip_anim", 0.55, False),
    ("recruit_done_2",      "recruit", "recruit_page", "skip_anim_alt", 0.55, False),
    ("confirm_free_headhunt", "recruit", "recruit_page", "confirm", 0.55, False),
    # daily_signin (大部分来自 shared/SharedNode narutomobile 体系)
    ("check_in_daily_award", "daily_signin", "award_center", "check_done", 0.85, False),
    ("check_not_in_daily_award", "daily_signin", "award_center", "check_undone", 0.85, True),
    ("weekly_sign",         "daily_signin", "award_center", "weekly_btn", 0.55, True),
    # activity/月签到
    ("monthly_sign",        "activity", "monthly_sign", "claim", 0.55, True),
    ("monthly_sign_done",   "activity", "monthly_sign", "done", 0.55, False),
    ("monthly_sign_done_1", "activity", "monthly_sign", "done_alt", 0.55, False),
    ("monthly_sign_done_activity", "activity", "monthly_sign", "done_activity", 0.55, False),
    ("monthly_sign_undone", "activity", "monthly_sign", "undone", 0.55, True),
    ("monthly_sign_undone_activity", "activity", "monthly_sign", "undone_activity", 0.55, True),
    ("ramen",               "activity", "activity_center", "ramen", 0.55, True),
    ("sign",                "activity", "monthly_sign", "sign_btn", 0.55, True),
    ("title",               "activity", "monthly_sign", "title", 0.55, False),
    ("headhunt",            "activity", "home", "entry_activity", 0.55, True),
    # shared/
    ("x.png",               "shared", "any", "close", 0.5, False),
    ("x_right_top",         "shared", "any", "close_alt", 0.5, False),
    ("green_masked_x",      "shared", "any", "close_green", 0.5, False),
    ("notice_x",            "shared", "any", "close_notice", 0.7, False),
    ("home_button_v3",      "shared", "home", "home_button", 0.5, True),
    ("award_button_v3",     "shared", "home", "award_entry", 0.55, True),
    ("award_center_entry",  "shared", "home", "award_entry_alt", 0.55, True),
    ("award_center_entry_v2", "shared", "home", "award_entry_v2", 0.55, True),
    ("center_entry_end",    "shared", "award_center", "tab_end", 0.7, False),
    ("top_bar",             "shared", "home", "home_check", 0.7, True),
    ("ninja_guide_v3",      "shared", "home", "ninja_guide", 0.55, True),
    ("in_ninja_guide",      "shared", "ninja_guide", "in_ninja_guide", 0.55, True),
    ("guide",               "shared", "home", "guide_btn", 0.55, True),
    ("banner_jifen_v3",     "shared", "home", "banner_jifen", 0.55, False),
    ("banner_paihang_v3",   "shared", "home", "banner_paihang", 0.55, False),
    ("banner_renzhe_v3",    "shared", "home", "banner_renzhe", 0.55, False),
    ("banner_richang_v3",   "shared", "home", "banner_richang", 0.55, False),
    ("banner_zhandou_v3",   "shared", "home", "banner_zhandou", 0.55, False),
    ("bottom_dress_v3",     "shared", "home", "bottom_dress", 0.55, False),
    ("bottom_equipment_v3", "shared", "home", "bottom_equipment", 0.55, False),
    ("bottom_ninja_v3",     "shared", "home", "bottom_ninja", 0.55, False),
    ("bottom_secret_v3",    "shared", "home", "bottom_secret", 0.55, False),
    ("bottom_summon_v3",    "shared", "home", "bottom_summon", 0.55, False),
    ("bottom_talent_v3",    "shared", "home", "bottom_talent", 0.55, False),
    ("right_doujouchang_v3", "shared", "home", "right_doujouchang", 0.55, False),
    ("right_fengrao_v3",    "shared", "home", "right_fengrao", 0.55, False),
    ("right_kungfu_v3",     "shared", "home", "right_kungfu", 0.55, False),
    ("right_more_v3",       "shared", "home", "right_more", 0.55, False),
    ("right_ninfa_tie_v3",  "shared", "home", "right_ninfa_tie", 0.55, True),
    ("right_sendS_v3",      "shared", "home", "right_sendS", 0.55, False),
    ("right_shop_v3",       "shared", "home", "right_shop", 0.55, True),
    ("recruit_button_v3",   "shared", "home", "recruit_entry", 0.55, True),
    ("settings_v3",         "shared", "home", "settings", 0.55, False),
    ("activity_button_v3",  "shared", "home", "activity_entry", 0.55, True),
    ("adventure_button_v3", "shared", "home", "adventure_entry", 0.55, True),
    ("match",               "shared", "any", "match_btn", 0.7, False),
    ("daily_mission",       "shared", "any", "daily_mission", 0.7, False),
    ("get",                 "shared", "any", "generic_get", 0.55, False),
    ("cancel",              "shared", "any", "generic_cancel", 0.55, False),
    ("back_to_konoha",      "shared", "any", "back_konoha", 0.7, False),
    ("confrim",             "shared", "any", "generic_confirm", 0.55, False),
    ("confrim_small",       "shared", "any", "generic_confirm_small", 0.55, False),
    ("mask_x",              "shared", "any", "close_mask", 0.7, False),
    # home_special/
    ("back_to_main",        "home_special", "any", "back_main", 0.7, False),
    # startup/
    # (startup/ 暂未在本任务范围内使用)
]

# 子目录默认值(没匹配到任何 NAME_RULES 时的 fallback)
DIR_DEFAULTS = {
    "shared":       ("shared", "any", "unknown", 0.7, False),
    "home_special": ("home_special", "any", "unknown", 0.7, False),
    "activity":     ("activity", "activity_center", "unknown", 0.55, False),
    "group":        ("group", "group_main", "unknown", 0.7, False),
    "liveness":     ("liveness", "award_center", "unknown", 0.7, False),
    "mail":         ("mail", "mail_page", "unknown", 0.55, False),
    "recruit":      ("recruit", "recruit_page", "unknown", 0.55, False),
    "startup":      ("startup", "startup", "unknown", 0.7, False),
}


def infer(file_rel: str) -> dict:
    """根据文件名推断模板元数据。"""
    name = pathlib.Path(file_rel).name
    # 规则匹配
    matched = None
    for needle, task, page, purpose, threshold, required in NAME_RULES:
        if needle in name:
            matched = (task, page, purpose, threshold, required)
            break
    if matched is None:
        subdir = pathlib.Path(file_rel).parent.name
        matched = DIR_DEFAULTS.get(subdir, ("unknown", "unknown", "unknown", 0.7, False))
    task, page, purpose, threshold, required = matched
    return {
        "task": task,
        "page": page,
        "purpose": purpose,
        "required": required,
        "recommended_threshold": threshold,
        # 版本敏感:红点/活动图标/活动入口/装饰性 UI 高频变化;按钮/标题相对稳定
        "version_sensitive": required,
        "notes": "",
    }


def main():
    files = sorted(TEMPLATES_DIR.rglob("*.png"))
    entries = []
    for p in files:
        rel = str(p.relative_to(TEMPLATES_DIR)).replace("\\", "/")
        meta = infer(rel)
        stat = p.stat()
        meta["file"] = rel
        meta["size_bytes"] = stat.st_size
        meta["captured_at"] = None  # 暂不记录采集时间(mtime 不可信)
        entries.append(meta)

    # 按 task 分组排序,file 为次要 key
    entries.sort(key=lambda e: (e["task"], e["page"], e["purpose"], e["file"]))

    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "templates_root": "resources/templates/actions",
        "total_templates": len(entries),
        "by_task_count": {},
        "required_count": sum(1 for e in entries if e["required"]),
        "version_sensitive_count": sum(1 for e in entries if e["version_sensitive"]),
        "templates": entries,
    }
    for e in entries:
        manifest["by_task_count"][e["task"]] = manifest["by_task_count"].get(e["task"], 0) + 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Generated: {OUTPUT}")
    print(f"Total templates: {len(entries)}")
    print(f"Required: {manifest['required_count']}")
    print(f"Version-sensitive: {manifest['version_sensitive_count']}")
    print("By task:")
    for t, c in sorted(manifest["by_task_count"].items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()