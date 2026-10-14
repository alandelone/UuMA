# 作者 Intent 与模板槽位的明确对应契约

依据原 ST-05/06/11/13/14/20/21/22 和 G-08；保留原 118 条／全部 11 组。

原作者 Section、Paragraph、Group、Intent、Thought、公式、附件关联、引用和论证边继续以原编号存放。模板槽位通过作者明确选择的原 Intent 编号引用原思想，不复制思想、不改作者原意、不按标签猜对应关系。一个原 Intent 同时最多对应一个已安置的模板 Intent；目标保留自己的固定来源。可以选择不同层级、不同同名章节中的任意槽位，预览以完整路径和编号区分。

原作者段落保留用途、范式、关系、完整组和原章节上下文。其公式／附件需要作者单独勾选目标段落，最多一个当前输出位置，防止分拆 Intent 时自动重复或遗漏。其他目标仍能回查同一原作者上下文。全部对应和上下文位置以文档版本保存，撤销／重做恢复整个原文档；原内容本体始终保留，取消预览不写入，源／目标／关系变化使原确认失效。

新增 JSON 字段为 Intent 的 `author_intent_ids` 与 Paragraph 的 `author_context_paragraph_ids`。不新增数据库表、不改变既有数据或生成版本。后端拒绝不存在／外来／重复／循环／未安置目标／缺固定模板来源的对应和重复上下文位置，保持现有稿件权限、冲突、不可变操作和原版本校验。

生成和 Chat 按明确对应解析目标思想。生成必须拒绝任何未对应原 Intent、未指定输出位置的公式／附件、未定原空段落／段落组以及尚未填写的模板槽位。原作者结构、章节路径、段落组、全部 L2 端点与条件保留在固定输入和输出追溯中，映射不等于科学批准。每个思想只在指定目标参与一次生成；原文件／资产与公式编号保持。

验收需覆盖完整来源预览、部分对应、多个任意目标、原上下文输出位置、确认过期、取消、保存刷新、独立逐次 Undo/Redo、失败／冲突／断线恢复、Chat 固定选区、生成缺项拒绝与完整成功链。软件测试／合成夹具只能证明软件行为，真实学术来源、真实内容与完整 11 组继续单独实跑。


2026-10-09 correspondence generation execution contract correction BEFORE read-view repair:
generation-v1 retained19passes/two failures. Actual generation+real artifact compiler succeeded,
but immutable generated read compared populated referenced author Intents against raw empty
template slots and rejected the original input. The reader must derive the same deterministic
realization projection from the EXACT frozen author revision, preserving canonical author bank,
fixed target source, original group/full contexts and relation conditions. Retain all original
validated-call/hash/output/mapping guards; add exact original bank/context/formula/asset guards
for mapped output. Tampering with frozen source/context/projection must remain rejected.
The other new check incorrectly assumed a block_ids API field: comment_changes exposes actual
before/after documents. Verify stable IDs by the existing changed-block calculation on those
exact documents, plus unchanged association events through Undo/Redo/archive/restore. No guard
or assertion scope is reduced. No real model, scientific acceptance or native download claim.


2026-10-09 after1041PASS native exact audit, final completion audit adds the original
L2-condition corruption case. l2-before-v1 proves a real gap: mapped model-call input condition
altered with a recomputed request hash still passed immutable generated read. Existing bank,
context, formulas/assets and output guards all remain. Reader must recompute complete original
argument_context from the fixed raw author revision plus same deterministic target projection,
and require exact model input edges/endpoints/content/condition. Record before changing code,
retain new failing test and run narrow then full final source. Native current valid result must
remain readable; no rewrite of historical source, database schema or actual worker/approval.
