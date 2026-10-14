# 冻结学生输出：政策论文全部9表的证据核验

完整覆盖18个表格候选单元、全部56个实际命题（基线20、优化36），并保留基线专家表的空命题集。每个引用由原source_span_ids逐字解析，原命题、quote和评分均不修改。原表格标题与列单位明确作为行值解释上下文；跨行错配与未选中信息另列。

| 程序 | 表格内实际命题 | 证据情况 |
| --- | --- | --- |
| baseline | 20 | {"QUOTED_CONTENT_SUPPORTED_WITH_DECLARED_PRIMARY_TABLE_HEADERS": 15, "RAW_SELECTED_TEXT_PARTIAL_PRIMARY_ROW_SUPPORTS": 5} |
| optimized | 36 | {"QUOTED_CONTENT_SUPPORTED_WITH_DECLARED_PRIMARY_TABLE_HEADERS": 25, "RAW_SELECTED_TEXT_PARTIAL_PRIMARY_ROW_SUPPORTS": 7, "RAW_SELECTED_TEXT_INHERITED_ROW_MISASSOCIATION": 2, "RAW_ROW_CONTINUATION_REQUIRES_ORIGINAL_ROW_CONTEXT": 1, "RAW_SELECTED_TEXT_PARTIAL_PRIMARY_TABLE_CONTEXT_SUPPORTS": 1} |

优化输出实际增加附录7行49个分值与专家表信息，说明该范围内具体性提高；同时继承专家行错配和项目状态错行，并存在引用跨度遗漏。两者都无法恢复解析漏掉的GEDAP项目成本。泛化的表格标签命题不证明完整表格科学覆盖。局部计数不能推算总体准确率或DSPy收益。

明确例子：专家2描述引用的550字符跨度在“Murdoch University,”结束，未包含26年及WesternAustralia；专家3的policy analysis来自原解析把专家2尾部移错行；SWOT命题引用的标题不包含SREP/REMP名称。实际原文上下文与选中解析证据分别记录。

- Both143/143rawblock reconstructions include allnine rawtables, but raw reconstruction cannot recover missing primaryGEDAPcost210.55, shifted cells or unseen plot numbers.
- OptimizedAppendixA includes all7score rows/49numbers; baselineAppendixA has only a genericcaption proposition. This is a bounded actual specificity gain, not proof of overall scientific improvement.
- BaselineTable6has zero atoms; optimizedTable6has7atoms with five expert descriptions and a separate26year statement, including exact-selected-text gaps and inherited row misassociation. The empty baseline is retained, not vacuously scored correct.
- BothTable4/5/7are genericheader/caption propositions and do not enumerate seven criteria/directions/policies. BothSWOTtable propositions do not enumerate20primary statements. Correct summary labels do not demonstrate full quantitative/conditional coverage.
- BothGEDAPatoms omit the primary210.55millionUSD absent from parser. They do not falsely assertzero cost. Optimized next-projectinprogress qualifier inherits precedingSREPstatus text.
- The primary score reproducibility gap belongs to the source publication. Faithful student reporting of73/68 or the author ranking elsewhere cannot count as independently validated calculation.

[全部实际命题、空单元及原始引用](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/policy-frozen-student-all-nine-table-evidence-review-v13.json)。原始科学判断和失败不被替换。
