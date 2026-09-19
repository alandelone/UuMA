# UuMA 工程标准评审

日期：2026-09-18。基线：`08377639363110160302ec12147ceea56f14b9f2`；本地 HEAD 与评审时 `origin/master` 的远端查询结果一致。

依据：用户提供的《Agent 工程标准》和《多 Agent 协作工程标准》（Agent Harness Codebook / zh-CN，均为 Draft Standard）。本报告是按这两份标准进行的工程评审，不是认证，也不替用户批准仓库阶段转换。

## 结论

建议保留 verification / pending_review。UuMA 已具备控制面、专门角色、数据库分离、事件日志、知识候选审核和测试基础；但共享控制状态的授权、并发和完成验证存在可复现的缺口，目前不足以证明满足两份标准的 Production Definition of Done。优先补强确定性提交边界，再扩大写入型多 Agent 使用范围。

## 已复现的问题

以下均使用临时目录和假 Hermes 路径复现，没有调用真实 Agent 或外部业务服务。P1 表示需要优先修复的正确性或权限问题。

### R1 — P1：Worker 能自行取消图变更审批

位置：`src/uuma/mcp_worker.py:153` 的 `propose_graph_operation`；`src/uuma/service.py:270` 的 `propose_operation`。

Worker MCP 只检查 requested_by 是否匹配身份，然后接受调用方传来的 requires_user_approval。Worker 将它设为 false 时，服务写入 AUTO_APPROVED 并立即执行图变更，没有按变更类型、目标所有权或结构风险重新判断。

复现：以 Brainstormer 的 Worker MCP 入口提交一个 project 节点 UPSERT，requires_user_approval=false，直接生成 revision=1 的共享节点。工具返回仍声称 PROPOSED。这违反仓库自身“Worker 只能提议”的 MCP 边界，也违反 Agent §8 和多 Agent §2、§9。此发现针对控制图，不能据此声称 Wisdom 的独立知识审核也被绕过。

建议：服务器计算审批需求；Worker 身份只允许创建待审提案；审核、应用入口按可信身份和资源范围验证。回归应拒绝 Worker 通过 JSON 标志写入共享 project/topic/dependency。

### R2 — P1：版本检查不在提交事务中，并发写入静默覆盖

位置：`src/uuma/service.py:526`、`:270`、`:293`；`src/uuma/projections.py:179`。

expected_revision 在单独连接中读取后关闭，后续事件追加才开启事务。EventStore 的 BEGIN IMMEDIATE 能保证日志与投影原子写入，却不能保护先前的版本判断；图投影 UPSERT 无条件覆盖 data_json。

复现：两个独立 ControlPlane 实例读取同一节点 revision=1，用 barrier 让两次真实版本检查都完成后继续提交。两个提案均成功，最终 revision=3，前一个数据被后一个覆盖。barrier 仅控制合法并发时序，没有更改存储逻辑。违反多 Agent I-03、§8 和 §11。

建议：在同一事务内校验必填 base_version、写入事件和投影；第二个写者返回冲突。审批记录与应用也需要原子提交或明确的可恢复中间状态。

### R3 — P1：心跳可以直接写入终态，绕过 ResultContract

位置：`src/uuma/service.py:192`；`src/uuma/projections.py:116`。

RunProgress.status 接受完整 RunStatus 枚举，report_progress 校验当前 Run 未终结后就把传入状态交给投影。于是 Worker 可通过心跳上报 COMPLETED，绕过 submit_result 的验收检查。

复现：任务要求 not-done 验收项，但仅发送 status=COMPLETED 的心跳即可令 Run 完成，result 仍为 null，任务投影仍为 RUNNING；之后正常提交结果又被“终态不可提交”检查拒绝。违反 Agent §4、§9 和多 Agent §11。

建议：心跳只更新进度字段或严格允许的非终态；所有终态转换经过唯一验证入口，并同时维护 Task/Run 一致性。

### R4 — P1：旧 Run 能回退已完成 Task

位置：`src/uuma/service.py:152`；`src/uuma/projections.py:278`，特别是 `:304`。

同一 Task 可注册多个 Run，没有持久化当前 attempt/owner 的提交资格。结果和阻塞事件只验证自身 Run 状态，然后无条件更新它所属的 Task。

复现：同一任务创建两个 Run；新 Run 提交成功后 Task=COMPLETED；仍在运行的旧 Run 上报 BLOCKED，Task 立即回退为 BLOCKED。无需并发线程即可重现。违反多 Agent I-02、I-05 和 §10–11。

建议：明确合法重试/接管规则，持久化 active_attempt 和递增 epoch，在真正写 Task 的事务中检查版本与 epoch；旧 attempt 可补充审计，但不可更改权威状态。

### R5 — P1：幂等键不能阻止并发重复建任务

位置：`src/uuma/service.py:80`、`:586`；`src/uuma/event_store.py` 的 tasks schema。

实现先扫描 JSON 合同查找 idempotency_key，再单独插入任务；数据库没有该键的唯一约束。任务 UUID 不同就不会触发主键冲突。

复现：两个 ControlPlane 实例同时完成相同 stable-key 的未命中查询，然后各自 create_task，得到两个不同 task_id。此处证明的是重复任务入场；没有执行或声称已经发生重复外部付款等副作用。违反多 Agent §5–6 的稳定身份与确定性去重要求。

