# 完整科学评测：当前结果与未完成范围

DSPy ALL4优化及测试输出已冻结。完整测试范围保持10篇新论文、1286个原始块、126窗口、252个基线/优化案例、20个整篇候选；本次未训练、重新抽取或修改原评分。

原始图表公式的直接科学核验累计为27/70张表、16/99幅图、27/93个公式块；两篇已核验论文包含46条编号公式。表格共1016项，其中853个数值、132个文本项、22个破折号、6个条件标记、2个未解释斜杠及1个原文数值歧义。全部262项原始范围保留，仍有43表、83图、66公式块待核验。

本轮完成随机微电网论文全部4表、78个数值、9个公式块（23条编号公式）及5幅图。原文成本表三行被解析遗漏、百分位标题被误识别；原文自身的电池max/max边界、费用符号、油价与油箱趋势、图轴单位矛盾分别保留。误差棒表示燃料配送A/B情景的最小/最大值，不能当作置信区间。模拟研究、场地输入和未来实地测试明确区分。

这次同时检查了真正的冻结学生输出。同一结果段落中，基线5个命题的选中引用均支持陈述；优化3个命题中，2个遗漏陈述所需的后续句、1个引用了不同结论的句子。所有引用通过原source_span_ids逐字重放，问题不是位置无效，而是选中证据与陈述不匹配。结论在完整原文段落其他位置有支持，因此不认定结论全篇为假。这个段落的局部结果不能推算10篇总体准确率；原整篇模型判断与协议失败均保留，未自动改分。

全部1967条参考证据审计已完成：模型判定608完全支持、1138未建立、221部分建立；原11次失败与81条有限恢复并存。直接原文复核已有反例。这些是参考证据状态，不是学生准确率或专家金标准。

原252案例状态保持：148已审计AI比较、79来源参考未接受、11科学未解决、8原始抽取失败、6评测契约失败。40个原始来源窗口仍未接受。全126来源、252候选和20整篇对象保持原始摘要，缺失或失败不被删除。整篇目标保证原状态仍为5充分、11保证协议失败、4原目标协议失败；这不能称为20篇科学审查完成。

现有可用案例的论文等权平均差为0.017777，条件95%区间[-0.042308,0.073728]，精确符号置换p=0.59765625；全部10篇识别界限[-0.434768,0.456885]。缺失非随机且参考证据存在缺陷，当前不足以证明DSPy总体科学收益。

[本轮全部原文图表公式](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-stochastic-table-equation-figure-science-review-v12.md)、[实际学生引用比较](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/stochastic-frozen-baseline-optimized-selected-evidence-review-v12.md)、[全部262项台账](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/all262-original-visual-scientific-scope-ledger-v14.json)、[全部126来源与252案例](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/all126-windows-and252-cases-primary-reference-assurance-v13.md)。

完整科学评测仍在进行。继续剩余原文科学核验、来源/评测契约修正和20个整篇论证审查；原始结果与失败证据全部保留。
