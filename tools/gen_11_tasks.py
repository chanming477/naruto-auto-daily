"""gen_11_tasks.py — 批量生成 11 个简化版 task 文件。"""

TASK_TEMPLATE = '''"""tasks.{tid}_task — {cname}(2026-06-30 抄自新版 MaaAutoNaruto v1.3.35 merged.json)。

narutomobile {pipeline}.json 流程:
{flow_doc}

Pipeline (8 节点):
    1. ensure_home                 Noop
    2. {entry_node}                进{entry_desc}
    3. {card_node}                 找{cname_desc}任务卡 → 点击
    4. {action_node}               {action_desc}
    5. {fight_node}                战斗中
    6. {win_node}                  胜利 → 点击继续
    7. back_main_screen            main_green_masked.png → 回主页
    8. verify_done                 Noop
"""

from __future__ import annotations
import time
from pathlib import Path

from core.base_task import BaseTask, TaskResult, TaskStatus
from state.game_state import GameState
from tasks.navigator import (ClickAction, Navigator, Node, NoopAction, Pipeline)
from tasks.common_actions import make_recovery_chain
from tasks.pipeline_runner import (DEFAULT_REF_HEIGHT, DEFAULT_REF_WIDTH, PipelineRunner)


def _build_{tid}_pipeline(nav: Navigator) -> Pipeline:
    tpls = nav.templates
    pipe = Pipeline(entry="ensure_home")

    pipe.add(Node(name="ensure_home", action=NoopAction(), next=["{entry_node}"], focus="主页基线"))

    # 1. {entry_desc}
    pipe.add(Node(
        name="{entry_node}",
        templates=tpls({entry_templates}),
        roi={entry_roi_py}, threshold={entry_threshold},
        action=ClickAction({entry_action}),
        next=["{card_node}"], on_error=["back_main_screen"],
        max_hit=3, focus="{entry_focus}",
    ))

    # 2. 找{cname_desc}任务卡
    pipe.add(Node(
        name="{card_node}",
        templates=tpls({card_templates}),
        roi={card_roi_py}, threshold={card_threshold},
        {card_extras}action=ClickAction({card_action}),
        next=["{action_node}"], on_error=["back_main_screen"],
        max_hit=3, focus="找{cname_desc}卡",
    ))

    # 3. {action_desc}
    pipe.add(Node(
        name="{action_node}",
        templates=tpls({action_templates}),
        roi={action_roi_py}, threshold={action_threshold},
        action=ClickAction({action_action}),
        next=["{fight_node}"], on_error=["back_main_screen"],
        max_hit=3, focus="{action_focus}",
    ))

    # 4. 战斗中检测
    pipe.add(Node(
        name="{fight_node}",
        templates=tpls({fight_templates}),
        roi={fight_roi_py}, threshold={fight_threshold},
        action=NoopAction(),
        next=["{win_node}"], on_error=["back_main_screen"],
        max_hit=5, post_delay_ms=3000, focus="战斗中",
    ))

    # 5. 胜利点击继续
    pipe.add(Node(
        name="{win_node}",
        templates=tpls({win_templates}),
        roi={win_roi_py}, threshold={win_threshold},
        action=ClickAction(),
        next=["back_main_screen"], on_error=["back_main_screen"],
        max_hit=3, focus="胜利 → 继续",
    ))

    # 6. 回主页
    pipe.add(Node(
        name="back_main_screen",
        templates=tpls("state/main_green_masked.png"),
        roi=(0, 0, 1920, 1080), threshold=0.7, green_mask=True, action=NoopAction(),
        next=["verify_done"], on_error=["verify_done"],
        max_hit=5, focus="回主页",
    ))

    pipe.add(Node(name="verify_done", action=NoopAction(), next=[], focus="{cname}完成"))
    return pipe


class {classname}Task(BaseTask):
    task_id = "{tid}"
    name = "{cname}"
    category = "{category}"
    max_retries: int = 0

    def pre_check(self, ctx): return bool(ctx.common_actions and ctx.common_actions.ensure_state(GameState.HOME))
    def post_check(self, ctx, result):
        if ctx.common_actions: ctx.common_actions.ensure_state(GameState.HOME)
    def cleanup(self, ctx, result): pass
    def enter(self, ctx): return True
    def verify(self, ctx): return True
    def recover(self, ctx):
        if not ctx.common_actions: return False
        return make_recovery_chain(ctx.common_actions, double_x=False, log=ctx.bind_logger(self.task_id))

    def run(self, ctx):
        log = ctx.bind_logger(self.task_id)
        if not ctx.common_actions:
            return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message="no common_actions", attempts=0)
        adb = ctx.common_actions.adb
        project_root = Path(ctx.config.project_root)
        templates_root = project_root / "resources" / "templates" / "actions"
        r = self._run_pipeline(adb, project_root, templates_root, log)
        if r.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="{tid} done", attempts=1)
        self.recover(ctx); time.sleep(1)
        r2 = self._run_pipeline(adb, project_root, templates_root, log)
        if r2.success:
            return TaskResult(task_id=self.task_id, status=TaskStatus.SUCCESS, message="{tid} retry", attempts=2)
        return TaskResult(task_id=self.task_id, status=TaskStatus.FAIL, message=f"{tid} failed: {{r2.error}}", attempts=2)

    def _run_pipeline(self, adb, project_root, templates_root, log):
        runner = PipelineRunner(adb, project_root, templates_root, log,
                               ref_width=DEFAULT_REF_WIDTH, ref_height=DEFAULT_REF_HEIGHT)
        nav = runner.make_navigator()
        return runner.run(_build_{tid}_pipeline(nav), max_total_iterations=60, max_idle_iterations=10)


__all__ = ["{classname}Task"]
'''


