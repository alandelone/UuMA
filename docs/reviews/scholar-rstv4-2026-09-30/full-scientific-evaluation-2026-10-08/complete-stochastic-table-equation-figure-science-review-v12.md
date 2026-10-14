# 随机微电网论文：全部图表、公式的原文科学核验

本次完整核验该论文4张表、78个数值项、9个公式块（23条编号子公式）和5幅图。原始10篇测试论文、126窗口、252组比较、20个整篇候选保持不变。数值转录是独立阅读记录，原解析文本与原评测记录均保留；未创建专家金标准或自动改分。

## 表1：原PDF第17页

| Case | t_P + t_T (days) | 50th percentile (days) | 90th percentile (days) |
| --- | --- | --- | --- |
| A | 1 | 1.5 | 3 |
| B | 2 | 3 | 6 |

- The fixed procurement-plus-transport time, median and 90th percentile are distinct. The 90th percentile is neither a hard maximum nor a confidence interval. Case B doubles all three specified times.
- Primary headers t_P+t_T and 90th are corrupted upstream to +d and yz06. All six body values are retained. Formula 6 labels time in hours while this table uses days; conversion requires 24 h/day.
- Fuel order occurs at 20% remaining tank capacity; a fixed 80% capacity delivery is described. Weibull calibration is a modeling assumption, not an empirical upper-bound guarantee.

## 表2：原PDF第18页

| Asset | P_0 and UM* | alpha ($/UM*) | beta (-) | Maintenance ($/UM/y) |
| --- | --- | --- | --- | --- |
| PV | 1 kW | 800 | 1 | 16 |
| Battery | 1 kWh | 350 | 1 | 3 |
| Bat. conv. | 1 kW | 1258 | 0.5 | 2 |
| Inverter | 1 kW | 1887 | 0.5 | 2 |
| Fuel gen. | 1 kW | 1013 | 0.8 | 0.05$/kW/h |
| Fuel tank | 1 liter | 52.2 | 0.45 | 0.15 |

- All six physical asset rows are visible in the primary crop. The raw parser contains only PV, Battery and Bat. conv. merged into one row; all Inverter/Fuel gen./Fuel tank rows are absent, not zero.
- P_0 is a reference size with asset-specific units: kW, kWh or liter. Alpha, beta and maintenance are different quantities. Formula 9 scales alpha by a dimensionless size ratio raised to beta; beta below one implies nonlinear scale economies.
- The diesel maintenance entry explicitly uses $/kW/h despite the general annual maintenance column heading. Keep this exception and the alpha unit/header convention; do not invent annual runtime or total costs.

## 表3：原PDF第21页

| Fuel price ($/liter) | LFS / 0.5 / delivery A | LFS / 0.5 / delivery B | LFS / 1 / delivery A | LFS / 1 / delivery B | RHS / 0.5 / delivery A | RHS / 0.5 / delivery B | RHS / 1 / delivery A | RHS / 1 / delivery B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.8 | 95 | 100 | 122 | 129 | 46 | 46 | 56 | 57 |
| 1.2 | 0 | 0 | 113 | 114 | 24 | 23 | 52 | 57 |
| 1.6 | 0 | 0 | 100 | 99 | 0 | 0 | 43 | 49 |

- All 24 installed diesel generator sizes have units kW. Preserve all zeros and the eight independent strategy/cost/delivery column combinations.
- RHS is not universally smaller: at fuel price1.2 and curtailment cost0.5 LFS installs zero while RHS installs24/23kW. Zero generator capacity does not imply zero demand or established reliability.
- Figure5 panel B1 denotes fuel1.2/curtailment0.5; it is not fuel-delivery scenario B. The primary prose24kW corresponds to table deliveryA; deliveryB is23kW.

## 表4：原PDF第21页

| Fuel price ($/liter) | LFS / 0.5 / delivery A | LFS / 0.5 / delivery B | LFS / 1 / delivery A | LFS / 1 / delivery B | RHS / 0.5 / delivery A | RHS / 0.5 / delivery B | RHS / 1 / delivery A | RHS / 1 / delivery B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.8 | 2.3 | 4.0 | 3.4 | 5.5 | 3.2 | 5.2 | 3.9 | 8.0 |
| 1.2 | 0 | 0 | 3.2 | 4.2 | 1.5 | 2.2 | 3.6 | 4.5 |
| 1.6 | 0 | 0 | 2.9 | 3.1 | 0 | 0 | 2.3 | 4.0 |

