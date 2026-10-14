整篇评测对象修正：旧整篇计数仅保留为历史审核证据。当前明确评测对象为固定提取候选，覆盖全部 20 个案例。

当前整篇状态：{"AUDITED_EXPLICIT_FROZEN_CANDIDATE_SCIENTIFIC_TARGET": 16, "TARGET_SCIENCE_PROTOCOL_FAILURE": 4}

原文完整性及出版状态：150 页中 14 页未关联解析窗口；至少一页含科学图表。测试集一篇论文已由出版方确认撤稿。十篇测试范围保持不变，完整科学评测与优化收益仍未确认。详见 source-quality-and-visual-coverage-v1.md。

# 10 篇论文：DSPy ALL 科学评测

当前结论：完整科学评测仍未完成，优化收益尚未证明。

固定范围：10 篇测试论文、1286 个原文块、126 个窗口、252 个基线/优化对照案例、20 份整篇候选。四层 DSPy GEPA 优化结果和原始候选保持冻结；编译阶段读取测试论文为 0。

合格原文参考：63/126。经审计的科学对照：106/252；另有 9 个已审计但科学判断不确定。整篇科学论证审计：11/20。

原文重建审计：20/20。这表示已检查全部候选，并不表示所有原文都完整重建。

| 案例状态 | 数量 |
|---|---:|
| AUDITED_AI_SCIENTIFIC_COMPARISON | 106 |
| SOURCE_REFERENCE_UNACCEPTED | 124 |
| AUDITED_UNRESOLVED_SCIENCE | 9 |
| ORIGINAL_EXTRACTION_CONTRACT_FAILURE | 8 |
| EVALUATION_CONTRACT_FAILURE | 5 |

全范围论文等权优化差值识别区间：[-0.6052, 0.6279]。缺失参考或评测没有被补为零分。

| 论文 | 窗口 | 合格参考 | 已解决成对窗口 |
|---|---:|---:|---:|
| Model-based techno-economic evaluation of power-to-hydrogen-to-power for the electrification of isolated African off-grid communities | 18 | 9 | 5 |
| URB-Solar_ An Open-Source Tool for Solar Power Prediction in Urban Areas | 5 | 2 | 1 |
| Sun-Powered Refrigerator_ Design, Testing, and Limitations | 7 | 4 | 4 |
| Optimal sizing of a grid-independent PV_diesel_pump-hydro hybrid system__A case study in Bangladesh | 16 | 7 | 6 |
| PV Sizing of a Stand Alone Solar Carport System Linked to Charging Stations and its Economic Analysis (A Case Study) | 17 | 14 | 12 |
| Assessing the effectiveness of energy policies in accelerating renewable energy-based mini-grid deployment_ A case study | 13 | 6 | 4 |
| Stochastic sizing of isolated rural mini-grids_ including effects of_fuel procurement and operational strategies | 10 | 5 | 4 |
| Integration of Advanced Metering Infrastructure for Mini-Grid Solar PV_Systems in Off-Grid Rural Communities _SoAMIRural_ | 10 | 4 | 3 |
| Socio-economic and environmental impacts of rural electrification with_Solar Photovoltaic systems_ Evidence from southern Ethiopia | 17 | 6 | 4 |
| Multi-objective evolutionary optimization with genetic algorithm for the_design of off-grid PV-wind-battery-diesel system | 13 | 6 | 6 |

| 论文编号 | 程序 | 整篇评测状态 | 科学判断 |
|---|---|---|---|
| paper_95eebae164cc42fd6005 | baseline | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_95eebae164cc42fd6005 | optimized | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_964b88669cfe422e7aef | baseline | AUDITED | SUPPORTED |
| paper_964b88669cfe422e7aef | optimized | AUDITED | SUPPORTED |
| paper_ad7ea2de394ae32d2ed2 | baseline | AUDITED | SUPPORTED |
| paper_ad7ea2de394ae32d2ed2 | optimized | AUDITED | SUPPORTED |
| paper_19f55daa7f17ede2858b | baseline | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_19f55daa7f17ede2858b | optimized | AUDITED | SUPPORTED |
| paper_b637a4adf835d6357900 | baseline | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_b637a4adf835d6357900 | optimized | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_2f81cb801401904d4767 | baseline | AUDITED | SUPPORTED |
| paper_2f81cb801401904d4767 | optimized | AUDITED | SUPPORTED |
| paper_6dc9f2bdd81d9dcf4a46 | baseline | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_6dc9f2bdd81d9dcf4a46 | optimized | AUDITED | SUPPORTED |
| paper_603603415f45919cbdc8 | baseline | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_603603415f45919cbdc8 | optimized | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_fb88f52bf6ea0323e952 | baseline | AUDITED | SUPPORTED |
| paper_fb88f52bf6ea0323e952 | optimized | AUDITED | SUPPORTED |
| paper_75abf75ded7b6df0c2b5 | baseline | WHOLE_PAPER_EVALUATION_PROTOCOL_FAILURE | PENDING_OR_PROTOCOL_FAILURE |
| paper_75abf75ded7b6df0c2b5 | optimized | AUDITED | SUPPORTED |

评测使用真实模型原文标注与独立复核，不是专家金标准。不支持和不确定判断保留；原始失败记录和模型调用证据可追溯。成功子集的统计不能推广到全部论文。

整篇精简输入已对 10 篇原文和 20 份候选验证逐字段可还原；仅删除重复表示，科学内容保持完整。

[全部案例、审计路径和统计证据](current-report.json)

更新时间：2026-10-09T05:02:41.721433+00:00
