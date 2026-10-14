# 10篇论文 · DSPy ALL4 科学评测终稿

结论：**未证实优化收益；完整科学有效性验证未通过。** 全范围的评测记录、原文核查、失败诊断及结论已汇总。终稿交付不表示全部候选通过科学验证，也不表示产生专家金标准。

固定实验：4篇训练、2篇验证、10篇全新测试；GEPA预算80、冻结四层优化与实际候选，编译读取测试论文为0。本终稿不增加模型调用、不重新训练、不重打旧分。

范围：10篇、1286原文块、126窗口、252对照案例、20整篇候选；1967参考命题、70表、99图像项、93解析公式块/125个实际印刷公式。原车棚空图像项的关联仍未确定。所有范围检查都有证据，范围覆盖不等于科学正确。

## 四层配对结果

正参考科学子集：60对窗口，10篇论文等权；另有4对零参考窗口只从本子集排除，仍保留在全252案例。统计是探索性、条件性描述，AI参考未成为专家金标准。

| 指标 | 基线 | 优化 | 差值 | Holm校正p |
|---|---:|---:|---:|---:|
| L1 原子命题覆盖 | 0.9457 | 0.9677 | +0.0219 | 1.0000 |
| 限定条件召回 | 0.9457 | 0.9677 | +0.0219 | 1.0000 |
| L2 关系宏F1 | 0.2730 | 0.2581 | -0.0149 | 1.0000 |
| L3 意图宏F1 | 0.4113 | 0.4323 | +0.0210 | 1.0000 |
| L4 块角色准确率 | 0.7647 | 0.7548 | -0.0099 | 1.0000 |
| 缺乏支持命题比例（低为好） | 0.0020 | 0.0008 | -0.0012 | 1.0000 |
| 固定综合分 | 0.6751 | 0.6859 | +0.0108 | 1.0000 |

不补分的全已解决子集为64对窗口（包含零参考窗口）：固定综合差值 +0.011531851，论文聚类95%描述性区间[-0.011325339116597853, 0.03969929228323154]，精确符号置换p=0.48046875。全部10篇/126窗口、62个未知配对的识别区间为[-0.48512385288596455, 0.49367812944542955]。缺失非随机、参考质量受限，不能据此声称全范围显著改善、无改善或等效。

旧69配对结果(+0.017776831、p=0.59765625、旧区间)实际包含5个抽取失败方记零，与旧无补分声明矛盾。本终稿保留完整旧证据，停止把它们作为当前不补分统计引用；四层全部重算，未修改任何旧候选或已评分案例。

## 全范围失败与整篇论证

| 原始案例状态 | 数量 |
|---|---:|
| AUDITED_AI_SCIENTIFIC_COMPARISON | 148 |
| SOURCE_REFERENCE_UNACCEPTED | 79 |
| AUDITED_UNRESOLVED_SCIENCE | 11 |
| ORIGINAL_EXTRACTION_CONTRACT_FAILURE | 8 |
| EVALUATION_CONTRACT_FAILURE | 6 |

40个未接受来源窗口诊断：{'SOURCE_OUTPUT_OR_BOUNDARY_CONTRACT_FAILURE': 25, 'INFERENCE_SERVICE_FAILURE': 3, 'ORIGINAL_SCIENTIFIC_NEGATIVE_OR_UNCERTAIN_RETAINED': 4, 'SOURCE_EDGE_EVALUATOR_FAILURE': 8}。完整原始错误、版本谱系、路径和摘要在JSON，未补零分，未放宽输出或定位合同。86个协议合格来源窗口也不自动成为科学正确的参考。

整篇20例原始目标保证状态：{'TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED': 11, 'ORIGINAL_TARGET_PROTOCOL_FAILURE_RETAINED': 4, 'EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE': 5}。终稿逐一保留候选四层实际输出数量、缺失原文块、实际ID恢复后的八个论证方面和论证边评审。4份无最终输出仍为缺失；其余模型判断也没有被替换或升级为独立科学认可。

## 逐篇科学结论