- Tank sizes are thousands of liters, not liters or kWh. All 24 cells and zero installations retained; every tank zero coincides with the corresponding generator zero.
- For each fixed strategy/cost/delivery combination, the complete table shows nonincreasing tank size as fuel price rises. Primary adjacent prose instead says higher fuel price increases size. Preserve this primary cross-statement inconsistency.
- DeliveryB exceedsA whenever both sizes are positive. RHS is not universally larger: at fuel1.6/cost1/deliveryA RHS2.3 is below LFS2.9. Ratios with zero LFS are undefined; zero/zero is not a percentage improvement. Fuel use24–35% and diesel energy28–45% are distinct prose quantities.

## 全部公式与科学解释边界

### 公式1a, 1b, 1c, 1d, 1e, 1f

- `min sum_t(C_F,t + C_C,t + C_M,t + C_RC,t) + C_SS`
- `C_SS = 0 if E_B,24 > E_B,0; c_SS(E_B,24 - E_B,0) otherwise`
- `C_C,t = c_C P_C,t`
- `C_M,t = c_M z_D,t`
- `C_F,t = c_F F_D,t`
- `C_RC,t = c_R,t P_RC,t`

- Printed1b gives a negative cost for final battery energy below initial when c_SS is positive, although prose calls this an overuse penalty. This is visible in the primary PDF, not solely a parser defect. The mathematical example below is not a measurement or implementation assertion.
- The raw equation block loses several cost relations and mislabels a maintenance-like term as fuel cost. The primary six subequations, binary diesel state, fuel use and load-versus-renewable curtailment costs must remain distinct.
- This rolling-horizon dispatch objective is distinct from the full-project expected NPC sizing objective.

### 公式2a, 2b

- `P_D,t + P_inv+,t - P_inv-,t = P_L,t - P_C,t`
- `P_B+,t - P_B-,t + P_inv+,t eta_I - P_inv-,t/eta_I + P_PVAv,t = P_RC,t`

- The primary AC balance contains diesel output P_D,t. Raw parser substitutes battery charge/discharge terms on that side, changing physical resource identity.
- Keep primary DC-side efficiency conventions as printed and distinguish the DC battery/PV and AC load/diesel buses; no unverified engineering correction is inserted.

### 公式3a, 3b, 3c

- `P_D,min z_D,t <= P_D,t <= P_D,max z_D,t`
- `F_D,t >= c_DS,i P_D,t + c_DI,i - (1-z_D,t) M for all t,i`
- `V_F,t = V_F,0 - sum_tprime=1..t F_D,tprime >= 0`

- Primary3a enforces the on/off technical minimum and maximum; parser omits it and duplicates3b. Big-M and binary diesel state are not continuously variable generator capacities.
- Fuel consumption and tank stock must share a compatible per-step volume convention. The case uses hourly physical steps; no nonhourly conversion factor is supplied by this printed equation.

### 公式4a, 4b, 4c, 4d, 4e, 4f

- `0 <= P_inv+,t <= z_I,t P_inv+,max`
- `0 <= P_inv-,t <= (1-z_I,t) P_inv-,max`
- `E_B,max <= E_B,t <= E_B,max`
- `E_B,t = E_B,0 + sum_that=1..t (-P_B+,that/eta_I + eta_B P_B-,that)`
- `0 <= P_B+,t <= z_B,t P_B+,max`
- `0 <= P_B-,t <= (1-z_B,t) P_B-,max`

- Primary4c itself prints max on BOTH sides. Literal inequality forces E_B,t to equal E_B,max. Do not silently replace the lower bound with min or claim that the actual solver used this expression.
- Charge/discharge exclusivity and inverter directional limits are six separate constraints. Preserve printed eta_I/eta_B in4d; power-energy relation needs timestep units, case uses1h.

### 公式5a, 5b

- `0 <= P_PV,t <= P_PVAv,t`
- `0 <= P_C,t <= P_L,t`

- PV availability and load curtailment bounds are distinct. Renewable curtailment and unserved load do not have interchangeable penalties.

### 公式6

- `t_D (h) = t_P + t_T + pdf`

- The primary prose defines pdf as a probability density function, yet the printed equation adds it to time. Density-versus-random-duration dimensional interpretation is unresolved. Preserve the primary wording without claiming actual Monte Carlo samples were implemented incorrectly.
- Table1 times are days; the equation labels hours. No maximum delivery time is established by a90th percentile.

