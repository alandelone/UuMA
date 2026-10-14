# 埃塞俄比亚农村太阳能：完整表图公式与统计核验

已直接阅读15页原始PDF、12表、4图、5公式块，以及全部16表图裁片。完整10篇测试范围、原始失败和评分保持。

原文的ANOVA样本量与自由度不一致，F检验显著性、部分t检验、逻辑回归系数/比值比/Wald检验及拟合优度数值不自洽。表10在同样本Pearson解释下有负的三阶主子式，即使保留显示精度也无法成为合法相关矩阵；未说明的逐对缺失样本仍是需要原始数据澄清的可能条件。

条件重放只针对印出的汇总数与明确声明的常规统计定义。没有原始家庭数据、模型源码、协方差或抽样权重，不能重新拟合、推断作者实际实现，或把计算结果自动变成金标准。整数支出表与年额/比例差异可以由四舍五入解释，未将它们断言成确定错误。

## Table 1

| Variable (X_i) | Definition of the variable | Expected sign |
| --- | --- | --- |
| Gender of HH head | Dummy with D = 1 for female and D = 0 for male | ± |
| Age of HH head | Age of household-head in years | − |
| Education level | Education level of HH head in number of years of schooling | + |
| Household size | Total number of household members | − |
| Children in school | Number of children in the family attending school | + |
| Gross income | Household gross annual income in ETB | + |
| Land holding size | Household total land holding size in hectare | + |
| Price of solar PV | Total cost of a solar PV/lantern installation for the household | − |
| Kerosene consump. | Household total annual kerosene consumption in litres | − |
| Distance to grid line | Distance between household's home and grid line, minutes | + |
| Distance to market | Distance between household's home and local market, minutes | − |
| Grid connection | Dummy, D = 1 if household is connected to grid, D = 0 otherwise | − |
| Biogas ownership | Dummy, D = 1 if the household owns biogas, D = 0 otherwise | − |
| Solar PV ownership | Dummy, D = 1 if the household owns solar PV, D = 0 otherwise | + |
| Access to credit | Dummy, D = 1 if household has access to credit, D = 0 otherwise | + |
| Location/district | Dummy: taking Mirab-abaya as a reference category, D1 = 1 if household lives in Aleta-wondo and D1 = 0 otherwise; D2 = 1 if household lives in Boloso-sore and D2 = 0 otherwise; D3 = 1 if the household lives in Cheha and D3 = 0 otherwise | ± |

- All16 definitions, expected signs and reference-district dummy coding read. Negative expected signs are signs, not missing-value dash markers. Raw parser drops several signs and corrupts±. Grid-distance expected+ versus adjacentprose negative retained. Children-in-school definition differs from descriptive children<15years. PVownership also appears as predictor of same-labelled solaradoption outcome; coding/design/endogeneity not supplied.

## Table 2

| Variables | Statistic | Aleta-wondo | Boloso-sore | Cheha | Mirab-abaya | Total samples(N=605) | SE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Sample households | Num | 189 | 204 | 134 | 78 | 605 |  |
| Gender of HH head Male | Num | 162 | 181 | 108 | 58 | 509 |  |
| Gender of HH head Female | Num | 27 | 23 | 26 | 20 | 96 |  |
| Age of HH head | Mean | 50.65 | 43.95 | 49.71 | 51.53 | 48.30 | 10.92 |
| Education level of HH head | Mean | 5.86 | 4.62 | 3.97 | 3.55 | 4.73 | 3.77 |
| HH size (total) | Mean | 6.76 | 7.00 | 4.34 | 6.29 | 6.24 | 2.38 |
| Family members < 15 years | Mean | 3.21 | 3.63 | 1.62 | 1.64 | 2.80 | 1.83 |
| Total landholding in hectares, (ha) | Mean | 0.53 | 0.88 | 0.65 | 0.74 | 0.70 | 0.64 |
| Gross annual cash income in Ethiopian Birr (ETB) | Mean | 28,358 | 16,579 | 17,184 | 38,123 | 22,155 | 22,350 |
| Access to credit service | % | 55.32 | 21.57 | 22.39 | 43.59 | 35.04 |  |
| Connected to the grid | % | 40.74 | 8.82 | 29.85 | 75.64 | 32.06 |  |
| Walking distance to grid power line (minutes) | Mean | 55.8 | 68.4 | 60.8 | 41.6 | 58.0 | 56.2 |

