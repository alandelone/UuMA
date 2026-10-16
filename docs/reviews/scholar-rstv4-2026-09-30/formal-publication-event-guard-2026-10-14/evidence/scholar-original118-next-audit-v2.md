# 原118下一批只读审计 v2 — RE-11 / WF-09 / WF-10

观察时间UTC 2026-10-14T10:21:53.014Z。整体目标仍未完成，mission verification/pending_review。本任务只读当前源码和正式证据快照，未运行shell、测试、模型、worker、浏览器/服务请求，未打开运行数据库，未改产品或共享会话。RE-10非空回复/两核对归档恢复由主线程处理，此处不重复。

## 相较旧矩阵的新事实

G01–G11原软件组现均有独立报告。G11实际GPU第6次成功、Collection/身份恢复/旧Method/零版本阶段保护已封存。旧GPU失败/NVML错误只是先前观测，不能再当作当前未成功或重试理由。

RE-03/RE-05四格式原生选择、编辑/取消/确认与来源回查已在[新导入报告](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-import-read-recovery-2026-10-14/acceptance.md)实跑。AC-03真实Bib本地读入、5,000,001bytes拒绝已证，实际慢读/取消恢复仍待补。CA-05列设置/宽度/横滚、CA-06文字/数值/日期/嵌套逻辑、CA-07真实1197可见与分页同值稳定性均有[新目录证据](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-collection-review-catalog-2026-10-14/acceptance.md)。旧矩阵21/96等覆盖分类不能沿用为现在进度。

本轮新静态发现：PUBLISHED事件入口直接推进PUBLICATION，未走/stage的正式版本及科学复核守卫；G11的/stage 422没有覆盖这个不同入口。这是静态可达缺口，尚未动态复现。

## RE-11

原句逐字：

> 待处理→已决定回应→修改中→待核对→已处理；作者确认才完成；失败或未解决不能自动已处理

来源：[原118第451行](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md:451)。交互契约说这是建议处理流，已处理必须作者认可；不要据箭头新增“每条意见必须先改正文”的强制条件，理由不修改仍须合法。

| 位置 | 当前实际实现 |
|---|---|
| [StudioResponseReview](C:/Users/Alandelone/CodeSpace_Local/writing-studio/components/studio-response-review.tsx:182)，182–194 | 决定与完整回复保存，PENDING/DECIDED/MODIFYING/VERIFY可选，RESOLVED选项disabled，核对前flush真实回复。 |
| [ResponseCheckDialog](C:/Users/Alandelone/CodeSpace_Local/writing-studio/components/studio-response-review.tsx:214)，223–266 | 未生成当前revision则stale；MODIFIED与EXPLAINED_NO_CHANGE两选项。后者不要求diff，要求非空理由/回复与作者ack，提交claims=[]。 |
| [StudioService.update_comment](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio.py:1553)，1575–1584 | 内容CAS，未核对/过期不能用status=RESOLVED快捷完成；完成后改回复使VERIFY并advance核对状态。 |
| [validate_claims](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio_response_checks.py:100)，103–148 | 必须ack、非空理由/回复、当前真实生成revision；无修改claims必须为空；修改必须精确UTF16、真实GENERATED_TEXT_CHANGED与最终页行/词框，逆转/未知/保留不算完成。 |
| [record](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio_response_checks.py:151)，153–172 | request幂等，context/current state复核后追加核对，才设置RESOLVED；没有LLM或科学批准。 |

已有直接证据：[G09 final-native receipt](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-source-round-reply-2026-10-13/evidence/native/final-native-audited-v1/receipt.json)及[原始持久表快照](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-source-round-reply-2026-10-13/evidence/native/final-native-audited-v1/all-tables.json)实际有2条核对，outcome均MODIFIED。第一次完成、回复编辑后STALE、重新核对CURRENT和刷新保持已证；205原意见PENDING未假完成。早期source-progress也证r40/旧v4时两种选择均不能确认。

已有软件测试：[no-change理由及不可改历史导出](C:/Users/Alandelone/CodeSpace_Local/RSTV4/tests/test_studio_response_checks.py:145)，[RESOLVED快捷完成拒绝](C:/Users/Alandelone/CodeSpace_Local/RSTV4/tests/test_studio_response_checks.py:35)。这是现存实现/历史回归范围，本任务没有重跑，不把API测试当原生操作。

**精确未证部分**：正式报告及G09原生表中没有成功EXPLAINED_NO_CHANGE原生确认。界面radio/单测不能替代该分支。还可补真实意见状态/空理由/不ack不能完成的原生证据。作者是否列全自然语言声明和理由是否科学成立仍由真人审阅；不要求软件自动语义批准。

**最小独立推进**：新owned v5/r62副本的新第3轮baseline v5添加一条明确软件意见，避开RE-10的A206。记录PENDING→DECIDED→VERIFY、非空决定和不修改的完整软件理由/回复。核对v5→v5无diff，MODIFIED无依据不能完成，切EXPLAINED_NO_CHANGE+ack后一次确认，刷新CURRENT/RESOLVED、claims=[]，作者文档/r62/版本/模型/作业/所有原意见保持。零Generate/零模型/不下载，可同时补RE-13理由不改。MODIFYING不是无修改意见的新增强制步骤。

