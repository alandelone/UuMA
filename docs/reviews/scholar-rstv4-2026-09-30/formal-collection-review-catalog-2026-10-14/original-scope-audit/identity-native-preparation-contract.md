# 当前身份重审原生最小准备合同（未执行）

父代理执行；本代理未复制、未打开DB、未启动服务/浏览器、未运行脚本。完整回归66789运行期间继续冻结产品src/tests/scripts。保留用户指定卡住IAB tab2，整个验收不访问、重置、关掉或限速该页。

## 一致复制与来源

1. 来源根：C:/Users/Alandelone/AppData/Local/Temp/scui-g11-native-22n_zg_d，DB=data/catalog.db。不得对源根执行写入或“修复”。父代理先新做SQLite只读连接的consistent backup到唯一新mkdtemp目录，目的必须不存在；复制资料使用原字节，不重放setup/seed/worker。不要直接copy可能活跃的DB/WAL单文件。
2. 副本DB的105表schema/rows应逐字段等于GPU成功后封存快照（摘要d713569c259e9b2cf4f86a4488280f9806235e6dda9654d8a27ff7526932cb2f）。若源已变化，停止并记录真实变化、选择已有真实一致快照来源；不把旧快照表灌回源DB。复制DB字节可能因SQLite backup页布局不同，不伪称物理字节相同。原根前后逻辑数据及声明资料字节必须相同。
3. 当前源文件记录storage_path保留原历史绝对路径：C:\Users\Alandelone\AppData\Local\Temp\scholar-review-recovery-2026-10-06-3xtv51bn\data\artifacts\papers\paper_dde0a449e93444c2771e7b0edeb7daf9\85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99\source.pdf；不改DB路径。该真实PDF只读核对1827B/SHA85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99，原纸/两次成功parse/6次失败成功历史均不替换。可把源根data/artifacts与data/paper-import原字节复制到新根相同相对目录，仅供完整资料保存；历史记录仍读原绝对PDF，输出/cache只允许新owned根。不得复制私有GPU配置、模型权重或启动MinerU。
4. 复制后全部schema/rows保持。当前基线中research_nodes=0、manuscripts=0，不需要任何科研批准。两个Collection固定：新collection_62ca47c927342115eb5f8fd870af9ca6 ACTIVE/r3；旧collection_d016024afda6fbf0ce956023f80306a8 PAUSED/r4。

## 仅服务准备，不做动作

新端口需实时查空闲（不假定8891可用，不触碰保留卡页/其他Studio）。启动真实Catalog正式当前冻结源码，新owned根，无worker、无extractor、无远程model gateway；拒绝所有模型/生成/collection新建/重试/实验/科学write。允许正常GET，以及唯一身份case的两次POST /api/catalog/review/cases/source_file_491d18ddee7958c95deb123a188280d5/actions。实际输入action只允许REOPEN_IDENTITY/APPROVE_IDENTITY，理由必须明确软件验收；从正常页面上下文产生expected_context_sha256与唯一requestID，不能在浏览器注入fetch。若正常UI需要discussion-context只读POST，可显式允许只读入口，绝不SEND。

先完整warm-load GET并捕获baseline；有真实GET副作用须解释并独立封存，不能把任意runtime写入放进宽白名单。本场景未调用Collection progress/budget，默认collection_runtime_state也精确保持。所有原已存在文件逐字节保持；只允许新owned根的独立PDF预览派生cache，并明列新文件，不把cache当新解析。

## 原生动作与状态

通过正式Catalog论文详情→PDF versions→“复核当前文件与记录”（实际链接 /?view=review&case=source_file_491d18ddee7958c95deb123a188280d5）进入；该入口支持已VERIFIED文件，不需要伪造待审记录。

- 初始：标题Software review identity title、DOI10.1234/corrected、原PDF及原核对批注/审核历史在场；当前文件VERIFIED；按钮“重新审核当前文件身份”。记录source_impact正好2个非终态job、0科研node、0稿件。若上下文不同，先说明差别，不直接执行。
- 填写新明确软件复核说明，按“重新审核当前文件身份”一次。期望IDENTITY_REOPENED，文件NEEDS_REVIEW，scientific_approval_restored=false；两个既有非终态任务NEEDS_HUMAN/last_error=SOURCE_REVIEW_REOPENED/fence各+1。原终态任务一律精确不动。
- 当前依据变更提示出现时读取新上下文并用“对照新状态后继续”；不强制修正已经正确的标题/DOI，不用手填假源，不把annotation当批准。现有原PDF确实对应Catalog，复核说明写明此事实。
- 点击“复核并批准文件身份”一次。期望APPROVED_IDENTITY、技术身份VERIFIED、两个非终态任务恢复READY，attempts仍分别1与0，不执行READY任务。两个既有PARSE_PDF job按相同幂等键返回原ID，无追加解析job预期；若多出job即检查真实key，不能自动放宽断言。旧PAUSED Collection始终PAUSED，身份批准不恢复科学批准。
- 原生刷新后VERIFIED、两新动作时间/来源/署名与原审核历史共存；Catalog仍同一paper/file/source与两次成功parse；没有新publication/模型/attempt。保存DOM/截图与两次响应，再独立全表/原文件比较。

## 允许变更（精确三表，其他102表和全部schema保持）

| 表 | 唯一允许变化 |
|---|---|
| source_file_versions | 同一file行identity_status VERIFIED→NEEDS_REVIEW→VERIFIED；validation_json仅真实再验结果。sha/size/path/ID/所有其他字段精确 |
| catalog_review_actions | append-only恰好2行REOPEN_IDENTITY、APPROVE_IDENTITY；case/file精确，old rows不变；supersedes链承接旧identity action，再接新reopen |
| acquisition_jobs | 仅job_ce6c4d42d5f07ead8f5bd6d21189427c(READY/attempt1/fence1→2)及job_fe4651959298eab54d88abd9edaf6760(READY/attempt0/fence0→1)的恢复状态/lease/error/result/available_at/updated_at；最终READY，attempt/input/digest/其他字段不变，无新增行 |

全部SUCCEEDED/SKIPPED/FAILED_TERMINAL job、所有attempt、workerpresence、trace、parse/paper版本、body/ref、modelcall、approvals、科研表、Collection状态/版本、来源批注、论文title/DOI/canonical_key、旧审核行均精确。当前source_impact过滤排除终态，故不重复执行旧模型/实验；新READY也不启动。若派生摘要GET出现未声明写入，保留失败并检查调用范围，绝不把“修复”解释为允许清空历史。

本路径补“已有真实身份合法重审→批准→恢复”的当前原生证据。它不重新执行最初错误title/DOI纠正，不替代RV04/RV09更宽批注要求，不证明新QuickRead语义成功，不代表G11/118/最后11或科学质量自动完成。
