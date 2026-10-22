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
2. **宿主自动完成同步**：
   - 真实用户本轮明确报告完成，由已认证消息宿主读取最新 Graph 并处理。
   - 当前 `HONC_LIFE_CURRENT_MESSAGE.work_completion` 非空时，以它的 `reply` 为准；不要重复
     调用 `honc_record_execution` 或 `honc_apply_completion`。后者的模型调用路径已由宿主阻止。
   - 唯一关联到普通 ACTION 叶子、具有 `done_when` 且不在复核／归档／Parked 状态时自动提交。
     已有任务未设项目角色不要求先改角色；任务身份不清时只补问目标。
   - 只有 `graph_verified=true` 才说明 Graph 已勾选完成。必须有实际 ExecutionReceipt 和节点读回。
   - 用户已确认：没有完成标准的旧任务先补标准，不能凭空生成标准或绕过检查。
     同步的是用户完成自述，评估记为 `USER_REPORTED`；不宣称独立验过产物。
3. **歧义与部分完成保护**：
   - 若用户仅说「弄好了」但存在多个候选任务，只保存事实，补问用户指的是哪个任务。
   - 若只完成回合小目标或尚有未满足的 `missing_items`，只保留执行事实，向用户清晰列出还差哪些项。
4. **对账与恢复 (`honc_reconcile_updates`)**：
   - 网络短暂超时使用 `honc_reconcile_updates` 查询原操作；已有生活调度也会静默对账。
     保留原操作编号和版本，不重复制造执行事件。已知版本冲突先重读核对，不盲目重试。