## WF-09

原句逐字：

> Stage 4 按目标期刊／会议定稿、产出 LaTeX / BibTeX / PDF / 投稿包；记录投稿事件；作者决定终稿与提交

来源：[原118第432行](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md:432)。支持契约：[六阶段](C:/Users/Alandelone/CodeSpace_Local/RSTV4/docs/paper-writing-backend-design.md:40)和[通用/目标模板](C:/Users/Alandelone/CodeSpace_Local/RSTV4/docs/paper-writing-backend-design.md:330)。Stage4按最终期刊要求定稿，不擅加所有期刊样式库或把全部行政字段阻塞Drafting。

| 位置 | 实现和边界 |
|---|---|
| [ReadingView](C:/Users/Alandelone/CodeSpace_Local/writing-studio/components/studio-workspace.tsx:2951)，2951–2986 | Stage3进入定稿、Stage4开始返修、Stage4/5出版归档，仍同Studio六阶段。 |
| [SubmissionPanel](C:/Users/Alandelone/CodeSpace_Local/writing-studio/components/studio-workspace.tsx:3042)，3057–3096 | venue/round/status/detail，SUBMITTED至PUBLISHED七事件，作者点击“＋记录”，显示历史。 |
| [studioApi.recordSubmission](C:/Users/Alandelone/CodeSpace_Local/writing-studio/lib/studio-api.ts:249)→[HTTP入口](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio_api.py:540) | POST /api/manuscripts/{id}/submission-events，JSON venue/round_number/status/detail。本地登记，不向外部期刊提交。 |
| [set_stage](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio.py:735)，743–791及[_require_successful_version](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio.py:795) | CAS/允许阶段/成功Generate，Stage4及Publication要求当前作者/科学binding且无needs_scientific_review。 |
| [record_submission_event](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio.py:1405)，1405–1432→[TrackFirstService.record_submission](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/track_first.py:891) | 与set_stage不一致：只查稿件存在就先插事件，PUBLISHED另直接UPDATE workflow_stage=PUBLICATION。 |

已有实际产物：[六素材PDF/25文件包](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-generated-materials-2026-10-09/acceptance.md)有原生定稿/编译/下载/三页目视；[109表快照](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/formal-generated-materials-2026-10-09/evidence/scholar-generated-assets-native-audit-v3/all109tables-after-native.json)素材稿FINALIZATION_SUBMISSION、submission_events=[]。G09原生16文件回复包/下载/两核对已证，但其submission_events亦[]、稿件仍WHOLE_PAPER_REVIEW。“包已交付”不能替代“作者记录投稿/提交终稿”。

**精确未证部分**：Stage4目标期刊/固定终稿明确决定→本地SUBMITTED事件→刷新/轮次历史保留。现事件只存稿件、venue、round、status、detail、time，无显式generated_version_id/template_version；不可用后来active版本倒推早期投稿使用哪版，需明确原版本绑定如何由真实记录承担。

**静态新缺口，未发请求**：任意存在的零版本PLANNING稿可达PUBLISHED事件入口；record_submission_event没调用正式版本/科学复核守卫，直接晋升PUBLICATION，也不查同venue/round的ACCEPTED。与WF09防无正式稿件切阶段、WF10接收后Stage6不一致。最小负例在全新无版本owned稿拒绝该事件，event/history/DB不变；主线程统一语义守卫/事务，不能先commit PUBLISHED再因校验失败留下事件。G11的/stage负例保持，仅补此新入口，无需重跑全部旧组。

## WF-10

原句逐字：

> Revision 生成仍在 Revision，不重置首次写作；Stage 6 接收后终稿／校样／发表／归档，以完成事件结束，不加第七阶段

来源：[原118第433行](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md:433)。[Stage6契约](C:/Users/Alandelone/CodeSpace_Local/RSTV4/docs/paper-writing-backend-design.md:42)，[Stage5生成约定](C:/Users/Alandelone/CodeSpace_Local/RSTV4/docs/paper-writing-backend-design.md:214)。

