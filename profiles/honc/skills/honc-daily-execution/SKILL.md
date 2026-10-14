---
name: honc-daily-execution
description: 记录日常执行事实、进展、成果、Next、Blocker、状态与过往补记
---

# 日常执行记录技能 (honc-daily-execution)

## 触发情境
当用户：
- 汇报当下的工作进展（如「刚才写了30分钟，完成了两段」）
- 补记过去的活动（如「昨天晚上有做有氧，帮我补记」）
- 报告卡住或阻塞（「遇到 500 报错，卡在环境配置」）
- 报告当前体力、精力或场景状态（「现在累了，在路上」）
- 询问今天做了什么或查询进展

## 执行准则
1. **调用 `honc_record_execution`**：
   - 提取成果（`outcome`）、下一步（`next_step`）、阻塞坑（`blocker`）和当前状态（`state`）。
   - 如果用户提到投入时长，指定 `actual_duration_seconds` 与 `actual_kind`（`timed`, `user_reported`, `estimated`）。
   - 若用户未提及确切时长，**严禁猜测编造**，`actual_duration_seconds` 留空，`actual_kind` 设为 `unknown`。
2. **处理补记**：
   - 补记昨日或历史事件时，将 `occurred_at` 设为实际发生日期的 ISO 时间戳，系统会自动保留 `recorded_at` 为当前记录时间。
3. **纠正已有记录**：
   - 若用户指出先前的记录有误（如「刚才说的不是完成，只是初稿」），调用 `honc_correct_record` 追加修正事件，保留原始历史链条。
4. **响应结构**：
   - 明确告知用户：事实已记入账本，当前任务关联状态与下一步建议。
