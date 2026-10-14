# 已撤稿混合能源论文：完整原始表图公式核验

完成20原页、35解析视觉项、25可用裁片的阅读。7张解析表加3张图片内印刷表，共10张印刷表；后3张保留独立清单，没有扩大固定70张解析表的计数。7公式块及正文内公式共16条印刷公式。

论文仍保留在全部10篇固定测试中，作为原文忠实度与可信度压力案例。[出版方原文页面](https://link.springer.com/article/10.1007/s00500-020-05372-y)注明2024年10月23日撤稿；[官方撤稿通知](https://link.springer.com/article/10.1007/s00500-024-10235-x)元数据一致，官方预览未给出全文，未根据次级搜索结果新增撤稿原因判断。

表9正文在冻结解析中完全缺失，实际表9与图14一起存在于另一张裁片。表10部分水印遮挡数字有同一PDF文本层支持；这不等于全部像素独立清晰可读。原文文本层与辅助识别的SOC、排放和成本数字明显不同，两者均保留。

表4的风机型号与表10前两城市型号/峰值不匹配；Madurai图20风能12150 kWh/年超过表10所印0.925 kW×8760小时的8103 kWh上界，若没有未说明的额外并联容量无法成立。四方案柴油类型0却有非零排放，原文没有给出说明这些数值的其他排放边界或清单。没有将其修成零，或臆造生命周期算法。

6.87 kWh/日×365=2507.55，符合图20舍入2508，仍是小负荷模拟，不是整座城市需求。有限遗传搜索、合成逐时气象和选定四个方案不能证明全局最优、长期现实可靠性或相对电网的经济优势。

## Table 1

| System datum | Value |
| --- | --- |
| DC voltage V | 48 |
| AC voltage V | 230 |
| Power factor AC load | 0.9 |
| Maximum unmet load % | 10 (annual) |
| Control strategy | Load following |
| Load scale factor | 1.2 (weekend) |
| Solar correlation | 0.9 |
| Wind correlation | 0.82 |
| Surface roughness class | 3 |
| Anemometer height m | 10 |
| Nominal interest rate % | 4 |
| Annual inflation rate % | 3 |
| Battery autonomy days | 5 |
| System lifespan years | 25 |

- All14values/13numeric/1text retained, including distinct solar/wind correlation rows, annual10% constraint, weekend1.2 and battery5days. Surface roughness3 is a class identifier, not3m roughness length; explicit class-to-z0 conversion absent. Nominal4% and inflation3% do not themselves specify all annual discounted flows.

## Table 2

| City | Latitude °N | Longitude °E | Height m | Annual average irradiation kWh/m² (literal) | Annual average wind speed m/s |
| --- | --- | --- | --- | --- | --- |
| Dindigul | 10.3673 | 77.9803 | 268 | 5.00 | 2.03 |
| Madurai | 9.9252 | 78.1198 | 101 | 5.10 | 2.11 |
| Salem | 11.6643 | 78.1460 | 278 | 5.20 | 1.50 |
| Tiruchirappalli | 10.7905 | 78.7047 | 88 | 5.20 | 1.76 |

- All20geographical/weather numeric entries. Literal annual average irradiation kWh/m² header retained; adjoining method calls monthly average daily radiation, annual-energy versus annual-average-of-daily meaning unspecified. No silent unit correction or current-geography/weather claim. Four selected cities are modeled locations, not statistical representative sample.

## Table 4

| Datum | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Power kW at 14 m/s | 0 | 0.547 | 0.925 | 0.660 | 1.660 | 3.471 | 3.260 | 6.345 | 14.7 | 26.9 | 43.1 | 72.477 |
| Hub height m | 0 | 9 | 11 | 13 | 13 | 15 | 15 | 15 | 16 | 16 | 18 | 22 |
| Acquisition k€ | 0 | 0.945 | 2.865 | 4.255 | 4.875 | 7.555 | 9.700 | 12.056 | 14 | 22 | 34 | 59 |
| O&M k€/year | 0 | 0.05 | 0.085 | 0.085 | 0.098 | 0.151 | 0.195 | 0.224 | 0.28 | 0.44 | 0.68 | 1.18 |

- All12typecolumns including type0 zero option and48dataentries retained. Raw parser loses/misaligns type IDs and zero cells; header power at14m/s becomes1m/s in actual optimized atom. Type5power3.471 vs Table10DindigulType5peak.66; type11power72.477 vs Table10MaduraiType11peak.925. Fig5type2/5/8curves broad units match Table4 scale; table10 inconsistent selected type/peak should not be repaired by choosing another type.

## Table 5

| Datum | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Battery bank Ah | 270 | 390 | 550 | 816 | 1340 | 1940 | 2240 | 2800 | 3090 | 3360 |
| Maximum current A | 54 | 78 | 110 | 163.2 | 268 | 388 | 448 | 560 | 618 | 672 |
| Round trip efficiency % | 85 | 85 | 85 | 85 | 85 | 85 | 85 | 85 | 85 | 85 |
| O&M €/year | 1.78 | 1.65 | 2.02 | 2.98 | 4.12 | 5.78 | 6.64 | 8 | 9.08 | 10.1 |
| Acquisition € | 178 | 165 | 202 | 298 | 412 | 578 | 664 | 800 | 908 | 1010 |

- All10typecolumns50values retained. Imax=.2×Ah for10columns and annualO&M=.01×purchase exactprintedarithmetic; plausible accounting identity does not validate battery-aging algorithm. At48V type6Ah1940 gives93.12kWh andtype9Ah3090 gives148.32, roundsTable10. Body12V component/bank wiring and parallelcount unspecified; fixedparallelone versus result PV arrays requires series-count/source conventions.

## Table 8

| Datum | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- |
| Maximum current A | 45 | 60 | 60 | 70 |
| Minimum DC voltage V | 12 | 12 | 48 | 12 |
| Cost € | 528 | 643 | 206 | 800 |

- All4columns12values: minimumDC12/12/48/12 distinct from maximum48V prose; not automatically incompatible since min≠max. MaximumA/cost notproof each design usescompatible controller: no selectedcontrollerIDs/wiring/losses independently provided.

## Table 9

| Parameter | Dindigul | Madurai | Salem | Tiruchirappalli |
| --- | --- | --- | --- | --- |
| MAIN maximum generations | 15 | 15 | 15 | 15 |
| MAIN population Nm | 16 | 15 | 23 | 33 |
| Maximum nondominated set Nmax | 50 | 50 | 50 | 50 |
| MAIN crossing probability | 0.9 | 0.9 | 0.9 | 0.9 |
| MAIN mutation rate | 0.01 | 0.01 | 0.01 | 0.01 |
| MAIN combinations evaluated | 240 | 225 | 345 | 495 |
| SECONDARY maximum generations | 15 | 15 | 15 | 15 |
| SECONDARY population Nsec | 3 | 3 | 3 | 3 |
| SECONDARY crossing probability | 0.9 | 0.9 | 0.9 | 0.9 |
| SECONDARY mutation rate | 0.01 | 0.01 | 0.01 | 0.01 |
| SECONDARY combinations evaluated | 45 | 45 | 45 | 45 |

- EntireprintedTable9 restored as declared originalpage reading, raw parser caption-only and no tablecrop/auxrows. Image254 actually containsTable9+Fig14, so available originalpixel evidence exists separately. All44matrixvalues+3sharedcompoundexpressioncells47numeric entries. 7×12×10×7×6=35280;5^5=3125;product110250000. Literal11.02×10^7 is rounded notation, not exactsameinteger; nearest tie convention unspecified. main15×population=240/225/345/495;sec15×3=45. These evaluationcounts notdistinctuniquecombinations or global-optimality proof. Nm variescity; eachmaxset50 exceeds currentpopulation.

## Table 10

| Datum | Dindigul | Madurai | Salem | Tiruchirappalli |
| --- | --- | --- | --- | --- |
| PV | Type 3 | Type 2 | Type 5 | Type 5 |
| PV peak kWp | 2 | 1.14 | 2.7 | 2.16 |
| Wind turbine | Type 5 | Type 11 | Type 8 | Type 7 |
| Wind peak kW | 0.66 | 0.925 | 14.7 | 6.345 |
| Battery | Type 6 | Type 6 | Type 9 | Type 6 |
| Battery bank kWh | 93.1 | 93.1 | 148.3 | 93.1 |
| Diesel generator | Type 0 | Type 0 | Type 0 | Type 0 |
| Inverter | Type 1 | Type 1 | Type 1 | Type 1 |
| Inverter kVA | 4 | 4 | 4 | 4 |
| P1gen W | – | – | – | – |
| Pmingen W | 0 | 0 | 0 | 0 |
| Pcriticalgen W | 391.7 | 97.9 | 195.9 | 97.9 |
| SOCstopgen % | 91.2 | 77.5 | 30 | 85 |
| SOCmin % | 30 | 40 | 30 | 70 |
| Battery lifetime years | 8.6 | 9.16 | 10.69 | 9.73 |
| Total unmet load % | 0 | 0 | 0 | 0 |
| CO2 kg/year | 806 | 1619 | 1085 | 1086 |
| NPC € | 61,027.9 | 146,316.3 | 85,225.8 | 90,784.5 |

- All72bodyentries48numeric/20typecode-text/4dashes retained. Several watermark-obscured digit readings have sameoriginalPDF text-layer support but NOT fully legible pixels; retained boundary explicitly. OriginalPDF text layer77.5/30/806/1619/61027.9 versusaux77.2/80/896/1319/61021 (and damagedraw). Noauxorstudentquote repaired. No-dieseltype0 coexists annualCO2nonzero andcontrolsPcritical>0; primarymethod discussesfuelCO2 but suppliesno embodied-emissions inventory or formula explaining nonzero totals. It is an unresolved system-boundary inconsistency, notproof zero-life-cycleemissions. Missing P1 dash not0. Battery34.4/36.64/42.76/38.92%of25yrs all>34%. Four selected zeroUL modeled cases not field reliability/allfutureyears guarantee.

## Table 3

| Datum | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Nominal peak kWp | 0 | .05 | .095 | .1 | .13 | .135 | .135 |
| Short circuit A | 0 | 3.13 | 5.51 | 6.79 | 8.33 | 8.23 | 8.73 |
| O&M €/year | 0 | 1.1 | 1.73 | 1.1 | 3.35 | 1.92 | 2.47 |
| Acquisition k€ | 0 | .11 | .173 | .11 | .335 | .192 | .247 |

- Type0 absentgenerator option. kWp/k€/€/year distinguished. Raw frozen corpus has no bodytable; figure10image contains fulltable. PV resultpowers imply20/12/20/16multiplesoftype3/2/5/5 respectively but parallelone prose; no circuit/seriescount reconstruction invented.

## Table 6

| Datum | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Rated output kVA | 0 | 1.9 | 3 | 4 | 5.5 | 7 | 10 |
| O&M €/h | 0 | .14 | .17 | .18 | .22 | .24 | .27 |
| Acquisition € | 0 | 800 | 1050 | 1200 | 1300 | 1600 | 3700 |

- Type0 no-diesel placeholder. Physicaltable caption also associatedtocrop-less245 but numericbody actuallyin244; no fabricatedadditionalfile. kVA≠kW without powerfactor; AC-load.9 notautomaticallygeneratorPF.

## Table 7

| Datum | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- |
| Power kVA | 4 | 6 | 8 | 12 | 12 | 18 |
| Acquisition € | 2400 | 3200 | 4800 | 6400 | 7200 | 9600 |
| Max charging A | 96 | 131 | 192 | 262 | 288 | 393 |

- BothType4/5rated12kVA with differentcost/current, preserveddistincttypes. Type1results4kVA supported. Curveefficiency93% is methodinput, notverifiedmeasuredperformance.

## 方法与证据边界

- Knownretractedpaperretainedin10testsassource-fidelityandcredibilitystresscase,notapprovedscientificgold.
- Fourmodeledsmallload6.87kWh/day scenariosnotfourcity-scalevalidatedplants. Monthlyaverages→synthetichourlyseries,weatherseeds/multiyearrobustness/datafiles/actualiHOGAcode/modelversion/dispatchenergybalancesnotprovided.
- Sevencomponentoptions/12wind/10battery/7diesel/6inverter finiteheuristicsearch35,280components×3,125controls. No exactglobaloptimizer/exhaustiveverifiedoptimum/independentrepeated-runvariance/baselinealgorithmperformance neededforstrengthenedglobal-optimalityclaims.
- InnerGAminimizesNPCforfixedcomponentset,sopotentiallowerUL/Econtrolsettingsmaynotbeouterfront; nofullcontrol-frontproof.
- No-diesel/yearCO2notdefinedsystemboundary;Table4/10types/peakcapacityandMaduraiannualenergyhardboundconflictwithoutunreportedparallelcapacity.
- Capitalcurrency€/k€/inflation/discount/salvage/lifetimes mustretain;cost-effectiveversusgridclaimnoexternalcomparatorortest. Negativeendcostcanrecovery/salvage,notoperatingprofit.
- Excessenergyannualsum notstreetlightingreliability/timing/or25yearadditionaldemandserved; authorsmay preserved.
- PDFtextlayerhelpswatermarkdigits,notindependentexternaltruth; severalauxreadingsincorrect,cropinventorycontainswatermark/captionartifactitems andcombinedmulti-figure/tablepayloads.

[逐项原文、公式、算术与来源记录](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-retracted-table-equation-figure-science-review-v16.json)。
