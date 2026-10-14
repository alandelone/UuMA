# 氢储能论文：全部原图、公式与模型科学核验

完整17页、8个图像项、7个解析公式块及全部8组编号公式已读。此前六表的完整核验对象保留；未重复增加解析表数。图4两张10×10显式编号矩阵及12个替代情景标注已核对，未估造无标签曲线坐标。

原文 CRF 两处写成 1−wacc；按其10%融资率与20年项目条件代入为负数，与正资本年金不符。只报告印刷公式问题，未推断实际程序用了该公式。公式6和8的时间与能量/功率单位、缺失图论式1、符号和部分模型约束也需完整代码厘清。

原文 FC 的2700/2600成本与50%/55%效率不一致。不同模型情景的价格阈值不能混为同一个交叉点；图4固定当前效率与表4/6同时改善效率亦不能武断判成数值错误。

## 全部图像范围

### Fig.1

- All buses H2/DC/AC/diesel, PV and diesel sources, ACload/excess sinks, battery/H2 storage,EL/FC andBoS inverter paths retained. Conceptual directed topology, not installed field performance or grid connection. Heat/O2/clean cooking excluded from actual optimization.

### Fig.2

- All twelve3Dpanels: i1DG_CAPEX/i2battery_CAPEX; ii1/2P2H2Pefficiency; iii1fuel/iii2DoD; iv1/2WACC; v1/2load shape; vi1/2seasonality. xP2H2PCAPEXfactor .2..1; ydifferentfactor/units; zoutputkWel. GreenFC/redDG/bluebattery and distinct color scales retained.
- Two regimes excludebattery orDG; conclusions not universal coexistence system. Positive nominal capacity is not energyshare. Each panel own power/coloraxis; no exact unprinted vertices/data inferred.
- GreenFC currentbatteryregime scale23..25kW conflicts bodyFC40.25; A4EL~25/FC~22 conforms broadfiguregreenrange, but exact run settings/files absent. Keep inconsistency, do not swap EL/FC silently.

### Fig.3

- All fourteen stackedbarpanels, seven eachDG andbattery regimes; legendsFC/PV/DG orBAT, supplyshare%0..100. Eachthreebarscenario group and xfactor direction retained. No individual segment exactnumbers guessed from colors.
- Efficiencyxlabels0/120/140% under changefrombasecaption appearfactor120/140% rather than+20/+40; preserve label ambiguity. DoDpositive0/25/50 versus bodydecreasingDoDto80 fromTable1base60 direction inconsistent.
- Only author printed prose shares retained asauthor reports; 44+43+12=99 can integer rounding, not automatically conservation failure. Shares dependdifferentregimes/efficiencies.

### Fig.4

- Heatmap fixed current efficiencies differs from Tables4/6 simultaneously changed efficiency scenarios; .69/3.96 versus1.53/8 not automatically a contradiction.
- Black solid boundary reference leadacid, black dashed alternativeLiion, blue dashed higherEL/FCefficiency. Callout12numbers are alternative cases, not body cells.
- At current CAPEX row, zeroFC at2.42 andpositive.10 at2.64 allow prose2.62 between gridpoints; abstract2.6 rounded,2.86separate power/share crossover not same threshold.
- Nonmonotone capacity values under parameter changes not by themselves optimizer errors; objective values and solver degeneracy unavailable.
- Both 10x10 explicitly numbered maps and all12alternative callouts, axes/units/thresholdlines/yearboxedmarkers fully transcribed. Not exact objective values or new parser tables.

### Fig.A.1

- All eleven demandprofilesF100-P0,F90-P10,F80-P20,F70-P30,F60-P40,F50-P50,F40-P60,F30-P70,F20-P80,F10-P90,F0-P100. 24hour x0:00..23:00; normalizedy0..4 (notkW); evening20hpeak rises whileovernightfalls.
- Caption10%interpolation, maintainedannualenergy statedmethod, no 264unprintedordinates manufactured. Flatprofileisvaryingnear1, notliterallyconstant. Original75/199kWpeaks separate scaledbody, representative assumption notempiricalcontinental guarantee.

### Fig.A.2

- All three base+0%,+50%,+100% seasonality curves, JAN..DEC, ykWh/kWp/day0..7; captionindex1.24→1.54. No36unprintedvalues guessed.
- Single2019MERRA2year supplies approximate index, primary explicitly admits multiyeardefinitionviolation. Artificial monthlydeviation scaling preservesannualtotal claimed, cannot validate dayweightedannualsum from raster or unprovidedseries.

### Fig.A.3

- All four axes and legends: PV/demand/diesel/excess powerkW; battery/H2SOC%; EL/FCpowerkW; batterycharge/dischargepowerkW. May1→May2one-dayxrange. H2/FC/EL/batteryflat0 notsuccessfulP2H2Pdispatch; captionallowedDG+P2H2P butoptimizerneednotusehydrogen.
- First panel PV/dieselload balance qualitative; no precise hourlyflows/loss/sum validation or annualreliability from selectedday. Legends showabsentcomponent to0 not activeplant.

### Fig.A.4

- All four axes samelegends andunits; Jan2 06h→Jan4 06h about48h, despite captionrepresentativeday. HourlystepPV/flatishdemand, batterySOC30..100approx/H2lowerSOC, ELday1/FCsecondnight, separatecharge/discharge. No exactunprintedorders inferred.
- FCmorningonlyclaim contrasted late-night activation onsecondplottedday; no run timestamp/fullfile toresolve. No dieseluse inferredsolelyfromretainedlegend; blackdieseltracezero, grayexcess maypositive. SOCshownpercent notkWhcapacity.

## 图4全部显式数值

### FC kWel

