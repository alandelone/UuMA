# 十篇论文 DSPy ALL4 完整科学评测报告

固定范围内的评测、原文检查、失败诊断和两轮补充复核均在本报告中逐项交付。结论是：现有证据未证明优化总体提升，也未建立完整可评分的科学基准或专家金标准。

完成评测交付与实验验证成功是两个不同结果。未通过的参考、缺失的输出、原文矛盾和未决判断全部保留；它们不补零，也不改为通过。

## 实验范围与冻结条件

10 篇新的测试论文，1286 个原文块、126 个窗口、252 个固定程序案例和 20 个整篇候选。ALL4 涵盖原子、关系、意图和角色四层。原 DSPy GEPA 优化采用 4 篇训练、2 篇验证、10 篇独立测试，预算 80、种子 20261002；测试论文不参与编译。两轮补充复核只评审既有冻结输出，未重新训练或调整学生提示。

参考及评审均包含 AI 判断。请求可追溯、验证器通过和精确评分可复算，不能单独建立科学真实性、专家认可或跨论文泛化。

## 原协议的条件性比较

原协议有 64 对满足双侧评分条件，覆盖十篇论文；其余 62 对未作数值填补。按论文等权，综合分基线 0.690895、优化 0.702427，差值 +0.011532。描述性论文组重采样 95% 区间 [-0.011325, 0.039699]；1024 种符号翻转的探索性 p=0.480469，七指标 Holm p=1.000000。

缺失不假设随机，十个论文组较少，分析为事后诊断；以上不能推断整体优越、无效或等效。历史报告中把提取失败补零的 69 对统计已经单列为历史错误，不作为当前结果。

| 指标：原协议 64 对，论文等权 | 基线 | 优化 | 差值 |
|---|---:|---:|---:|
| L1 原子覆盖 | 0.946776 | 0.969709 | +0.022933 |
| 条件召回 | 0.946776 | 0.969709 | +0.022933 |
| L2 关系 F1 | 0.317420 | 0.303026 | -0.014393 |
| L3 意图 F1 | 0.445273 | 0.468083 | +0.022810 |
| L4 角色准确率 | 0.761902 | 0.750539 | -0.011363 |
| 不受支持原子比例 | 0.001978 | 0.000745 | -0.001233 |
| 综合分 | 0.690895 | 0.702427 | +0.011532 |

另有 60 对正参考样本的分析，仅在自己的限定样本内解释；四对空参考没有从 64 对主分析中删除。两套完整统计及精确分数保存在结构化报告中。

## 两轮预先固定的补充复核

第一轮：全部六个旧评审失败窗口，两版共 12 案例，来自四篇论文。六对可评分，三对上升、三对下降；论文等权综合差值 +0.005677，描述性区间 [-0.049510, 0.060865]，探索性 p=0.75，七指标 Holm p=1。实际 209 次逻辑调用、207 个不同运行，三个被拒输出均由原验证器再次确认。

第二轮：全部九个原科学未决窗口，两版共 18 案例，来自五篇论文。实际可评分 7/9 对；所有未决和失败记录保留。原来 11 个个别未决窗口中有两个同时缺失基线输出，仍列在提取缺失组。

两轮按不同的原失败原因选入，均为非随机、事后条件性分析。它们与原 64 对分别报告；本报告没有将多个协议或队列拼成一套总体效果估计。

第二轮仅对可评分样本按论文等权：综合差值 +0.000745，描述性区间 [-0.015536, 0.016817]，探索性 p=0.875000，七指标 Holm p=1.000000。

跨声明协议共有 77/126 个不同窗口具备双侧比较，仍有 49 个未解决。这个数表示覆盖率，不表示总体准确率。

## 每篇论文的科学检查

### Model-based techno-economic evaluation of power-to-hydrogen-to-power for the electrification of isolated African off-grid communities

单一原型和2019气象年；印刷CRF的减号给出条件负值；燃料电池参数、TAC数字和容量单位有原文差异。缺少完整模型及运行记录，未证明实际求解器使用错误式。基线缺失20块，优化输出完整。整篇模型的COMPLETE标签不能抹去这些缺失或验证跨地区结论。

整篇候选的原状态：baseline：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED；optimized：ORIGINAL_TARGET_PROTOCOL_FAILURE_RETAINED。

### URB-Solar_ An Open-Source Tool for Solar Power Prediction in Urban Areas

单一新加坡案例与2017无雨日，原文定位为概念验证。公式条件反例和图文差异保留；没有实测预测精度、实际作者代码复现或PV电功率验证。当前作者仓库为空不证明历史仓库为空。两份SUPPORTED只能按原文忠实度解释。

整篇候选的原状态：baseline：EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE；optimized：EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE。

### Sun-Powered Refrigerator_ Design, Testing, and Limitations

实验室直流源模拟PV、已预冷空箱和四个24小时温度条件；不是四次独立重复或全年户外验证。Fig5(a)与93%SOC原文数字冲突；名义电池能量和最大效率不足以证实无日照自治或全生命周期零排放。整篇SUPPORTED的验证用语过强。

整篇候选的原状态：baseline：EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE；optimized：EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE。

### Optimal sizing of a grid-independent PV_diesel_pump-hydro hybrid system__A case study in Bangladesh

合成负荷、缺少完整GA代码/种子/重复及相同搜索范围；未证明算法全局优越。灵敏度成本方向、结论减排百分比、货币单位及配置比较存在原文或解析问题。相对5/7年回收不能当作绝对盈利。基线缺9块；优化整篇SUPPORTED不能消除全部限制。

