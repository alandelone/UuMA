---
name: honc-tracing
description: 任务验收标准核对、依据留存、Graph 完成回写与回执对账
---

# 任务完成核对与追踪技能 (honc-tracing)

## 触发情境
当用户：
- 明确表示某项任务已完成（如「登录模块单元测试全部写完并通过了，这个任务完成了」）
- 询问某个任务的验收标准或还差什么
- 撤销先前的完成状态或重开任务
- 查询待同步的外部更新与对账

## 执行准则
1. **核对验收标准 (`honc_assess_completion`)**：
   - 提取任务 ID 与用户的完成依据。
   - 读取任务在 Graph 上的 `done_when` 标准快照。
   - 逐项核对满足项（`satisfied_items`）与缺失项（`missing_items`）。
   - 若标准为空或缺失，判定为 `INSUFFICIENT`，告知用户缺少标准，不能盲目提交。
2. **提交 Graph 完成 (`honc_apply_completion`)**：
   - 仅在用户**明确报告完成**且核对结果为 **`SATISFIED`** 时提交。
   - 传入任务 ID、用户输入凭据 `trusted_input_id` 以及评估 ID `assessment_id`。
   - 系统将生成唯一 `operation_id` 并提交至 Graph 的 `/api/v2/execution/action-decisions`，获取 `ExecutionReceipt`。
3. **歧义与部分完成保护**：
   - 若用户仅说「弄好了」但存在多个候选任务，只保存事实，补问用户指的是哪个任务。
   - 若只完成回合小目标或尚有未满足的 `missing_items`，只保留执行事实，向用户清晰列出还差哪些项。
4. **对账与恢复 (`honc_reconcile_updates`)**：
   - 若提交由于网络短暂超时处于等待，定期调用 `honc_reconcile_updates` 查询原回执，不重复制造执行事件。