| FC/EL CAPEX USD/kWel | 1.1 | 1.32 | 1.54 | 1.76 | 1.98 | 2.2 | 2.42 | 2.64 | 2.86 | 3.08 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 260/100 | 4.08 | 6.17 | 5.91 | 5.81 | 6.06 | 6.17 | 6.00 | 5.69 | 7.18 | 8.13 |
| 520/200 | 2.86 | 5.10 | 4.14 | 4.10 | 4.53 | 4.40 | 4.75 | 4.47 | 4.50 | 4.92 |
| 780/300 | 2.10 | 4.02 | 3.21 | 3.18 | 3.07 | 3.36 | 3.75 | 3.72 | 3.69 | 4.15 |
| 1040/400 | 1.35 | 2.49 | 2.33 | 2.30 | 2.18 | 2.31 | 2.52 | 2.79 | 3.12 | 3.56 |
| 1300/500 | 0.51 | 1.33 | 1.12 | 1.34 | 1.47 | 1.73 | 1.91 | 2.10 | 2.35 | 2.87 |
| 1560/600 | 0.00 | 0.21 | 0.47 | 0.69 | 0.86 | 1.07 | 1.34 | 1.46 | 1.73 | 2.08 |
| 1820/700 | 0.00 | 0.00 | 0.00 | 0.12 | 0.32 | 0.51 | 0.75 | 1.05 | 1.36 | 1.51 |
| 2080/800 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.08 | 0.36 | 0.62 | 0.83 | 1.19 |
| 2340/900 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.08 | 0.18 | 0.47 | 0.68 |
| 2600/1000 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.10 | 0.23 | 0.36 |

### EL kWel

| FC/EL CAPEX USD/kWel | 1.1 | 1.32 | 1.54 | 1.76 | 1.98 | 2.2 | 2.42 | 2.64 | 2.86 | 3.08 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 260/100 | 25.15 | 34.69 | 38.06 | 39.47 | 41.61 | 43.19 | 37.74 | 38.56 | 42.32 | 39.98 |
| 520/200 | 18.41 | 28.28 | 27.13 | 28.39 | 30.90 | 28.26 | 28.79 | 29.05 | 30.56 | 29.16 |
| 780/300 | 13.57 | 22.00 | 20.75 | 20.67 | 19.92 | 20.36 | 22.75 | 22.45 | 22.52 | 22.80 |
| 1040/400 | 8.82 | 14.19 | 14.78 | 14.32 | 13.29 | 13.07 | 14.54 | 16.96 | 18.09 | 18.94 |
| 1300/500 | 3.36 | 7.89 | 6.68 | 8.04 | 8.66 | 9.92 | 10.45 | 11.82 | 13.27 | 15.53 |
| 1560/600 | 0.00 | 1.25 | 2.70 | 3.96 | 4.81 | 5.81 | 6.81 | 7.71 | 9.15 | 11.58 |
| 1820/700 | 0.00 | 0.00 | 0.00 | 0.53 | 1.73 | 2.51 | 3.79 | 5.38 | 6.77 | 7.47 |
| 2080/800 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.27 | 1.88 | 2.90 | 3.97 |
| 2340/900 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.29 | 0.61 | 1.95 | 2.85 |
| 2600/1000 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.31 | 0.64 | 1.09 |

## 方法与外推边界

- Single representative archetypal KenyanEldasmini-grid, PV-onlyrenewable,2019MERRA2hourlyseries, constant repeatedannualdemand/weather/SOCcyclic. Noreal multi-location sampling/multiyearout-of-sample/observed plantvalidation or statisticalconfidence. Archetype+sensitivity doesnotautomaticallyprovecontinentaltransferability.
- No shortageconstraint optimizesperfectservice inassumedsequence, notmeasuredhighestrealworldreliability; linearconstant efficiencies ignorepart-load/minrun/startup/cyclicaging; 1–2hcoldAELstartupTable2may span hourlysteps despitebodynegligibleclaim.
- No loss/CO2life-cycle/emissionsinventory evaluation;100percentrenewable/decarbonized operationalPV assumption notzeroalllifecycleemissions. O2/heat/cooking revenuesexcluded andonlyproposedfuturework.
- Fuel5percentfuturetrend appliedfixedfutureprices notwithinprojectannualescalation. Scenarioyear2030/2040/2050 illustrativeassumptions notvalidatedforecasts. Financing10percentuniformWACC andinvestment/lifetimecompression assumptions limitexternality.
- PrintedCRFnegative, power/energytimeunitmismatch, malformedgraph/balance, FCbaseline50/55percent and2700/2600USD discrepancies prevent literalformula frombeing reliable numericalgold. Actual code/solver settings/modelversion/rawinputs/run logs notincluded, cannot infer implementationactuallyusedbadprintedformula.
- Fig2/3counterfactual regimes distinct fromFig4integrated options, Fig4currentefficiency differsTable4/6futureimprovement; thresholds1.5/2.62/2.86/2.6 aredifferentcomparisons/roundings, notallcontradictions.
- BaselinebodyEL25.85/FC40.25 versusA4/figuregreenapprox23–25FC notsilentlyswapped. FigureA4captionday but48hrange. No exactunprintedpower/SOCdigitsfromraster; capacity isnotannualenergyshare.
- Policyshiftfuel-subsidies/nationalbudgetadvantages/cookinganchorloads speculative, no fiscal/behavioral/health/causalmodelvalidated inthisoptimization. Learningrates/efficiency/potentialliterature are historicalauthorstatements, not independentlycheckedlive2026facts.

[完整逐项原件、来源、算术与图表记录](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-pthp-equation-figure-and-model-science-review-v17.json)。