### 公式7

- `NPC = sum_y=0..N_L (CAPEX_y + OPEX_y)/(1+i)^y`

- Discounted full-project costs include investment, replacements and operating cost. Fifteen-year project life is a case assumption; NPC is not annual OPEX, dispatch cost or COE.

### 公式8

- `OPEX_y = sum_s=1..S OPEX_y,s / S`

- This is an equal-weight Monte Carlo scenario mean; the case hasS=5. It is not a confidence interval, worst-case guarantee or an independently validated population expectation.

### 公式9

- `C(x) = alpha (P_x/P_0)^beta`

- The reference-size ratio is dimensionless and beta controls economies of scale. At beta0.5 quadrupling the reference size doubles modeled cost rather than quadrupling it. Table2 alpha/beta/maintenance and asset units are independently retained.

## 全部图形与外部有效性

### Fig.1

- Complete single-bus topology: PV and battery converter on DC bus, bidirectional inverter linking AC bus, fuel storage and engine-generator supply AC load. This modeling topology is not field deployment or a detailed distribution-network power-flow result.
- Primary simplification includes distribution losses within demand. All arrows and component roles considered.

### Fig.2

- Complete rolling-horizon illustration distinguishes physical timestepT_r, dispatch refreshT_h and optimization horizonT_o. Forecast PV/load and scheduled diesel are distinguished from past actual values and real-time correction.
- CaseT_r=1h, T_h=6h, T_o=24h. No exact unprinted curve values or empirical forecast accuracy inferred from the schematic.

### Fig.3

- Complete nested workflow: draw annual scenarios, outerPSO component sizing/CAPEX, inner per-scenario dispatch with LFS or RHS MILP refresh and real-time correction, annual operational/replacement costs and expectedNPC, then updatePSO best and termination.
- The diagram labels an optimal output but does not prove a global optimum. CasePSO200 maximum iterations,12 stall iterations,tolerance10^-3; simulated annual scenariosS=5.

### Fig.4

- Complete two-panel NPC comparison: load-curtailment costs0.5/1.0USD/kWh; fuel0.80/1.20/1.60; greenLFS and blueRHS. Each plotted value averages fuel-delivery casesA/B; small error bars are their min/max, not confidence intervals or Monte Carlo standard deviations.
- NPC axisM$ has a truncated1.7 baseline, so bar lengths cannot be compared as percentages from zero. Printed fuel x-axis label$/kWh conflicts with table/prose$/liter and remains a primary label inconsistency.
- VisibleRHS is lower or equal in all six pairs, equal at highest fuel/lowest curtailment. The prose3% is not independently recovered as an exact unprinted bar value.

### Fig.5

- Complete six panelsA1/A2/B1/B2/C1/C2: three fuel prices0.8/1.2/1.6USD/L by two curtailment costs0.5/1USD/kWh; two strategies and four component bars each,48 bars in total. PanelA/B/C letters are independent of fuel-delivery scenarioA/B.
- Difference(%) is relative to baselineLFS panelA1 sizesPV806kWp, converter412kW,inverter234kW,battery2.25MWh. A zero difference bar is not zero installed capacity; negative percentages are not negative capacities.
- Means and min/max bars refer to deliveryA/B. All components/legend/axis ranges retained; RHS is not uniformly smaller, including C1battery and C2converter exceptions. No exact unprinted bar heights or sampling confidence intervals invented.


- Five annual Monte Carlo scenarios and15-year planning life; physical1h/dispatch6h/forecast24h. This is a simulation sizing study, not our rerun or a globally certified optimum.
- Forecast error is generated with Gaussian standard deviation5% at first prediction step rising to15% at horizon end. Local input demand uses nearby2014half-hour measurements plus Gaussian noise20% of actual demand; input provenance does not establish real deployment validation.
- SyntheticPV/weather and mid-term representative annual load; long-term load growth is not simulated. Conclusion explicitly places real-mini-grid testing in future work.
- Author computational timing (~month on12-core16GB and500timesLFS/RHS difference) remains an author report. No independent timing rerun or new software benchmark performed.

原文电池边界两端均为max、过度使用费用的符号与文字解释冲突、油箱尺寸的价格趋势与正文冲突，均单独保留。未把原文矛盾归因于学生幻觉，也未推测实际求解器实现。科学评测尚未完成。

[完整原始证据与精确算术](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-stochastic-table-equation-figure-science-review-v12.json)。