- All12 descriptive rows and literalSE header retained, not silently renamedSD. Districtcounts andgender sum correctly. Ordinary sample-weighted means and printed precision bins replayed; if totalmean differs, additional surveyweights not supplied. No rawdata to validateSE or design-effect/cluster confidence statements. Gridtotal32.06 differsTable3printed32.07.

## Table 3

| Districts | Sample households | Grid-electrified | Solar-electrified | Non-electrified (neither grid nor solar) |
| --- | --- | --- | --- | --- |
| Aleta-wondo | 189 | 77 (40.74%) | 37 (19.58%) | 75 (39.68%) |
| Boloso-sore | 204 | 18 (8.82%) | 26 (12.75%) | 160 (78.43%) |
| Cheha | 134 | 40 (29.85%) | 63 (47.01%) | 31 (23.13%) |
| Mirab-abaya | 78 | 59 (75.64%) | 11 (14.10%) | 8 (10.25%) |
| Total | 605 | 194 (32.07%) | 137 (22.64%) | 274 (45.29%) |

- All five rows20numeric compound/scalarcells;15 count/percent pairs countedonce. Groupcounts partition605 by primarylighting, not proof exclusiveownership; footnote allows multipledevices/fuels. Smallpercent round/truncation anomalies preserved.

## Table 4

| Group | Kerosene(L/month) | Dry-cell batteries(pcs) | Candles(pcs) | Grid electricity(kWh) | Total kerosene savings(L/month) |
| --- | --- | --- | --- | --- | --- |
| Grid electrified | 0.47 | 0.50 | 4.25 | 50.06 | 3.99 (89.5%) |
| Solar electrified | 0.82 | 1.70 | 2.06 | 0.00 | 3.64 (81.6%) |
| Non-electrified | 4.46 | 4.28 | 0.42 | 0.00 | Reference |
| Mean | 2.36 | 2.48 | 2.02 | 16.01 |  |
| SE | 2.76 | 1.84 | 1.77 | 62.18 |  |

- All five rows inclfirstgridrow preserved. Monthlylitres/.pcs/kWh separate; non-electrified reference textualnot0.3.99 and3.64 differences ofdisplayedgroupmeans replayed; observationalcrossgroup contrast, not withinhousehold causalbefore-after. Means andSE do not share additive interpretation.

## Table 5

| Source of variation | SS | df | MS | F | P-value | F crit |
| --- | --- | --- | --- | --- | --- | --- |
| Between groups | 326,828.7 | 2 | 163,414.4 | 283.875 | 3.9E-17 | 3.010 |
| Within groups | 340,212.7 | 591 | 575.656 |  |  |  |
| Total | 667,041.4 | 593 |  |  |  |  |

- All11 numericcells. Caption Ns194+137+274=605; totaldf593 andwithin591 imply594 observations forusualone-way3groupANOVA. AllSS/df/MS/F replayed; printedp3.9E-17 incompatible conventionalF(2,591) evenprintedrounding. Missing11observations/ANOVAinputs not documented, no rawdatarefit.

## Table 6

| Statistic | Value |
| --- | --- |
| Multiple R | 0.69087 |
| R Square | 0.47730 |
| Adjusted R Square | 0.47117 |
| Standard Error | 0.50098 |
| Observations | 605 |

| Source | df | SS | MS | F | Significance F |
| --- | --- | --- | --- | --- | --- |
| Regression | 7 | 136.825 | 19.546 | 77.879 | 5.90E-18 |
| Residual | 597 | 149.837 | 0.250 |  |  |
| Total | 604 | 286.663 |  |  |  |

|  | Coefficients | SE | t Stat | P-value | Lower 95% | Upper 95% |
| --- | --- | --- | --- | --- | --- | --- |
| Intercept | 1.497 | 0.230 | 6.495 | 0.000 | 1.044 | 1.950 |
| Grid-electrified | -0.696*** | 0.051 | -13.777 | 0.000 | -0.795 | -0.597 |
| Solar-electrified | -0.811*** | 0.051 | -15.959 | 0.000 | -0.911 | -0.711 |
| Gender (female) | -0.095 | 0.056 | -1.684 | 0.093 | -0.205 | 0.016 |
| log(HH income) | -0.108 | 0.057 | -1.894 | 0.059 | -0.219 | 0.004 |
| Distr (Cheha) | -0.200 | 0.111 | -1.793 | 0.073 | -0.418 | 0.019 |
| Distr (Boloso) | 0.726*** | 0.124 | 5.845 | 0.000 | 0.482 | 0.970 |
| Distr (Aleta) | 0.312** | 0.098 | 3.179 | 0.012 | 0.119 | 0.504 |

