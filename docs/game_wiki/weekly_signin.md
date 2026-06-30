# 每周签到任务 (weekly_signin)

> **任务 ID**: `weekly_signin`
> **任务类型**: weekly(每周)
> **代码文件**: `tasks/weekly_signin_task.py`(251 行,Phase 7 新增)
> **设计目标**: 主页 → 点击"每周签到"按钮 → 确认签到 → 关闭弹窗 → 返回主页

---

## 1. 入口路径(待 v1.1 校准)

**假设路径**(未在用户当前 UI 实测):

```
主页 → 主页右侧"奖励"信封(1170, 290, 130, 100)
    → 奖励中心 → "周签到" tab(待 OCR / 模板定位)
    → 主页"每周签到"按钮 (510, 540, 250, 110)
```

> ⚠️ **校准状态**: 代码里写死 `ROI_WEEKLY_SIGN = (510, 540, 250, 110)`,但**未在真机验证**。
> 计划书 §1.2.1 主页勘察任务中必须实测确认。

---

## 2. 实测 ROI(1920×1080,代码注释值,**未校准**)

| 节点 | ROI | 模板 | 阈值 |
|---|---|---|---|
| find_weekly_sign | (510, 540, 250, 110) | shared/weekly_sign_v3.png / shared/weekly_sign.png | 0.55 |
| confirm_weekly_sign | (860, 560, 200, 80) | shared/confrim.png / confrim_small.png / get.png | 0.55 |
| close_popup | (1820, 60, 80, 80) | shared/x.png / x_right_top.png / green_masked_x.png / notice_x.png | 0.5 |
| back_to_home | (30, 700, 100, 80) | shared/home_button_v3.png | 0.5 |

---

## 3. Pipeline(6 节点)

```
[1] ensure_home          Noop           (pre_check)
[2] find_weekly_sign     ClickAction    → confirm_weekly_sign | on_error: verify_done
[3] confirm_weekly_sign  ClickAction    → close_popup     | on_error: close_popup | max_hit=2
[4] close_popup          ClickAction    → back_to_home    | on_error: back_to_home | max_hit=2
[5] back_to_home         ClickAction    → verify_done
[6] verify_done          Noop(终点)
```

**关键设计点**:
- ✅ 永不调用 `KeyAction(key="BACK")`(用界面 X 按钮)
- ✅ best-effort SUCCESS: 失败也返回 SUCCESS(`run()` 末尾)
- ✅ 重试机制: 失败后 `recover()` 点 (1826,84) + (85,760) 再跑一次
- ✅ `pre_check()` 验证 `GameState.HOME`

---

## 4. 任务骨架

```python
class WeeklySigninTask(BaseTask):
    task_id = "weekly_signin"
    name = "每周签到"
    category = "weekly"
    max_retries: int = 0

    # pre_check / post_check / cleanup / enter / verify / recover / run
```

**Run 流程**:
1. 检查 `ctx.common_actions` 非空
2. 第一次跑 pipeline
3. 失败 → `recover()` → 第二次跑 pipeline
4. 都失败 → best-effort SUCCESS

---

## 5. 依赖模板清单

| 模板路径 | 用途 | 状态 |
|---|---|---|
| `shared/weekly_sign_v3.png` | 主页每周签到按钮 | ❓ 待校准 |
| `shared/weekly_sign.png` | 主页每周签到按钮(备用) | ❓ 待校准 |
| `shared/confrim.png` | 弹窗确认按钮 | ❓ 待校准 |
| `shared/confrim_small.png` | 弹窗确认按钮(小) | ❓ 待校准 |
| `shared/get.png` | 领取按钮(共用) | ✅ 通用 |
| `shared/x.png` | 关闭按钮 | ✅ 通用 |
| `shared/x_right_top.png` | 右上 X 按钮 | ✅ 通用 |
| `shared/green_masked_x.png` | 绿色遮罩下的 X | ✅ 通用 |
| `shared/notice_x.png` | 通知弹窗 X | ✅ 通用 |
| `shared/home_button_v3.png` | 主页橙色按钮 | ✅ 通用 |

---

## 6. 已知问题 & 风险

1. **入口 ROI 未校准**: (510,540,250,110) 是注释值,真机可能漂移
2. **奖励中心 → 周签到 tab 路径未实现**: 当前 pipeline 默认用户在主页就能找到"每周签到"按钮
3. **未在 main.py 注册**: v1.1 已计入第 7 任务,但 main.py 需补 `cmd_weekly_signin_real` + `register_task`(同步修复中)
4. **best-effort SUCCESS**: 找不到入口也会返回 SUCCESS,日志记 "weekly_signin best-effort: ..."

---

## 7. 校准 Checklist(§1.2.1 主页勘察阶段执行)

- [ ] 实测主页"每周签到"按钮真实位置(在主页能直接看到?还是在奖励中心?)
- [ ] 若在奖励中心:确认"周签到"tab 的 OCR 文字或模板
- [ ] 采集 3-5 张每周签到页截图存 `screenshots/calibration/weekly_signin_*.png`
- [ ] 更新 ROI 到 `template_manifest.json` 和本文档
- [ ] 在 main.py 补注册(同步进行)
- [ ] 跑 `dryrun_weekly_signin.py` 验证
