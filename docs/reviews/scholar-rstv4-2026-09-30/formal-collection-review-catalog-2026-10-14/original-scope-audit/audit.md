# G11 原软件组封存证据审计（只读）

结论：原 G11 的 Collection、解析复检、失效可见性、旧 Method 拒绝与零版本保护已有对应证据。身份恢复有有效历史 HTTP/controller 实跑，未找到历史或当前的原生浏览器身份批准闭环。原句未明示“本轮重新做身份修正”，因此不能由后续 preparation 自动增加重复运行要求；但是同样不能写成“本轮身份和解析两条均完成原生闭环”。父线程 current 完整回归仍在运行，本报告不提前判其结果，也不写 G11_complete=true。

## 原定义与范围

原文 ui-requirements-preservation.md:495：**真 Collection 运行可追踪；审核复检恢复；上游失效传播、旧方法拒绝运行、零版本不可进 Stage 3 / Publication**。原118矩阵只是定位，不是额外 G11 子项定义。完整 QuickRead/Skeleton/Assessment、frontier预算与无固定深度、科学复审重新批准/绑定、完整 RV03–09 批注历史、原118及最后11贯通，不得被改成该句封存的隐含通过项，也不能随 G11 软件组声明删除。

| 子项 | 已查证层级 | 内容与限制 | 证据定位 |
|---|---|---|---|
| G11-C 真 Collection 运行可追踪 | 直接证明 | 新 Collection 从原 Topic 原生开始并返回；SCREEN1次明确软件筛选夹具、LOCATE1次复用 VERIFIED 原PDF；PARSE同一job实际6次历史→GPU成功；原生详情与暂停/继续；非语言模型/科学批准。 | .tmp/scholar-g11-parallel-v1/proof/new-collection-return-original-topic.dom.txt; screen-owned-once-v2/receipt.json; locate-owned-once-v1/receipt.json; native-pause-resume-v1/receipt.json; formal-gpu-parser-recovery-2026-10-14/native-and-context/03-native-gpu-success.dom.txt |
| G11-R-parse 审核复检恢复（解析） | 直接证明 | 原始PDF页2词56–66补ref6；RECHECK_PARSE返回quality_approved=false并恢复原job；失败候选与5次失败保留；attempt6真实GPU发布parse_run_bb2661e7c11bb18dd684661073472d71 / paper_version_ef45db917629e2f892e0c7e7aac31d1a；3正文块6引用与原生固定来源读回。 | .tmp/scholar-g11-parallel-v1/proof/native-reference6-correction-and-recheck-receipt.dom.txt; formal-gpu-parser-recovery-2026-10-14/audit-and-execution/actual-gpu-success-final-audit-v3.json; native-and-context/04-native-two-parses-six-references.dom.txt; 05-native-new-parse-fixed-source.dom.txt |
| G11-R-identity 审核复检恢复（身份） | 历史直接执行＋当前间接，原生缺证 | 10/06真正HTTP＋正式JS controller已完成title/DOI精确来源修正、APPROVE_IDENTITY、VERIFIED、原LOCATE恢复及parse入队；browser_verified=false。10/13新LOCATE复用该历史VERIFIED，不是新的身份修复。原句不要求本轮重复身份，但不能把历史controller称旧浏览器点击或宣称两条当前原生闭环。当前Python后端已变，父线程正在做current回归。 | formal-review-recovery-2026-10-06/actual-identity-controller-original-receipt.json; actual-identity-parser-recovery-helper.py; actual-shipped-controller-helper.mjs; .tmp/scholar-g11-parallel-v1/actual-mineru-once-after-all-tables.json:catalog_review_actions |
| G11-U 上游失效传播 | 原历史传播＋当前原生状态/历史保持直接证明 | 原Method被替代；直接/间接Claim均STALE r2；间接稿needs_scientific_review=1且旧binding r1保留。10/13原生读取真实ID及刷新确认；没有重新批准或重放supersession。当前track_first.py摘要与10/13审计一致。 | .tmp/scholar-g11-upstream-native-prepare-v1/native-proof-v1/report.md; receipt.json; upstream-zero-final-audit-v1.json; historical-all-tables.json |
| G11-M 旧方法拒绝运行 | 直接证明（核心边界）＋原生禁用 | 当前run_experiment(old_plan)实调一次确切Method refusal，0新增run/approval/model/marker；原生旧计划按钮因缺reviewed_manifest禁用。没有声称点击禁用按钮触发Method guard，没有重复旧终态。 | .tmp/scholar-g11-upstream-native-prepare-v1/owned-copy-receipt.json; native-proof-v1/06-old-plan-native-disabled.json; upstream-zero-final-audit-v1.json |
| G11-Z 零版本不可进 Stage3 / Publication | 直接证明 | 4个真实独立零版本MS原生空成文；四合法边界HTTP422精确successful-generated-version要求；105表/文件保持。无Generate/阶段改写/伪造版本。 | .tmp/scholar-g11-upstream-native-prepare-v1/zero-version-boundary-v1/receipt.json; zero-version-native-v1; upstream-zero-final-audit-v1.json |