- Complete statistics5cells,ANOVA10cells,and8coefficientrows48cells;63numeric. Rawparseromitsupperpanelstatistics/df andloses negativeupperCI signs. N605/7regressors/597residual/604total consistent. PrintedF77.879 and5.90E-18 incompatible usualF7,597;Aletat3.179 andp.012 incompatible t597. All8rows testedunderdeclareddecimalprecision. Prose swapsgrid−.811/solar−.696 versus tablegrid−.696/solar−.811. Responsecalledannual litres butformula lacksincome/district coefficients anddata/scale/transformation unspecified. No arbitraryoutcome rescaling.

## Table 7

| Group | Kerosene | Dry-cell battery | Candles | Grid electric | Total Lighting fuel expenses | Total cost savings |
| --- | --- | --- | --- | --- | --- | --- |
| Grid electrified | 11 | 6 | 21 | 29 | 67 | 89 (57.3%) |
| Solar electrified | 19 | 20 | 10 | 0 | 50 | 106 (68.2%) |
| Non-electrified | 103 | 51 | 2 | 0 | 156 |  |
| Mean | 54 | 30 | 10 | 9 | 103 |  |
| SE | 63 | 22 | 9 | 36 | 130 |  |

- All27numericcells incl2savings/percentcompoundscountonce. ActualprimaryMeangridelectric9 andSEcandles9,rawboth6. Solarroundedcomponents49 vsprintedtotal50; annualcosts andpercentages differdisplayed arithmetic butwhole-ETB rounding can explain, not categoricalcontradiction. SEcolumnsum notexpectedtoequalSEtotal;covariances unavailable. Footnoteexcludesmaintenance; no fullnet/lifetime savingsclaim.

## Table 8

| Group | Annual kerosene savings (L) | Annual BC emission savings (kg) | Annual CO2 emission savings (kg) |
| --- | --- | --- | --- |
| Grid electrified | 47.88 | 2.98 | 117.31 |
| Solar electrified | 43.68 | 2.72 | 107.02 |
| Mean | 46.14 | 2.88 | 113.05 |
| SE | 4.14 | 0.25 | 10.14 |

- All12 numericcells andfullgroup/Mean/SElabels retained despiteauxrowlabelomission.12×monthlydifferences produce47.88/43.68L; factor62.33g/L÷1000 and2.45kg/L replay. Estimatedavoidedkerosenecombustion, notdirectair/healthmeasurement ornetPVlife-cycleLCA. Mean/SE requireweight/rawdistributiondefinition.

## Table 9

| Problems/constraints | Frequency | Percentage (%) |
| --- | --- | --- |
| Poor quality PV/lantern and short lifespan | 65 | 47.44 |
| Lack of after-sales maintenance and training | 50 | 36.50 |
| High cost of products from licensed distributors | 48 | 35.04 |
| Unreliable supply of quality-verified products | 41 | 29.93 |
| Lack of alternative financing and credit system | 40 | 29.20 |
| Lack of adequate know-how/operational skill | 38 | 27.74 |

- Allsix constraintfrequency/percentagepairs preserved, denominator137solarowners. Openendedmultipleproblems, sumresponses282>137 expected; no mutuallyexclusivepercentage100requirement. Tinypercentageprecision/truncation differences notlargeeffect.

## Table 10

|  | Solar ownership | Distance to market | Gross income | Access to grid | Access to credit | Kerosene consump | Price of solar PV | Price of kerosene |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Solar ownership | 1.000 |  |  |  |  |  |  |  |
| Distance to market | -0.523 | 1.000 |  |  |  |  |  |  |
| Gross income | 0.642 | -0.041 | 1.000 |  |  |  |  |  |
| Access to grid | -0.446 | -0.313 | 0.333 | 1.000 |  |  |  |  |
| Access to credit | 0.291 | -0.137 | 0.182 | 0.093 | 1.000 |  |  |  |
| Kerosene consump | -0.463 | 0.262 | -0.473 | -0.254 | 0.049 | 1.000 |  |  |
| Price of solar PV | -0.839 | -0.422 | 0.316 | -0.170 | 0.341 | 0.242 | 1.000 |  |
| Price of kerosene | -0.118 | 0.547 | 0.024 | -0.071 | -0.229 | 0.145 | -0.222 | 1.000 |

