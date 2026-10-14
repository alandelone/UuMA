# 10 篇论文：完整科学评测记录

当前结论：完整科学评测尚未通过，不能宣称 DSPy 优化带来总体科学质量提升。

固定范围为 10 篇互相独立的测试论文、1286 个原始源块、126 个窗口、252 个基线／优化对照案例，以及 20 个整篇候选。ALL 优化覆盖四层；编译阶段未读取测试论文。

已审计完整原文参考 83/126；已精确复核整篇原文重建 20/20。

原始抽取失败、参考失败、评测失败和科学不确定均保留在全量记录中。未合格来源不被赋予伪造的零分；缺失配对结果用可能区间表示。

以论文等权计算的全范围优化差值可识别区间：[-0.4348, 0.4569]。该区间包含缺失来源和未解决评测的全部可能值，不能据成功子集推断总体收益。

| 测试论文 | 窗口 | 已审计原文 | 已解决配对 | 未解决配对 |
|---|---:|---:|---:|---:|
| Model-based techno-economic evaluation of power-to-hydrogen-to-power for the electrification of isolated African off-grid communities | 18 | 10 | 6 | 12 |
| URB-Solar_ An Open-Source Tool for Solar Power Prediction in Urban Areas | 5 | 3 | 2 | 3 |
| Sun-Powered Refrigerator_ Design, Testing, and Limitations | 7 | 5 | 5 | 2 |
| Optimal sizing of a grid-independent PV_diesel_pump-hydro hybrid system__A case study in Bangladesh | 16 | 10 | 8 | 8 |
| PV Sizing of a Stand Alone Solar Carport System Linked to Charging Stations and its Economic Analysis (A Case Study) | 17 | 16 | 15 | 2 |
| Assessing the effectiveness of energy policies in accelerating renewable energy-based mini-grid deployment_ A case study | 13 | 8 | 6 | 7 |
| Stochastic sizing of isolated rural mini-grids_ including effects of_fuel procurement and operational strategies | 10 | 8 | 8 | 2 |
| Integration of Advanced Metering Infrastructure for Mini-Grid Solar PV_Systems in Off-Grid Rural Communities _SoAMIRural_ | 10 | 7 | 5 | 5 |
| Socio-economic and environmental impacts of rural electrification with_Solar Photovoltaic systems_ Evidence from southern Ethiopia | 17 | 9 | 7 | 10 |
| Multi-objective evolutionary optimization with genetic algorithm for the_design of off-grid PV-wind-battery-diesel system | 13 | 7 | 7 | 6 |

评分来自模型原文判断及精确计数，不是专家金标准。类别 F1 和总分采用有理数精确复算；原始浮点结果以全部合法加法顺序严格核验，旧失败记录保留。

整篇检查独立审查科学论证与实际跨窗口论证边；原文重建率是文字来源完整性指标，不能替代科学准确率。

所有案例、状态、原始失败、来源审计、评分证据、整篇审查与缺失块号详见同目录 report.json。未推进任务阶段或批准生产知识。