## 不能误称的证据

- 10/06 .tmp/scholar-review-recovery-native-v1.json 和封存 actual-identity-controller-original-receipt.json 均 browser_verified=false；所谓 native 文件名不改变 Python HTTP / Node VM controller 的执行层级。24个旧封存 artifact 摘要现在全部一致。
- 10/06 catalog_review_workflow.py=3a5d24b2…、acquisition.py=9940da32…；当前分别 aca89c29…、911f386b…，所以旧成功不单独证明当前Python身份恢复分支。正式JS controller仍与旧manifest的4160dfea…相同。9个当前关键后端摘要与10/13 upstream/zero证据相同，仅能证明这段最近证据未过期。父线程当前完整回归可补软件契约当前性，不能补不存在的浏览器点击。
- GPU封存 manifest70文件全部字节/摘要一致；新解析正是原job attempt6及原PDF，非旧parse冒充新parse。旧QuickRead/Skeleton AVAILABLE不能当新parse下游阅读成功。
- upstream原生证据是当前真实失效状态和保留历史，未重放历史替代；旧Method精确拒绝属于单独核心实调，不是禁用按钮。

## 最小原生补验建议（只有父线程判断仍需要时执行）

不需重造标题/DOI不一致、不需改SQL或重跑任何终态。现有 source_file_491d18ddee7958c95deb123a188280d5 与1827B原PDF真实可用。为保护当前成功GPU根和下游READY句柄，可用其已声明软件资料的另一个独立一致副本，禁止worker/remote gateway。先记录全部表/文件与具体非终态job，然后从正式文件详情进入身份核对：填写明确软件重审说明→“重新审核当前文件身份”→NEEDS_REVIEW→重新读取当前依据/必要时“对照新状态后继续”→不改原文/真实Catalog字段，填写明确复核说明→“复核并批准文件身份”→VERIFIED→原非终态相关任务恢复/parse幂等入队→刷新读回附加动作及原历史。

该路径是合法产品重审，不是数据库回滚。source_review.py:44只选非SUCCEEDED/SKIPPED/FAILED_TERMINAL任务，故不得执行或重放旧终态。APPROVE_IDENTITY只恢复文件可用性，scientific_approval_restored=false，原科研失效保持；不执行新READY解析或阅读任务即可补身份入口及恢复原生证据。其证明“重审已有真实身份并恢复”，不能冒称完成新的初始title/DOI错误纠正。完整RV04/09精确批注、错误重改、撤回等继续单列。

## 封存建议

可在当前回归真实通过后由父线程作**原 G11 软件组定义证据通过**的有边界声明，明确历史身份HTTP/controller＋新原生解析复检的分层证据。若目标声明是“当前 G11 所有相关界面已原生闭环”，本审计不支持；用上面最小合法路径补直接证据，不重新执行旧模型/实验/GPU。无论选择何种原软件组报告用语，原118、最后同源码11贯通、科学批准/质量保持未完成。

本代理仅文件读取、摘要核对与本新目录产出；未启动共享session writer、未读写DB、未运行测试/浏览器/服务/模型/实验；未改产品、测试、gate、HANDOFF或任何既有封存。未读私有GPU配置内容。