| 子项 | 实现/已有证据 | 仍缺证据或风险 |
|---|---|---|
| Revision生成不重置 | [_generate](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/studio.py:2169)，2169–2177保留当前REVISION等stage；[现软件测试](C:/Users/Alandelone/CodeSpace_Local/RSTV4/tests/test_writing_studio.py:298)，353–357生成r2后断言REVISION。 | G09原生v5仍Stage3，不是原生Revision生成证明。先查旧真实job和前后stage持久流水，缺时才声明一次新的bounded软件触发，不重跑原job或旧模型。 |
| 接收后Stage6 | set_stage允许Stage4/5→PUBLICATION，PUBLISHED事件也直接晋升。 | 两入口未见ACCEPTED前提；“出版归档”按钮直接onStage PUBLICATION，需与原接收/版本契约一致。 |
| 终稿/校样归档 | [文件入口](C:/Users/Alandelone/CodeSpace_Local/writing-studio/components/studio-workspace.tsx:3098)，3098–3115允许PDF/DOCX/TEX/TXT，调用[onArchiveFile](C:/Users/Alandelone/CodeSpace_Local/writing-studio/components/studio-workspace.tsx:2142)上传为DOCUMENT并列表。 | 没有本地真实校样/终稿登记、SHA/所属稿件/固定版本/刷新回查的完整正式原生证据；入口不是完成。 |
| 发表/归档完成事件 | [SubmissionStatus](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/models.py:91)有SUBMITTED/UNDER_REVIEW/REVISION_REQUESTED/REJECTED/WITHDRAWN/ACCEPTED/PUBLISHED；detail可写稿号/DOI/校样说明。[事件schema](C:/Users/Alandelone/CodeSpace_Local/RSTV4/src/rstv4/database.py:547)只event/MS/venue/round/status/detail/time。 | 未见接收→校样→发布→归档完成的权威链/标记；需明确PUBLISHED是否承担最终完成及与固定终稿/校样相连，不能只stage==PUBLICATION冒充全部完成。不新增第七阶段。 |

[既有publication测试](C:/Users/Alandelone/CodeSpace_Local/RSTV4/tests/test_writing_studio.py:369)，369–377仅成功生成/包后直接record PUBLISHED，断言事件和stage；没有ACCEPTED、校样文件、归档完成或零版本事件拒绝。它通过属于原有效软件证据，不能扩张成完整WF10；无需弱化旧断言，应补缺的负例/完成链。

**最小独立顺序**：先统一投稿事件与阶段的正式版本/有效科学依据守卫、接收条件；另一个owned v5/r62副本由作者明确Stage4/软件期刊/固定终稿，记录本地SUBMITTED→UNDER_REVIEW→REVISION_REQUESTED。Stage5优先复用旧真实保持证据，确实缺原生触发才新声明一次bounded软件生成。ACCEPTED→Stage6→真实软件终稿/校样文件→PUBLISHED/可追归档完成→刷新history/文件hash/稳定六阶段。事件详情明确“软件演练，无外部投稿/接收/发表”，不外发、不伪造现实期刊接受、不当科学批准。

## 分工与界限

1. 主线程RE-10继续，此处没有归档/恢复操作。
2. RE11/13 no-change可零模型/零Gen独立原生补验，用新意见。
3. WF09/10先处理新事件绕过，再真实事件/文件证据，不使用有缺口路径制造绿灯。
4. 更新118采用新G11/四格式/目录证据，不重复GPU、旧模型、已完成测试/下载。最终同源码11贯通仍独立待验。

本次一次初稿构造发生JavaScript语法错误，发生在文件写入前；确认目标不存在后改为直接模板文本保存，未执行任何产品动作或改变要求。

## 读取时源码摘要

- writing-studio/components/studio-response-review.tsx SHA256 af03a27fe60c6c43e98287d95331f5e300b8e30da4ccce958a9d40d77c35d060
- writing-studio/components/studio-workspace.tsx SHA256 425018e7e17170eb70267917504b8781a7d69252fc8edeaa1308af60fcff33fd
- writing-studio/lib/studio-api.ts SHA256 d7ca79b54b158b5c1312a925a6678d985fd48c498b0ca4941fa9bfad1e1b81d5
- RSTV4/src/rstv4/studio_response_checks.py SHA256 6da7be09aa232f61983d8c63cc828da345c215b7f4c013655e2d461516af7813
- RSTV4/src/rstv4/studio.py SHA256 73e31e84d3fadb51a46ec9c50e44e0763cccde98be6cac519a2db480923e6797
- RSTV4/src/rstv4/studio_api.py SHA256 5a62bab6568aaecbe61b10602d2d15a936bb19ae5a35cfaa6639093c7e8d3e36
- RSTV4/src/rstv4/track_first.py SHA256 5e66d9590a50d3b3335dbb52557a68b489a1e4c794c12cc584534a311e726143
- RSTV4/src/rstv4/models.py SHA256 0dfbc9a1c927cec7f5dd9599032ce2e32c4909519660cb0d548cd63550e4fce6
- formal-source-round-reply-2026-10-13/acceptance.md SHA256 37ddf37f0c733d4007495aabcb3ea45b969c1f2063ebc43b0099c60c9ffa929f
- formal-import-read-recovery-2026-10-14/acceptance.md SHA256 f554f3a1fcbbcd8a2f9998a4f1f0a46b93ae38c8dec35b10aa9bce78342d478e
- formal-collection-review-catalog-2026-10-14/acceptance.md SHA256 b4e32093ac71cf3cd7ddfafcbe21b7173744747398a8d86e2bf2bcf96875dbe0
- formal-response-review-2026-10-04/acceptance.md SHA256 47d55531dae20d1963530609b32134933a77c6786d65eeff6b65c8805cdc091f

这些是读取时快照；主线程随后修改源码时行号/SHA需按新向量复核。本文不宣称新测试通过、不批准gate或科学结果。