| 测试论文 | 原文/候选证据与判断 |
|---|---|
| Model-based techno-economic evaluation of power-to-hydrogen-to-power for the electrification of isolated African off-grid communities | 单一原型和2019气象年；印刷CRF的减号给出条件负值；燃料电池参数、TAC数字和容量单位有原文差异。缺少完整模型及运行记录，未证明实际求解器使用错误式。基线缺失20块，优化输出完整。整篇模型的COMPLETE标签不能抹去这些缺失或验证跨地区结论。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-pthp-equation-figure-and-model-science-review-v17.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\pthp-frozen-student-all-six-tables-and-scientific-body-review-v17.json) |
| URB-Solar_ An Open-Source Tool for Solar Power Prediction in Urban Areas | 单一新加坡案例与2017无雨日，原文定位为概念验证。公式条件反例和图文差异保留；没有实测预测精度、实际作者代码复现或PV电功率验证。当前作者仓库为空不证明历史仓库为空。两份SUPPORTED只能按原文忠实度解释。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-urb-equation-figure-and-model-science-review-v18.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\urb-frozen-student-all-scientific-body-review-v18.json) |
| Sun-Powered Refrigerator_ Design, Testing, and Limitations | 实验室直流源模拟PV、已预冷空箱和四个24小时温度条件；不是四次独立重复或全年户外验证。Fig5(a)与93%SOC原文数字冲突；名义电池能量和最大效率不足以证实无日照自治或全生命周期零排放。整篇SUPPORTED的验证用语过强。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-fridge-equation-figure-and-model-science-review-v18.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\fridge-frozen-student-all-scientific-body-review-v18.json) |
| Optimal sizing of a grid-independent PV_diesel_pump-hydro hybrid system__A case study in Bangladesh | 合成负荷、缺少完整GA代码/种子/重复及相同搜索范围；未证明算法全局优越。灵敏度成本方向、结论减排百分比、货币单位及配置比较存在原文或解析问题。相对5/7年回收不能当作绝对盈利。基线缺9块；优化整篇SUPPORTED不能消除全部限制。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-phs-remaining-figures-and-model-science-review-v19.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\phs-frozen-student-all-scientific-body-review-v19.json) |
| PV Sizing of a Stand Alone Solar Carport System Linked to Charging Stations and its Economic Analysis (A Case Study) | 40个12V电池按4串10并仅2200Ah@48V，按文中假设约1.105天，不能支持4天；完整计算另见原始报告。平均寿命能量39621与36621不一致；抽象657347kg/year与正文终身量冲突；援引World Bank百分比指标不建立kg/kWh因子。未取得SAM原项目和逐小时SOC。优化缺12块；两份整篇结论不构成设计验证。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-carport-equation-and-model-science-review-v20.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\carport-frozen-student-all-scientific-body-review-v20.json) |
| Assessing the effectiveness of energy policies in accelerating renewable energy-based mini-grid deployment_ A case study | 五位专家的MCDA/SWOT及历史政策资料；权重与表格标题上下文、排序及小组代表性均受限制。评分排名不能证明政策造成部署增长，不能直接外推其他国家或当前政策。两份SUPPORTED不构成独立因果研究或专家金标准。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-policy-table-figure-and-mcda-science-review-v13.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\policy-frozen-student-all-nine-table-evidence-review-v13.json) |
| Stochastic sizing of isolated rural mini-grids_ including effects of_fuel procurement and operational strategies | 五个年度Monte Carlo情景与合成PV/负荷；未模拟长期负荷增长，图误差条是配送案例min/max而非置信区间。印刷电池上下界均max以及pdf加到时间的维度解释未解决；没有作者实际求解器复现。基线缺21块，优化完整；约3%NPC/60–65%削减负荷是作者条件结果。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-stochastic-table-equation-figure-science-review-v12.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\stochastic-frozen-baseline-optimized-selected-evidence-review-v12.json) |
| Integration of Advanced Metering Infrastructure for Mini-Grid Solar PV_Systems in Off-Grid Rural Communities _SoAMIRural_ | 人口/家庭与正文/表格数字冲突；95%阈值管理准确率缺少完整验证定义和独立数据，不能视作部署可靠性。整篇baseline引用既有文献的不足不能替代本研究限制，q7保持UNRESOLVED；优化整篇评测输出缺失且候选缺12块。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-ghana-table-equation-figure-science-review-v14.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\ghana-frozen-student-all15-table-and-key-claims-review-v14.json) |
| Socio-economic and environmental impacts of rural electrification with_Solar Photovoltaic systems_ Evidence from southern Ethiopia | 观察性调查有原文F/t/Wald/OR/拟合及相关矩阵问题；未取得原始数据重新拟合。关联不支持无混杂因果结论或全国推广。两份候选原文重建完整，但两个整篇科学输出均为原始失败，不能创建SUPPORTED或把空结果算正确。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-ethiopia-table-equation-figure-statistical-science-review-v15.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\ethiopia-frozen-student-all12-table-and-key-claims-review-v15.json) |
| Multi-objective evolutionary optimization with genetic algorithm for the_design of off-grid PV-wind-battery-diesel system | 出版方确认撤稿；保留测试而不当作科学金标准。额定风机容量与年能量的条件上界、成本和参数映射问题保留；无运行文件证明零缺电或全生命周期可持续。基线缺12块，优化完整；优化整篇SUPPORTED遗漏撤稿与科学限制，不能用于部署认可。 [原文核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\complete-retracted-table-equation-figure-science-review-v16.json) · [候选核查](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\retracted-frozen-student-all-seven-parser-table-and-key-claims-review-v16.json) |

## 解释边界与复现

L1衡量参考命题覆盖；L2衡量参考关系标签宏F1；L3衡量意图标签宏F1；L4衡量块角色。它们依赖各自的参考和匹配合同，不可替代物理正确性、作者模型复现、因果有效性或部署可靠性。正文忠实但继承原文错误，与学生新增错误分别记录。小样本、单次优化、非盲AI评审和非随机缺失均限制推断。

确定性重放已核对原PDF/解析/候选/引文与位置及原始统计；这证明可追溯性，不证明科学真值。现有研究不具备独立专家金标准与全部作者原始模型/数据。若需要经金标准验证的最终准确率，须建立新的独立标注与验证实验，不能通过继续重试旧失败或在现有测试集调优得到。

[完整未舍入统计、全部252案例、126窗口、40错误、20整篇结果与证据](C:\Users\Alandelone\CodeSpace_Local\UuMA\docs\reviews\scholar-rstv4-2026-09-30\full-scientific-evaluation-2026-10-08\final-scientific-assessment-v1.json)

本次交付的终稿结论为“科学有效性验证未通过、收益未证实”，所有原始未完成/未接受标志保持原值；UuMA verification/pending_review门禁未获批准。


当前科学进度v24：以上终稿汇总不等于目标通过。独立金标准、全部有效来源与缺失评测仍未建立；goal保持active，verification门禁pending_review。所有v23以前原文证据、失败与旧统计完整保存，当前不补分统计以v24和终稿v1为准。
