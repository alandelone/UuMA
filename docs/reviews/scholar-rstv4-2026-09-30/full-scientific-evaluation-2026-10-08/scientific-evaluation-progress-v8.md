# 完整科学评测：当前证据与未完成项

**完整科学评测尚未完成；尚不能证明 DSPy ALL4 提高了科学准确性。**

固定范围保持为 10 篇新测试论文、1286 个原始块、126 个窗口、252 个冻结的基线/优化候选，以及 20 个整篇候选。DSPy 优化覆盖四层，优化时没有访问测试论文。

目前 86/126 个来源窗口通过原有模型和结构审核；148/252 个候选完成原有模型科学判断及原始回执、精确算分复核。**这些数量不能解释为已经独立证实科学正确。**

| 全部候选的当前状态 | 数量 |
|---|---:|
| AUDITED_AI_SCIENTIFIC_COMPARISON | 148 |
| SOURCE_REFERENCE_UNACCEPTED | 79 |
| AUDITED_UNRESOLVED_SCIENCE | 11 |
| ORIGINAL_EXTRACTION_CONTRACT_FAILURE | 8 |
| EVALUATION_CONTRACT_FAILURE | 6 |

已完成 20/20 个整篇重建对照。重建完整性、原始块覆盖率和科学准确性是分别检验的内容。整篇原有理由的目标核验状态：{"TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED": 11, "ORIGINAL_TARGET_PROTOCOL_FAILURE_RETAINED": 4, "EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE": 5}。

原始 PDF 视觉证据已完成全部 150 页的实际读取尝试：147 页返回符合结构要求的辅助记录，3 页保留原始格式失败。全部 262 个视觉项目（99 图、70 表、93 公式）和全部 70 张表格的审核矩阵已保存。辅助读取通过不代表全部图表的科学信息已核验。

本次逐格检查了两张完整原始表格的 47 个数值单元，保留标题、单位、范围、行列、来源引用和适用范围；其中一张表的原始解析存在费用数值错行、参数名称合并和无标签续行问题。另一张表的数值和算术可以确认，但九条原有来源证据把另一页的作者页眉当作数值证据。原始模型判断与错位证据均未被覆盖。

已对 83 个原有审核窗口的 1845 条原生来源证据建立逐条索引，其中 124 条选中的原文只有两个词或更少，作为下一步审核优先项。长度不足本身不自动判定科学错误；已直接核验的九处位置错误与其余待审核条目分别记录。

原有 AI 参考评分下，可用对照的每论文等权平均差为 0.017777，条件符号翻转检验 p=0.597656。全十篇评分差的识别区间为 [-0.434768, 0.456885]。缺失并非随机，部分来源定位仍有已确认问题；这些结果不能用于宣称整体科学收益。

当前来源修正任务：4/4 已返回，3 个通过严格原有审核；当前新增评分：8/8 已返回。有限后续流程处于 report-scientific-target-assurance-v5.py，只合并实际通过审核的来源、只评测尚未声明的固定候选。

仍需完成：剩余来源和候选的实际评测、全部来源定位及科学含义核验、全部图表公式的逐项保真检查、剩余整篇论证与原有理由的科学核验，以及基于合格证据的全范围统计解释。所有原始失败、负面判断、不确定性和测试范围持续保留。

证据：[全部 252 个候选与原有统计](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/atomic-report-v8.json)；[完整视觉审核矩阵](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-original-visual-review-matrix-v2.json)；[完整电池表逐格核验](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-battery-table-pixel-review-v3.json)；[原生定位索引与负荷表核验](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/native-primary-location-and-complete-load-table-review-v4.json)。

没有专家金标准、科学参考批准、知识库写入或阶段门批准。完整目标仍在进行。