def make_task(
    tid, classname, cname, category, cname_desc, flow_doc,
    entry_node, entry_desc, entry_templates, entry_roi_py, entry_threshold,
    entry_action, entry_focus,
    card_node, card_templates, card_roi_py, card_threshold, card_action,
    action_node, action_templates, action_roi_py, action_threshold, action_action, action_focus,
    fight_node, fight_templates, fight_roi_py, fight_threshold,
    win_node, win_templates, win_roi_py, win_threshold,
    card_extras='',
):
    return {
        'tid': tid, 'classname': classname, 'cname': cname, 'category': category,
        'pipeline': tid, 'cname_desc': cname_desc, 'flow_doc': flow_doc,
        'entry_node': entry_node, 'entry_desc': entry_desc, 'entry_templates': entry_templates,
        'entry_roi_py': entry_roi_py, 'entry_threshold': entry_threshold,
        'entry_action': entry_action, 'entry_focus': entry_focus,
        'card_node': card_node, 'card_templates': card_templates,
        'card_roi_py': card_roi_py, 'card_threshold': card_threshold,
        'card_action': card_action, 'card_extras': card_extras,
        'action_node': action_node, 'action_desc': action_focus,
        'action_templates': action_templates, 'action_roi_py': action_roi_py,
        'action_threshold': action_threshold, 'action_action': action_action,
        'action_focus': action_focus,
        'fight_node': fight_node, 'fight_templates': fight_templates,
        'fight_roi_py': fight_roi_py, 'fight_threshold': fight_threshold,
        'win_node': win_node, 'win_templates': win_templates,
        'win_roi_py': win_roi_py, 'win_threshold': win_threshold,
    }


