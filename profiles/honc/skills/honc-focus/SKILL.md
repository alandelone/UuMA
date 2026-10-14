---
name: honc-focus
description: 回合准备、番茄钟控制、暂停/恢复、到点查成果与工时统计
---

# 回合与专注控制技能 (honc-focus)

## 触发情境
当用户：
- 准备开启新一轮专注（如「现在准备写30分钟代码」）
- 开始、暂停、恢复、结束或取消当前回合
- 专注到点，需要记录产出和工时
- 查询当前活动回合的状态与计时

## 执行准则
1. **🛸 准备回合 (`action="prepare"`)**：
   - 提取果象（`target_outcome`：这一轮的明确交付成果）、小笨事（`tiny_step`：前5分钟极易开始的微动作）、Mode（默认 Focus）、预算时长（默认 25 分钟）。
   - 可选关联当前 Main / Support 任务 ID。
   - 调用 `honc_control_round(action="prepare", ...)`。
2. **🍅 开工 (`action="start"`)**：
   - 切换状态至 `RUNNING`，开启新的计时区间。
   - 系统会自动向 Graph 广播 `focus-events`（event_type="start"）。
3. **⏸ 暂停与恢复 (`action="pause" / "resume"`)**：
   - 用户被打断时，记录中断原因并暂停。暂停区间不计入专注工时。
   - 恢复时开启新区间，继续累积有效时间。
4. **🏁 结束回合 (`action="end"`)**：
   - 到点或用户主动结束时，关闭当前区间，汇总累计有效工时。
   - 引导用户留下小成果、Next 与 Blocker。
   - **注意**：到点只结束回合生命周期，绝不自动等同于任务 `DONE`。
