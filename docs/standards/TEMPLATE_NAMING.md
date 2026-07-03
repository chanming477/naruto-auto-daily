# TEMPLATE_NAMING.md — 模板命名规范

> 680+ 个模板在 `resources/templates/actions/`(56 子目录)。**统一 snake_case + 按 task 分目录**,**不要用驼峰或 PascalCase**。

## 1. 目录命名

**禁止大小写混合**(例如 `Activity/` 和 `activity/` 并存)。2026-06-30 现状是 narutomobile 镜像(大小写混合),后续 task 引用都按现状,**未来**逐步统一为小写 snake_case。

| 现有目录 | 现状 | 建议 |
|---------|------|------|
| `Activity/` | 大写 | snake_case `activity/` |
| `auto_battle/` | snake_case | ✅ |
| `Black_market_merchant/` | PascalCase | snake_case `black_market_merchant/` |
| `Easy_helper/` | PascalCase | snake_case `easy_helper/` |
| `Mail/` | 大写 | snake_case `mail/` |
| `SharedNode/` | PascalCase | snake_case `shared_node/` |
| `Startup/` | 大写 | snake_case `startup/` |

**未来任务**(本次不动): 写脚本把所有大写目录改小写,同步更新 `tasks/*.py` 里的 template 路径。

## 2. 文件命名

### 命名格式

`<scope>_<object>_<state>.png` 三段:

- **scope** (可选):模板所在子模块,如 `headhunt_`、`mail_`、`select_`
- **object**:模板视觉对象,如 `go_fight`、`check_in_daily_award`、`one_key`
- **state** (可选):状态修饰,如 `_undone` / `_done` / `_waiting` / `_selected`

### 例子

✅ 好的:
- `Mail/mail_envelope.png`
- `Mail/mail_wait.png`
- `Mail/mail_done.png`
- `Weekly_win/weekly_sign.png`(虽然是 `Weekly_win/Weekly_win/...` 现存但)
- `Group/group_pray_go_btn.png`
- `Activity/mouthly_sign_undone.png`

❌ 不好的:
- `mailEnvelope.png`(驼峰)
- `MailEnvelope.PNG`(驼峰 + 大写扩展名)
- `award_button_v3.png`(用版本号版本太多)— 更倾向 `award_button_v5_real.png`(指明用途)
- `x.png`(太通用 — 文件名一律如此会冲突)

## 3. 状态命名

| 后缀 | 含义 |
|------|------|
| `_undone` | 未完成(可点击执行) |
| `_done` | 已完成(灰显 / 跳过) |
| `_waiting` | 可领取奖励(黄色感叹号) |
| `_selected` / `_masked` | 已选中(用于 green_mask 模板匹配) |
| `_v2` / `_v3` / `_v5_real` | 同一对象的版本迭代(更高版本优先放 fallback 最前)|

## 4. 版本管理

如果一个模板需要更新(UI 变更):
1. **保留** 旧模板(不要删,可能其它账号还在用)
2. 加新版本 `xxx_v2.png` 或 `xxx_v5_real.png`
3. 把它加到该 task 的 fallback chain **最前**(优先级最高)
4. 旧模板仍在 chain 后面 fallback(对老账号有效)

## 5. 不要做

- ❌ 同一个对象**多个名字**(例 `mail_envelope.png` + `Mail/email.png` 共存)
- ❌ 路径含中文(只允许 ASCII — narutomobile 路径全是 ASCII)
- ❌ 模板带 `_v1` / `_v2_final` / `_v2_real_v3` 这种版本号贪多
- ❌ 把模板放在 `resources/templates/` 顶层(已经全部移到 `actions/<task>/`)
- ❌ 在 `scripts/` 或 `docs/` 里放 PNG(只能用 `resources/templates/`)

## 6. 校验

跑 `python tools/validate_templates.py`:
- 检查每个 task 在 `tasks/<tid>_task.py` 引用的模板是否存在
- 检查每个模板文件是否被某个 task 引用(孤儿)
- 输出 `manifest.json` 用于团队参考

## 7. 命名速查(按对象类型)

| 对象类型 | 例子 |
|---------|------|
| 入口图标 | `headhunt.png` / `award_center_entry.png` |
| 关闭按钮 | `x.png` / `green_masked_x.png` / `notice_x.png` |
| 确认 / 领取 | `confrim.png` / `get.png` / `one_key_claim.png` |
| 任务卡(未完成) | `xxx_ac_undone.png` / `xxx_undone.png` |
| 任务卡(已完成) | `xxx_done.png` / `xxx_done_masked.png` |
| 进度状态 | `xxx_wait.png` / `xxx_done.png` / `xxx_waiting.png` |
| 主页标识 | `main_green_masked.png` (绿通道匹配) |
| 状态变化模板 | 加 `_v<n>` 或 `_v<n>_real` 后缀 |
