# 冻结学生输出：优化前后引用支持的直接比较

原PDF第18页、同一结果段落b98的全部5个基线命题和3个优化命题逐项核验。引用通过原始source_span_ids重新解析，并与冻结quote逐字一致；科学支持与位置正确分别检查。此结果仅适用于该段落，不能推算整篇或全部10篇准确率。

| 程序 | 命题 | 选中证据支持 | 发现 |
| --- | --- | --- | --- |
| baseline | a1 | FULL_SELECTED_TEXT_SUPPORT | All stated sensitivity qualifications appear in the selected sentence. |
| baseline | a2 | FULL_SELECTED_TEXT_SUPPORT | Selected sentence explicitly reports the3% extreme case. |
| baseline | a3 | FULL_SELECTED_TEXT_SUPPORT | Selected sentence explicitly statesCAPEX and supply continuity. |
| baseline | a4 | FULL_SELECTED_TEXT_SUPPORT | Selected sentence states60–65% on average. |
| baseline | a5 | FULL_SELECTED_TEXT_SUPPORT | Selected sentence statesNPC sensitivity and negligible delivery-time effect. |
| optimized | a1 | PARTIAL_SELECTED_TEXT_SUPPORT | The selected IDss1/s2 are only the preceding sensitivity sentence. The3% assertion is in unselecteds3. |
| optimized | a2 | PARTIAL_SELECTED_TEXT_SUPPORT | Selecteds3/s4 supportNPC decrease/CAPEX/continuity but not the60–65% assertion, which is unselecteds5. |
| optimized | a3 | NOT_ESTABLISHED_BY_SELECTED_TEXT | Selecteds5 states only60–65% curtailment reduction. The full sensitivity statement is unselecteds6. |

优化输出的前两个命题分别把未选中的3%和60–65%结论并入陈述；第三个关于NPC敏感性的命题却只引用60–65%削减句。这些结论在完整原文段落中有其他支持，因此本次认定的是引用支持不足或错配，不能认定结论在全篇为假。基线5个命题均有相应选中句支持。

优化候选重建111/111解析块；基线保留原有90/111、缺失21块。完整解析覆盖不能证明完整原文覆盖：成本表原解析已经遗漏逆变器、柴油机、油箱三行。原文内部矛盾与学生引用错误分别保留；原始科学评分和整篇协议失败均未替换。

[完整逐命题原始证据、跨度和候选摘要](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/stochastic-frozen-baseline-optimized-selected-evidence-review-v12.json)。科学总评测与DSPy收益证明仍未完成。