- All36lowertrianglenumericcells read,28structuralblanks retainednot0. Rawlosesmanynegative signs. Declaredsame-sample Pearson interpretation fails negative3×3principalminor forSolarownership/marketdistance/PVprice evennearest.001rounding; unspecifiedpairwisemissingdata coulduseinconsistentsamples, notexcluded withoutdata. SingleBolososhowcase notnationwidecausality.

## Table 11

| Factor | Coef | SE coef | Wald Chi-square | P-value | Odds ratio | 95% CI of OR |
| --- | --- | --- | --- | --- | --- | --- |
| Gender of HH head | -0.320 | 0.376 | 1.138 | 0.278 | 0.663 | (0.215, 1.294) |
| Age of HH head | -0.004 | 0.017 | 0.232 | 0.657 | 0.994 | (0.970, 1.019) |
| Education of HH head | 0.016 | 0.036 | 0.109 | 0.672 | 1.015 | (0.943, 1.094) |
| HH size total | -0.153** | 0.077 | 4.117 | 0.046 | 0.856 | (0.738, 0.993) |
| Children in school | 0.116** | 0.099 | 5.422 | 0.029 | 1.120 | (1.029, 1.352) |
| Gross income (log) | 0.187*** | 0.092 | 11.54 | 0.002 | 2.407 | (1.911, 3.903) |
| Kerosene consumption | -0.089*** | 0.012 | 29.36 | 0.001 | 0.821 | (0.702, 0.940) |
| Price of solar PV/lantern | -0.523*** | 0.165 | 7.207 | 0.000 | 0.588 | (0.318, 0.816) |
| Distance to Grid line | -0.093 | 0.073 | 1.523 | 0.213 | 0.909 | (0.784, 1.055) |
| Distance to market | -0.091** | 0.138 | 2.101 | 0.038 | 0.691 | (0.360, 0.993) |
| Grid-connection | -2.033*** | 0.567 | 26.75 | 0.000 | 0.530 | (0.217, 0.761) |
| Access to credit service | 0.606** | 0.281 | 7.937 | 0.024 | 2.249 | (1.079, 3.754) |
| Location Aleta-wondo | -0.404 | 0.553 | 0.548 | 0.463 | 0.666 | (0.224, 1.976) |
| Location Boloso-sore | -1.178** | 0.370 | 5.720 | 0.019 | 0.308 | (0.118, 0.808) |
| Location Cheha | 0.685** | 0.351 | 2.277 | 0.015 | 1.988 | (1.812, 3.862) |
| Constant | 1.859 | 0.690 |  |  |  |  |

| Statistic | Value |
| --- | --- |
| Observations | 605 |

| Test | DF | Chi-square | P-value |
| --- | --- | --- | --- |
| Deviance | 588 | 434.72 | 1.000 |
| Pearson | 588 | 806.35 | 0.900 |
| Hosmer-Lemeshow | 8 | 15.92 | 0.633 |

| Statistic | Value |
| --- | --- |
| Deviance R-sq | 30.66% |
| Deviance R-sq(adj) | 28.83% |
| AIC | 109.50 |

- All15coef/SE/Wald/p/OR/CIrows,constant2cells,N605 andcompletebottomGoodnessfit9/Modelsummary3numericcells read. Auxiliarytable_rows omitsbottompanel, completeprimary explicitlyrestoredasreading, notnativequotechange. All15Wald/exp(coef)/p tests conditionalstandardformulas;confidenceintervalalternativeconstruction notruledout. Pearson806.35df588p.900 andHL15.92df8p.633 incompatiblechi-squareSF. Waldsignificance≠fitproof. Primarycoefs/OR/test summaries internallyinconsistent, no fitted-model correction.

## Table 12