整篇候选的原状态：baseline：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED；optimized：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED。

### PV Sizing of a Stand Alone Solar Carport System Linked to Charging Stations and its Economic Analysis (A Case Study)

40个12V电池按4串10并仅2200Ah@48V，按文中假设约1.105天，不能支持4天；完整计算另见原始报告。平均寿命能量39621与36621不一致；抽象657347kg/year与正文终身量冲突；援引World Bank百分比指标不建立kg/kWh因子。未取得SAM原项目和逐小时SOC。优化缺12块；两份整篇结论不构成设计验证。

整篇候选的原状态：baseline：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED；optimized：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED。

### Assessing the effectiveness of energy policies in accelerating renewable energy-based mini-grid deployment_ A case study

五位专家的MCDA/SWOT及历史政策资料；权重与表格标题上下文、排序及小组代表性均受限制。评分排名不能证明政策造成部署增长，不能直接外推其他国家或当前政策。两份SUPPORTED不构成独立因果研究或专家金标准。

整篇候选的原状态：baseline：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED；optimized：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED。

### Stochastic sizing of isolated rural mini-grids_ including effects of_fuel procurement and operational strategies

五个年度Monte Carlo情景与合成PV/负荷；未模拟长期负荷增长，图误差条是配送案例min/max而非置信区间。印刷电池上下界均max以及pdf加到时间的维度解释未解决；没有作者实际求解器复现。基线缺21块，优化完整；约3%NPC/60–65%削减负荷是作者条件结果。

整篇候选的原状态：baseline：EXISTING_RATIONALE_EVIDENCE_TARGET_ADEQUATE；optimized：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED。

### Integration of Advanced Metering Infrastructure for Mini-Grid Solar PV_Systems in Off-Grid Rural Communities _SoAMIRural_

人口/家庭与正文/表格数字冲突；95%阈值管理准确率缺少完整验证定义和独立数据，不能视作部署可靠性。整篇baseline引用既有文献的不足不能替代本研究限制，q7保持UNRESOLVED；优化整篇评测输出缺失且候选缺12块。

整篇候选的原状态：baseline：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED；optimized：ORIGINAL_TARGET_PROTOCOL_FAILURE_RETAINED。

### Socio-economic and environmental impacts of rural electrification with_Solar Photovoltaic systems_ Evidence from southern Ethiopia

观察性调查有原文F/t/Wald/OR/拟合及相关矩阵问题；未取得原始数据重新拟合。关联不支持无混杂因果结论或全国推广。两份候选原文重建完整，但两个整篇科学输出均为原始失败，不能创建SUPPORTED或把空结果算正确。

整篇候选的原状态：baseline：ORIGINAL_TARGET_PROTOCOL_FAILURE_RETAINED；optimized：ORIGINAL_TARGET_PROTOCOL_FAILURE_RETAINED。

### Multi-objective evolutionary optimization with genetic algorithm for the_design of off-grid PV-wind-battery-diesel system

出版方确认撤稿；保留测试而不当作科学金标准。额定风机容量与年能量的条件上界、成本和参数映射问题保留；无运行文件证明零缺电或全生命周期可持续。基线缺12块，优化完整；优化整篇SUPPORTED遗漏撤稿与科学限制，不能用于部署认可。

整篇候选的原状态：baseline：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED；optimized：TARGET_ASSURANCE_PROTOCOL_FAILURE_RETAINED。

## 全范围失败与证据账目

原 252 个案例的互斥状态：148 个 AI 科学比较、79 个源参考未通过、11 个科学未决、8 个原提取失败、6 个评审失败。原状态不因补充复核而覆盖；完整报告另列每个案例的新复核谱系。

原 40 个未通过源窗口：25 个输出或边界合同失败、3 个推理服务失败、4 个真实负面或未决科学判断、8 个源关系评审失败。原八个提取失败中有一个与源参考组重叠，因此剩余窗口分区中的提取缺失为七个。

20 个整篇候选：5 个既有理由和证据目标满足有限合同、11 个保障合同失败、4 个原目标失败。有限合同的满足不等于整篇科学有效。

原文证据范围：1967 条参考主张、70 张表、99 个图像范围、93 个公式块、125 个不同印刷公式、2272 个表值条目。原文忠实度与学生准确率分开；原论文的数值矛盾、限制条件、撤稿和缺少复现资料均保留。

## 复现与审计

两轮每个实际请求、响应、持久运行、原验证器的接受和拒绝、完整窗口聚合及精确有理数评分均独立回放。所有原科学检查和修正后的统计守卫也再次执行，原文、候选和提示未变。

本实验只运行一次冻结优化，未验证多随机种子稳健性；没有把作者科学结果的可复现性、抽取忠实度或 AI 参考协议当作同一个量。要建立完整可评分基准，需要后续独立修复和审核参考及缺失输出，并把它明确记录为新实验。

[全部 252 案例、20 个整篇记录及两轮完整谱系](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/final-scientific-assessment-v2.json)
[第一轮逐对结果](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/paired-scientific-evaluator-successor-v1.md)
[第二轮逐对结果及未决原因](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/paired-scientific-evaluator-successor-v2.md)
[全部既有科学与两轮复核的独立回放](C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/scientific-evaluator-successor-v2/independent-publication-and-original-science-replay-v1.json)