建议：将幂等键及作用域做成受唯一约束的字段，在事务内原子认领；相同键相同请求返回原结果，不同请求摘要应返回冲突。另需定义 semantic_key，防止不同请求键代表同一业务意图。

### R6 — P1：Worker 自报检查通过即成为权威完成

位置：`src/uuma/service.py:218`，`tests/test_control_plane.py` 的完成路径测试。

submit_result 只检查 Worker 提交的 check 名称及 passed 布尔值；不验证独立评审记录、验收证据真实性或 artifact 关联。即使验收列表不为空，Worker 仍同时生产结果并自证通过。

复现：Worker 对 independent-check 发送 passed=true，不提供 artifact 或独立 verifier 记录，Task/Run 都直接 COMPLETED。现有测试将这一行为作为成功路径。违反 Agent §9“DONE 由 Independent Verification 触发”及多 Agent §2。

建议：Worker 提交 RESULT_READY/REVIEW；独立 verifier 针对冻结的 acceptance 与结果摘要生成验证证据，再由确定性提交入口进入完成。单纯增加一个 Worker 可填写的 reviewer 字段无效。

## 标准覆盖评价

| 工程面 | 观察与评价 |
| --- | --- |
| Truth / Role | 控制数据库、wisdom.db、Hermes 状态的责任划分清楚；Worker 图写入例外必须修复。 |
| Mission Contract | TaskContract 有目标、风险、能力、验收名和引用；缺少任务级 allowed/forbidden scope、步骤/时间/token/费用预算和完整 stop 条件。RunProgress 的 attempt≤3 是输入约束，不等于执行次数预算。 |
| Durable Runtime | 事件追加与投影更新同事务、日志链可检查、投影可重建是优点；业务状态迁移缺少统一 CAS/epoch。 |
| Context / Memory | 知识来源、候选和审核模型及专用存储有基础；本轮没有验证所有检索 ACL、TTL、删除路径或真实部署隔离，不能判定全面达标。 |
| Tools / Authorization | 有类型模型、身份边界、HTTP bearer 角色和能力过滤；审批需求仍存在调用方可自报路径。 |
| Verification | 43 项相关现有测试通过，但没有阻止本报告六项复现；还需要独立验收及恶意输入、并发、崩溃恢复测试。 |
| Semantic / Effect Consistency | Hermes Kanban adapter 传递稳定任务幂等键是优点；控制层自身并发去重不足。知识投影有 outbox，不能据此推断所有外部业务 Effect 都已有 ledger/reconciliation。 |
| Scheduling / Protocol | 核心 Task/Run 合同未携带 lease_epoch、稳定 txn/semantic 身份和协议能力协商元数据；Hermes 上游能否提供等价保证需要独立集成证据。 |
| Observability | 已有 correlation_id、事件日志与 Hermes observability 集成；本轮未检查线上 trace 的完整性或实测 SLO。 |
| Multi-Agent Admission | 本轮未验证到单 Agent 对照下的质量、成本、延迟收益证据；应作为投产门槛提供，不能仅由角色数量推定收益。 |
| Operations / Recovery | 有恢复/降级文档及历史验收记录；本轮没有重启线上 Hermes、KAG 或 Docker。故障注入覆盖还需要 coordinator crash、旧 owner 恢复、ACK 丢失与补偿超时等。 |

## 修复次序与验收

1. 先封闭 Worker 图写入和心跳终态路径；使提议、验证、提交角色在代码上分离。
2. 把版本判断、幂等认领、active attempt/epoch 检查和事件提交收敛到一个事务边界。
3. 增加独立完成验证，再补 Mission Contract 预算、终止条件与实际执行计量。
4. 将本报告六条复现改为“应拒绝或保持原状态”的回归测试；扩展到重放、并发、断点恢复和外部 Effect UNKNOWN 调和。
5. 完成隔离环境全量测试、Hermes 集成与故障注入证据后，由用户/Orchestrator 决定是否批准阶段转换。

## 本轮验证和限制

- 本地 HEAD 与 GitHub master：`08377639363110160302ec12147ceea56f14b9f2`。
- 定向既有测试：`test_control_plane.py`、`test_brainstormer_state.py`、`test_knowledge_system.py`、`test_wisdom_code_audit_regressions.py`、`test_uuma_control_guard.py`，共 **43 passed**。
- 六项隔离复现：全部确认，脚本保留在 `.uuma-local/review/probe.py`。脚本断言的是缺陷当前存在，不是修复后安全性测试。
- 全量 pytest 收集阶段因 `ModuleNotFoundError: No module named 'ruamel'` 失败，没有得到全量通过结论。工作区原无 .venv；完整依赖下载耗时较长而停止。定向验证使用已有 Python 3.12 环境；临时 .venv 后配置为可读已有系统包，不能视为干净依赖复现。
- 未修改产品源码、未提交/推送、未发布 GitHub 评论、未改变 mission_status.json；此报告保存在本地供审阅。
- 初始已有 `Question Orbit Engine.docx`、`build_question_orbit_doc.py` 和 session progress 修改；评审期间另一会话完成文档并移除了其生成脚本、更新并关闭共享 session。本次未修改其文档或脚本；随后新开评审收尾 session，并在交接中保留其结果。
- `git diff --check` 报告 active-session 生成文件的 CRLF 尾随空白；没有据此修改生命周期实现，不能报告整个工作区 whitespace 检查通过。此次只增加评审材料、临时环境/复现数据及生命周期交接记录。
