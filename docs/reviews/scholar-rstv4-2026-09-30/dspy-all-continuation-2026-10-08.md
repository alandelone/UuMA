# DSPy ALL：10 篇论文续跑报告

更新时间：2026-10-08T11:04:40.976178+08:00

四个组件的 GEPA ALL 优化已完成并冻结。10 篇独立测试论文的基线与优化版输出已存在；全文科学评分仍未完成，暂不能认定优化带来收益。

固定测试范围：10 篇、1286 个源块、126 个完整窗口、252 个基线／优化对照案例。原始抽取失败 8 个，保留在总范围中。

当前完整原文参考窗口审计：33/126；分块评分的调用与评分复算审计：9 个。完整论文科学对照：0/20。

评分器修正已核验：旧评分器把 7 条实际匹配的陈述误判为缺失；新分块评分与先前独立原文复核逐条一致。旧判断和分数保留，不作为整体收益证据。

专用模型路由已保留原持久状态恢复。4 个未写回窗口沿原任务恢复；47 个连接拒绝窗口采用独立恢复记录、原调用缓存及原标识。科学负例、科学不确定项和已耗尽的协议失败不混入连接恢复。

| 测试论文 | 页数 | 完整窗口 | 已审计原文窗口 | 已审计分块评分 | 原抽取失败 |
|---|---:|---:|---:|---:|---:|
| Model-based techno-economic evaluation of power-to-hydrogen-to-power for the electrification of isolated African off-grid communities | 17 | 18 | 7 | 7 | 2 |
| URB-Solar_ An Open-Source Tool for Solar Power Prediction in Urban Areas | 6 | 5 | 1 | 0 | 0 |
| Sun-Powered Refrigerator_ Design, Testing, and Limitations | 7 | 7 | 4 | 0 | 0 |
| Optimal sizing of a grid-independent PV_diesel_pump-hydro hybrid system__A case study in Bangladesh | 17 | 16 | 5 | 2 | 1 |
| PV Sizing of a Stand Alone Solar Carport System Linked to Charging Stations and its Economic Analysis (A Case Study) | 8 | 17 | 10 | 0 | 1 |
| Assessing the effectiveness of energy policies in accelerating renewable energy-based mini-grid deployment_ A case study | 15 | 13 | 6 | 0 | 0 |
| Stochastic sizing of isolated rural mini-grids_ including effects of_fuel procurement and operational strategies | 27 | 10 | 0 | 0 | 2 |
| Integration of Advanced Metering Infrastructure for Mini-Grid Solar PV_Systems in Off-Grid Rural Communities _SoAMIRural_ | 18 | 10 | 0 | 0 | 1 |
| Socio-economic and environmental impacts of rural electrification with_Solar Photovoltaic systems_ Evidence from southern Ethiopia | 15 | 17 | 0 | 0 | 0 |
| Multi-objective evolutionary optimization with genetic algorithm for the_design of off-grid PV-wind-battery-diesel system | 20 | 13 | 0 | 0 | 1 |

仍需完成：剩余原文参考窗口的科学核验、全部 252 个科学对照评分、20 个整篇评测及重建／最终独立审计。未完成、来源不确定和模型失败项均显式保留；不以局部窗口成绩推断全文质量。

优化设置：80 次指标预算，ALL 同时覆盖 layer1–layer4；编译阶段访问测试论文数为 0。

冻结提示词 SHA：`3dccecc127b9a3bab467775c074f9400f36516b015a6260836443473a0505db5`

[DSPy 官方 ALL 选择器说明](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/GEPA/GEPA_Advanced.md)

[当前机器可核验记录](C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/dspy-all-continuation-current-20261008.json)

状态：进行中；没有科学知识应用、生产发布或阶段审批。