TASKS = [
    make_task(
        tid='advanture', classname='Advanture', cname='冒险', category='combat', cname_desc='冒险',
        entry_node='advanture_entry', entry_desc='冒险卷轴(主页右下白底竖牌)',
        entry_templates='"Advanture/advanture_entry.png"',
        entry_roi_py='(1076, 543, 204, 177)', entry_threshold=0.85,
        entry_action='x_offset=0, y_offset=0', entry_focus='点冒险卷轴',
        card_node='advanture_in_level_roll', card_templates='"Advanture/level_roll.png"',
        card_roi_py='(0, 0, 363, 258)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0',
        action_node='advanture_go_fight', action_templates='"Advanture/go_fight.png"',
        action_roi_py='(975, 419, 305, 301)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='出战',
        fight_node='advanture_in_fight', fight_templates='"auto_battle/challenge.png"',
        fight_roi_py='(560, 0, 156, 89)', fight_threshold=0.7,
        win_node='advanture_win', win_templates='"Advanture/win.png"',
        win_roi_py='(341, 0, 600, 413)', win_threshold=0.85,
        flow_doc='advanture_entry(冒险卷轴) → advanture_in_level_roll → advanture_go_fight → 自动战斗 → advanture_win → 回主页',
    ),
    make_task(
        tid='elite_instance', classname='EliteInstance', cname='精英副本', category='combat', cname_desc='精英副本',
        entry_node='elite_instance_entry', entry_desc='精英副本入口',
        entry_templates='"Advanture/advanture_entry.png"',
        entry_roi_py='(1076, 543, 204, 177)', entry_threshold=0.85,
        entry_action='x_offset=0, y_offset=0', entry_focus='点精英副本入口',
        card_node='elite_instance_to_elite_instance', card_templates='"Elite_instance/entry.png"',
        card_roi_py='(17, 0, 357, 234)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0',
        action_node='elite_instance_go_fight', action_templates='"Advanture/go_fight.png"',
        action_roi_py='(955, 488, 325, 232)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='出战',
        fight_node='elite_instance_in_fight', fight_templates='"auto_battle/challenge.png"',
        fight_roi_py='(560, 0, 156, 89)', fight_threshold=0.7,
        win_node='elite_instance_win', win_templates='"Advanture/win.png"',
        win_roi_py='(257, 0, 834, 577)', win_threshold=0.85,
        flow_doc='elite_instance_entry → elite_instance_to_elite_instance(进精英副本) → go_fight → 自动战斗 → win → 回主页',
    ),
    make_task(
        tid='point_race', classname='PointRace', cname='积分赛', category='combat', cname_desc='积分赛',
        entry_node='award_center_enter', entry_desc='奖励中心入口(积分赛通过 ninja_guide)',
        entry_templates='"shared/award_center_entry.png", "shared/award_button_v5_real.png"',
        entry_roi_py='(1174, 302, 99, 105)', entry_threshold=0.7,
        entry_action='x_offset=3, y_offset=-51', entry_focus='点奖励中心',
        card_node='point_race_ac_entry_undone', card_templates='"Point_race/point_race_ac_undone.png"',
        card_roi_py='(180, 288, 1100, 225)', card_threshold=0.8,
        card_action='x_offset=12, y_offset=116', card_extras='green_mask=True,\n        ',
        action_node='point_race_challenge', action_templates='"SharedNode/challenge_rhombus.png"',
        action_roi_py='(1084, 380, 195, 229)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='挑战积分赛',
        fight_node='point_race_in_fight', fight_templates='"auto_battle/challenge.png"',
        fight_roi_py='(560, 0, 156, 89)', fight_threshold=0.7,
        win_node='point_race_challenge_finished', win_templates='"SharedNode/win.png"',
        win_roi_py='(298, 469, 691, 251)', win_threshold=0.8,
        flow_doc='award_center_enter → point_race_ac_undone(任务卡) → challenge_rhombus 挑战 → 自动战斗 → challenge_finished → 回主页',
    ),
    make_task(
        tid='rebel_ninja', classname='RebelNinja', cname='叛忍', category='combat', cname_desc='叛忍',
        entry_node='ninja_guide_entry', entry_desc='忍界指引卷轴(主页右下)',
        entry_templates='"shared/guide.png"',
        entry_roi_py='(934, 597, 178, 123)', entry_threshold=0.8,
        entry_action='x_offset=0, y_offset=0', entry_focus='点忍界指引',
        card_node='rebel_ninja_group_to_rebel_ninja', card_templates='"Rebel_ninja/entry.png"',
        card_roi_py='(503, 155, 276, 291)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0',
        action_node='rebel_ninja_go_fight', action_templates='"Sky_ground/gameplay.png"',
        action_roi_py='(44, 382, 177, 118)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='出战',
        fight_node='rebel_ninja_in_fight', fight_templates='"auto_battle/challenge.png"',
        fight_roi_py='(560, 0, 156, 89)', fight_threshold=0.7,
        win_node='rebel_ninja_finish', win_templates='"Rebel_ninja/entry.png"',
        win_roi_py='(503, 155, 276, 291)', win_threshold=0.85,
        flow_doc='ninja_guide → rebel_ninja_entry(切到叛忍 tab) → gameplay → 自动战斗 → finish → 回主页',
    ),
    make_task(
        tid='use_energy', classname='UseEnergy', cname='使用体力', category='daily', cname_desc='使用体力',
        entry_node='use_energy_by_ninja_piece', entry_desc='体力入口(冒险云)',
        entry_templates='"Use_energy/adventure_cloud.png"',
        entry_roi_py='(1083, 541, 199, 180)', entry_threshold=0.85,
        entry_action='x_offset=0, y_offset=0', entry_focus='点体力入口',
        card_node='use_energy_ez_sweep_entry', card_templates='"Use_energy/ez_sweep.png"',
        card_roi_py='(700, 599, 123, 104)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0',
        action_node='use_energy_ez_sweep', action_templates='"Use_energy/sweep_button.png"',
        action_roi_py='(953, 564, 164, 64)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='一键扫荡',
        fight_node='use_energy_keep_sweep', fight_templates='"Use_energy/sweep_button.png"',
        fight_roi_py='(953, 564, 164, 64)', fight_threshold=0.7,
        win_node='use_energy_finished', win_templates='"Use_energy/sweep_finish.png"',
        win_roi_py='(477, 372, 328, 192)', win_threshold=0.85,
        flow_doc='use_energy_by_ninja_piece(体力入口) → ez_sweep_entry → ez_sweep 一键扫荡 → 重复 → finished → 回主页',
    ),
    make_task(
        tid='give_energy', classname='GiveEnergy', cname='赠送体力', category='daily', cname_desc='赠送体力',
        entry_node='energy_entry', entry_desc='送体力入口(主页右侧菜单)',
        entry_templates='"shared/right_sendS_v3.png"',
        entry_roi_py='(1700, 396, 200, 100)', entry_threshold=0.8,
        entry_action='x_offset=0, y_offset=0', entry_focus='点送体力图标',
        card_node='give_energy_account_friend', card_templates='"Leaderboard/leaderboard_the_first.png"',
        card_roi_py='(143, 169, 197, 143)', card_threshold=0.8,
        card_action='x_offset=0, y_offset=0',
        action_node='give_energy_in_account_friend', action_templates='"Leaderboard/leaderboard_the_first.png"',
        action_roi_py='(259, 83, 298, 439)', action_threshold=0.8,
        action_action='x_offset=0, y_offset=0', action_focus='送体力给好友',
        fight_node='give_energy_verify', fight_templates='"Give_energy/give_energy_done_masked.png"',
        fight_roi_py='(27, 181, 63, 61)', fight_threshold=0.8,
        win_node='give_energy_done', win_templates='"Give_energy/give_energy_done_masked.png"',
        win_roi_py='(27, 181, 63, 61)', win_threshold=0.85,
        flow_doc='right_sendS_v3(右上角送S忍图标) → 进好友列表 → 给体力 → done → 回主页',
    ),
    make_task(
        tid='leaderboard', classname='Leaderboard', cname='排行榜', category='social', cname_desc='排行榜',
        entry_node='ninja_book_leaderboard', entry_desc='忍者书页右下排行榜',
        entry_templates='"Ninja_book/leaderboard.png"',
        entry_roi_py='(1112, 659, 93, 39)', entry_threshold=0.85,
        entry_action='x_offset=0, y_offset=0', entry_focus='进排行榜',
        card_node='leaderboard_in_leaderboard', card_templates='"Leaderboard/leaderboard_the_first.png"',
        card_roi_py='(444, 105, 170, 170)', card_threshold=0.8,
        card_action='x_offset=0, y_offset=0',
        action_node='ninja_book_leaderboard_like_undone', action_templates='"Ninja_book/thumb.png"',
        action_roi_py='(1000, 200, 80, 349)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='点赞',
        fight_node='leaderboard_in_leaderboard', fight_templates='"Leaderboard/leaderboard_the_first.png"',
        fight_roi_py='(444, 105, 170, 170)', fight_threshold=0.8,
        win_node='close_ninja_book_leaderboard', win_templates='"Ninja_book/close_leaderboard.png"',
        win_roi_py='(1007, 133, 36, 44)', win_threshold=0.85,
        flow_doc='ninja_book_leaderboard(忍者书右下角) → leaderboard 页 → 点赞 → close_leaderboard → 回主页',
    ),
    make_task(
        tid='more_gameplay', classname='MoreGameplay', cname='更多玩法', category='combat', cname_desc='更多玩法',
        entry_node='more_gameplay_ac_entry_undone', entry_desc='更多玩法任务卡',
        entry_templates='"More_gameplay/more_gameplay_ac_undone.png"',
        entry_roi_py='(180, 288, 1100, 225)', entry_threshold=0.8,
        entry_action='x_offset=12, y_offset=116', entry_focus='找更多玩法卡',
        card_node='more_gameplay_check_point', card_templates='"More_gameplay/mission_book.png"',
        card_roi_py='(824, 604, 274, 103)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0', card_extras='green_mask=True,\n        ',
        action_node='more_gameplay_go_fight', action_templates='"Weekly_win/go_to_war.png"',
        action_roi_py='(1069, 506, 190, 190)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='出战',
        fight_node='more_gameplay_in_fight', fight_templates='"More_gameplay/attack.png"',
        fight_roi_py='(963, 369, 316, 345)', fight_threshold=0.7,
        win_node='more_gameplay_award', win_templates='"More_gameplay/award.png"',
        win_roi_py='(434, 570, 674, 93)', win_threshold=0.85,
        flow_doc='more_gameplay_ac_undone(任务卡) → mission_book → go_to_war → 自动战斗 → award 领取 → 回主页',
    ),
    make_task(
        tid='ninja_book', classname='NinjaBook', cname='忍者书', category='daily', cname_desc='忍者书',
        entry_node='hit_to_enter_ninja_book', entry_desc='进忍者书',
        entry_templates='"Ninja_book/has_award.png"',
        entry_roi_py='(89, 98, 111, 108)', entry_threshold=0.85,
        entry_action='x_offset=0, y_offset=0', entry_focus='进忍者书',
        card_node='check_no_ninja_book_award_red_point', card_templates='"Ninja_book/ninja_book_award_undone_v2.png"',
        card_roi_py='(116, 108, 56, 79)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0',
        action_node='get_ninja_book_award', action_templates='"Ninja_book/copper_60_waiting.png", "Ninja_book/fame_waiting.png", "Ninja_book/gold_waiting.png"',
        action_roi_py='(98, 490, 1131, 148)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='领取忍者书奖励',
        fight_node='confirm_ninja_book_award', fight_templates='"Ninja_book/get_award.png"',
        fight_roi_py='(493, 562, 261, 143)', fight_threshold=0.85,
        win_node='ninja_book_done', win_templates='"Ninja_book/ninja_book_done_masked.png"',
        win_roi_py='(1204, 412, 53, 39)', win_threshold=0.85,
        flow_doc='进忍者书 → 选左 tab (award_undone) → 领 9 类奖励 → 完成 → 回主页',
    ),
    make_task(
        tid='weekly_win', classname='WeeklyWin', cname='周胜', category='combat', cname_desc='周胜',
        entry_node='award_center_enter', entry_desc='奖励中心入口',
        entry_templates='"shared/award_center_entry.png", "shared/award_button_v5_real.png"',
        entry_roi_py='(1174, 302, 99, 105)', entry_threshold=0.7,
        entry_action='x_offset=3, y_offset=-51', entry_focus='点奖励中心',
        card_node='weekly_win_ac_entry_undone', card_templates='"Weekly_win/weekly_win_ac_undone.png"',
        card_roi_py='(180, 288, 1100, 225)', card_threshold=0.8,
        card_action='x_offset=12, y_offset=116', card_extras='green_mask=True,\n        ',
        action_node='weekly_win_go_to_war', action_templates='"Weekly_win/duel_mission.png"',
        action_roi_py='(0, 110, 980, 607)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='点击决斗场',
        fight_node='weekly_win_match_fighting', fight_templates='"Weekly_win/battle_emoji.png"',
        fight_roi_py='(0, 224, 127, 154)', fight_threshold=0.7,
        win_node='weekly_win_confirm_weekly_award', win_templates='"Share/weekly_ninja_title.png"',
        win_roi_py='(0, 475, 622, 244)', win_threshold=0.85,
        flow_doc='award_center_enter → weekly_win_ac_undone → duel_mission → 出战 → 战斗 → confirm_weekly_award → 回主页',
    ),
    make_task(
        tid='sky_ground', classname='SkyGround', cname='天地', category='combat', cname_desc='天地',
        entry_node='ninja_guide_entry', entry_desc='忍界指引卷轴',
        entry_templates='"shared/guide.png"',
        entry_roi_py='(934, 597, 178, 123)', entry_threshold=0.8,
        entry_action='x_offset=0, y_offset=0', entry_focus='点忍界指引',
        card_node='sky_ground_gameplay', card_templates='"Sky_ground/gameplay.png"',
        card_roi_py='(44, 382, 177, 118)', card_threshold=0.85,
        card_action='x_offset=0, y_offset=0',
        action_node='sky_ground_mode', action_templates='"Sky_ground/sky_ground_icon.png"',
        action_roi_py='(190, 150, 913, 224)', action_threshold=0.85,
        action_action='x_offset=0, y_offset=0', action_focus='切到天地 tab',
        fight_node='sky_ground_in_fight', fight_templates='"Weekly_win/battle_emoji.png"',
        fight_roi_py='(5, 267, 79, 68)', fight_threshold=0.7,
        win_node='sky_ground_end', win_templates='"Sky_ground/back.png"',
        win_roi_py='(1160, 0, 119, 91)', win_threshold=0.85,
        flow_doc='ninja_guide → 切天地 tab → sky_ground_entry → in_fight → 战斗 → end → back → 回主页',
    ),
]

from pathlib import Path
DST = Path(r'D:\火影自动日常\tasks')
DST.mkdir(parents=True, exist_ok=True)

for t in TASKS:
    code = TASK_TEMPLATE.format(**t)
    out = DST / f"{t['tid']}_task.py"
    out.write_text(code, encoding='utf-8')
    print(f'  {out.name} ({len(code)} bytes)')

print(f'\n== done. generated {len(TASKS)} task files ==')