| Explanatory variables | Kerosene (Non-electrified) | Grid-electricity (Grid-electrified) | Solar PV (Solar-electrified) |
| --- | --- | --- | --- |
| aGender of HH head (1 = Female) | 0.013 (0.144) | -0.021 (0.040) | -0.111 (0.205) |
| Age of HH head | 0.074 (0.089)** | 0.016 (0.024) | -0.059 (0.552) |
| Education level of HH head | -0.203 (0.180)** | 0.254 (0.215)** | 0.148 (0.009) |
| Total HH size | 0.179 (0.029)*** | -0.009 (0.028) | -0.177 (0.223)** |
| No of children in school | -0.025 (0.167) | 0.113 (135) | 0.282 (0.300)** |
| Gross income (ETB/year) | -2.256 (2.306)*** | 1.278 (0.600)** | 2.302 (1.190)*** |
| Landholding size in ha | -0.152 (0.170)** | 0.138 (0.107) | 0.215 (0.307)** |
| Price of solar PV/lantern | 0.642 (0.125)** | -0.019 (0.010) | -0.208 (0.004)** |
| Distance to market (town) | 0.193 (0.068)** | -0.108 (0.088) | -0.198 (0.168)*** |
| aAccess to credit facility | -0.063 (0.095) | 0.103 (0.166) | 0.225 (0.035)** |
| aAccess to electricity | -0.396 (0.401)*** | 0.670 (0.441)*** | -0.293 (0.210)*** |
| aBiogas ownership | -0.098 (0.104) | 0.018 (0.023) | -0.018 (0.009) |
| aSolar PV ownership | -0.253 (0.399)*** | -0.268 (0.143) ** | 0.711 (0.220)*** |
| bLocation: Aleta-wondo | -0.208 (0.080)** | 1.0145 (0.175)*** | -0.188 (0.205) |
| bLocation: Boloso-sore | 1.085 (0.312)*** | -0.274 (0.245)*** | -0.416 (0.110)** |
| bLocation: Cheha | -0.137 (0.243) | -0.018 (0.024) | 0.298 (0.120)** |
| Constant | -2.861 (1.674)** | -1.034 (0.776)*** | 0.992 (1.004)** |

- All51coefficient(SE)compoundcells countonce, all17rows×3outcomes;5footerstats separatelypreserved. Literal0.113(135) andprimary1.0145(0.175)*** retained; auxiliaryflat1.0155 wrong. Primaryfootnote***1%/**5%,notraw4%. Raw losesnegativegridmarket/Chehacoefs. All51standardnormalWald tests andstarscheckedwithprintedprecision; inferconventionaltestsconditionally, notauthorimplementation. Education solar.148(.009)unstarred versusproseinsignificant; several starredlargeSErows cannotmatch conventionaltwo-sidedz. Three primary-lighting exclusivegroups andsame-outcomeaccess/PVownershippredictors requireactualcoding/covariancematrix/data to validateMVP.

## 证据边界

- Cross-sectional2018householdsurvey605,137solarproducts,15purposiveinformants,24pretesthouseholds. Fourdistricts selectedwithin23renewable-activeof137ruraldistricts and12kebeleclusters; selection/exclusion55,response/designweights andclusterrobust covariance notsupplied. 95%/4% planning notalloutcomesconfidenceoraccuracyvalidation.
- Primarylightingclassificationmutuallyexclusive whilefootnoteallowsmultiplefuels/ownership. Solarownerusedinterchangeablywithadoption/use despite91.24%activeproducts. Choice/ownership/sourcegroups mustremain distinct.
- ANOVA/OLS/logit/MVPsignificance andfit identities checkedconditionalpublishedlabels. No householdrawdata/modelcode/covariancematrix to reproducefits, restoremissingN11, determinewhether responseLmonthly/annual/log transformed, or repaircoefficient/significance contradictions.
- Tables10/11/12 internalstatistic inconsistencies and primaryprose contradictions retained. StandardWaldOR=expbeta and(coef/SE)² tests declaredconditions; possiblealternativemethods notinvented. P=.000 is roundedsmallp notexactzero.
- 2018reportedfuelusage×citedemissionfactors providesestimatedcombustionsavings, notmeasuredBC/CO2 concentration orcausalhealthoutcomes. External49.9gCO2e/kWh footprintcitation withoutgeneration/lifetime cannotyieldnetannualLCAbenefit.
- Costs estimatesexcludeO&Mfootnote andcapital/lifetime/batteryreplacement/discounting;costrecovery<2.5yearssimplegrosspayback authorassertion, notfullfinancialassessment. Displayedintegerannualdifferences mayrounding; notrepairpublishedfigures.
- One-millionfunctioningorreplaceddevices scenario explicitlyassumed;nationalfuelvolume~14.81% whereasUS48/177million~27.12%. Authorabout15% bothquantity/dollars notmathematicallysame. Device-to-householdmapping/transportsupply substitution/macrocausality notobserved.
- Fig4importanceaverages and3–5hdayselfreports,twoChehabarberincomeaccounts notrandomizedhealth/incomeeffects. Crosssectionalone2018wave cannotmeasuregrowthspeed/timeorbefore-aftercausality. Policyrecommendations nottestedinterventions.

[全部原文、精确算术及条件统计重放](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-ethiopia-table-equation-figure-statistical-science-review-v15.json)。
