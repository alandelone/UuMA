# 加纳SoAMIRural：完整原文科学核验

直接阅读全部18原PDF页和全部30表图裁片：15表、15图、7公式块（6编号公式及1符号定义）。10篇完整测试范围与原始评分保持。

主要发现：表4的灯和手机、表7的灯功率×数量×时长不等于印出的用电量；表8家庭数使用人数，与正文家庭数不同；表10大型设施合计4，正文和表9使用5。表12多晶效率17.18与表11/公式3不一致。原文95%准确率没有测试分母、独立基准或误差数据；不能把5%统计误差设定转换成实测准确率。

全部原始数字与符号保留，条件重放只说明矛盾，不替换作者实现或创建评分依据。印出的算法用同一个非负消费量产生110%阈值后再与自身比较，无法触发该条件；没有源码，不能据此认定实际软件行为。论文的实地部署照片、瞬时设备显示、概念图和长期因果/寿命验证分别解释。

## Table 1

| Priorities | Number of People |
| --- | --- |
| Education | 73 |
| Health | 145 |
| Communication | 46 |
| Economic activities | 79 |
| Domestic activities | 43 |
| Total | 386 |

- Five priority counts sum386 and match Fig4/Table14; descriptive chosen priorities, not measured health/education outcomes. Results prose267health/80domestic conflicts with145/43 here.

## Table 2

| Appliance | Power Rating (W) | Number of Appliances | Average Time Duration of Use per Day (h) | Times of Day Appliances Are Used | Total Consumption per Day (Wh) |
| --- | --- | --- | --- | --- | --- |
| Lights indoors | 15 | 2 | 2 | 6 p.m.–8 p.m. | 60 |
| Outdoors lamp | 20 | 3 | 12 | 6 p.m.–6 a.m. | 720 |
| Mobile phone | 5 | 2 | 3 | 5 p.m.–8 p.m. | 30 |
| Radio set | 10 | 1 | 12 | 8 a.m.–8 p.m. | 120 |
| Total | 50 | 8 | 29 |  | 930 |

- All four P×n×hours products agree with printed Wh. Total50W sums distinct ratings, not quantity-weighted connected power.

## Table 3

| Appliance | Power Rating (W) | Number of Appliances | Average Time Duration of Use per Day (h) | Times of Day Appliances Are Used | Total Consumption per Day (Wh) |
| --- | --- | --- | --- | --- | --- |
| Lights indoors | 15 | 3 | 2 | 6 p.m.–8 p.m. | 90 |
| Outdoors lamp | 20 | 3 | 12 | 6 p.m.–6 a.m. | 720 |
| Mobile phone | 5 | 3 | 3 | 5 p.m.–8 p.m. | 45 |
| TV | 100 | 1 | 12 | 8 a.m.–8 p.m. | 1200 |
| Deep freezer | 400 | 1 | 24 | 6 a.m.–6 a.m. | 9600 |
| Total | 540 | 11 | 53 |  | 11,655 |

- All five P×n×hours products agree with printed Wh. Printed11655Wh/day exceeds the text medium1–3kWh/day classification; preserve both.

## Table 4

| Appliance | Power Rating (W) | Number of Appliances | Average Time Duration of Use per Day (h) | Times of Day Appliances Are Used | Total Consumption per Day (Wh) |
| --- | --- | --- | --- | --- | --- |
| Lights indoors | 15 | 3 | 2 | 6 p.m.–8 p.m. | 900 |
| Outdoors lamp | 20 | 3 | 12 | 6 p.m.–6 a.m. | 720 |
| Mobile phone | 5 | 4 | 3 | 5 p.m.–8 p.m. | 45 |
| TV | 100 | 1 | 12 | 8 a.m.–8 p.m. | 1200 |
| Deep freezer | 400 | 2 | 24 | 6 a.m.–6 a.m. | 19,200 |
| Decoder | 25 | 1 | 12 | 8 a.m.–8 p.m. | 300 |
| Total | 565 | 14 | 65 |  | 22,065 |

- Primary indoor-lamp900Wh conflicts with15×3×2=90; phone45Wh conflicts with5×4×3=60. Printed total22065 differs from printed component sum22365 by-300 and formula result21570 by495. Summed65hours spans appliances, not household elapsed daily duration.

## Table 5

| Appliance | Power Rating (W) | Number of Appliances | Average Time Duration of Use per Day (h) | Times of Day Appliances Are Used | Total Consumption per Day (Wh) |
| --- | --- | --- | --- | --- | --- |
| Lamps (CFL) | 20 | 4 | 13 | 5:30 p.m.–6:30 a.m. | 1040 |
| Mobile phone | 3 | 2 | 4 | 5 p.m.–9 p.m. | 24 |
| Radio set | 11 | 2 | 6 | 6 a.m.–7 a.m., 4 p.m.–10 p.m. | 132 |
| Total | 34 | 8 | 23 |  | 1196 |

- All three products agree with Wh, but radio time intervals6–7am and4–10pm total7hours versus printed duration6. Preserve scheduling inconsistency.

## Table 6

| Appliance | Power Rating (W) | Number of Appliances | Average Time Duration of Use per Day (h) | Times of Day Appliances Are Used | Total Consumption per Day (Wh) |
| --- | --- | --- | --- | --- | --- |
| Lamps | 15 | 8 | 12 | 6 p.m.–6 a.m. | 1440 |
| Mobile phone | 6 | 5 | 4 | 5 p.m.–9 p.m. | 120 |
| Radio set | 10 | 3 | 5 | 5 a.m.–7 a.m. 5 p.m.–8 p.m., | 150 |
| Fan | 60 | 2 | 12 | 6 p.m.–6 a.m. | 1440 |
| TV | 95 | 2 | 6 | 4 p.m.–10 p.m. | 1140 |
| Total |  |  |  |  | 4290 |

- All five products agree; total4290Wh exceeds text medium1–3kWh/day classification. Blank total-rating/count/hour cells remain unspecified, not0.

## Table 7

| Appliance | Power Rating (W) | Number of Appliances | Average Time Duration of Use per Day (h) | Times of Day Appliances Are Used | Total Consumption per Day (Wh) |
| --- | --- | --- | --- | --- | --- |
| Lamps | 10 | 7 | 12 | 6 p.m.–6 a.m. | 8400 |
| Mobile phone | 8 | 5 | 5 | 5 p.m.–9 p.m. | 200 |
| Fan | 60 | 2 | 12 | 6 p.m.–6 a.m. | 1440 |
| Freezer | 450 | 2 | 24 | 6 a.m.–6 a.m. | 21,600 |
| Paid TV. | 20 | 2 | 5 | 5 p.m.–10 p.m. | 200 |
| Stereo | 30 | 2 | 5 | 5 p.m.–10 p.m. | 300 |
| Irons | 1200 | 2 | 1 | 6 a.m.–7 a.m. | 2400 |
| TV Set | 105 | 2 | 5 | 5 p.m.–10 p.m. | 1050 |
| Total |  |  |  |  | 35,590 |

- Primary lamp8400Wh conflicts with10×7×12=840Wh. Printed35590Wh sums printed cells; formula components sum28030. Phone5hours conflicts with5–9pm four-hour interval.

## Table 8

| Total per Day Consumption for Single Household (Wh) | Number of Households | Total per Day Consumption of All Residential Buildings (Wh) |
| --- | --- | --- |
| 1196 | 174 | 208,104 |
| 4290 | 135 | 579,150 |
| 35,590 | 77 | 2,740,430 |

- All three printed products are exact, but household column174/135/77 equals total people386. Adjacent prose instead derives35/27/16 households with five people per household; neither is reconciled with80households onpage3/Table15.

## Table 9

| Total per Day Consumption for Single Household (Wh) | Number of Facilities | Total per Day Consumption of All Residential Buildings (Wh) |
| --- | --- | --- |
| 930 | 6 | 5580 |
| 11,655 | 5 | 58,275 |
| 22,065 | 5 | 110,325 |

- Commercial caption versus inherited single-household/all-residential column labels is primary inconsistency. Parser drops facilities6/5 and writes11.655 where primary has11,655. Printed products exact; five large facilities conflict with Table10sum4.

## Table 10

| Facility | Small-Scale | Medium-Scale | Large-Scale |
| --- | --- | --- | --- |
| Eatery | 0 | 2 | 1 |
| Church | 0 | 0 | 1 |
| Mosque | 0 | 1 | 0 |
| Shop | 3 | 2 | 1 |
| Barbering salon | 1 | 0 | 0 |
| Sewing shop | 2 | 0 | 0 |
| Storage unit | 0 | 0 | 1 |

- All21counts inclzeros checked; category sums6/5/4, not prose/Table9six/five/five. Facility categories are not equivalent to consumption measurements.

## Table 11

| Parameters | Thin Film | Monocrystalline | Polycrystalline | Interpretation |
| --- | --- | --- | --- | --- |
| Efficiency (direct sunlight) (%) | 7 | 17.5 | 14.5 | The higher, the better |
| Cost in USD/W | 0.50-1.00 | 0.60-0.90 | 0.40-0.60 | The lower, the better |
| Land area/kW (m^2 ) | 13-20 | 6-9 | 8-9 | The lower, the better |
| Low-light performance factor | 7 | 4 | 4 | The higher, the better |
| Life span (years) | 10 | 25 | 25 | The higher, the better |

- All15numeric cells include six ranges preserved as intervals;5direction texts. Midpoints for costs/land are an explicit conditional replay assumption, not printed actual chosen values.

## Table 12

| Parameters | Thin Film | Monocrystalline | Polycrystalline |
| --- | --- | --- | --- |
| Efficiency (under direct sunlight) | 17.95 | 44.87 | 17.18 |
| Cost | 31.25 | 31.25 | 37.5 |
| Land area | 24.62 | 38.46 | 36.91 |
| Low-light performance | 46.67 | 26.67 | 26.67 |
| Life span | 16.67 | 41.67 | 41.67 |
| total | 137.16 | 182.92 | 159.93 |

- Primary polycrystalline efficiency matrix17.18 versus Eq3/Table11implied37.179487...; first row sums80, not100. All three printed column totals exactly sum printed cells; conditional replacement of one efficiency value changes ranking gap, not a permitted source/grade repair.

## Table 13

| Components | Size |
| --- | --- |
| Solar PV Array | 24 kW |
| Battery bank | 28.5 kWh |
| Hybrid Inverter | 8 kVA × 3 = 24 kVA |

- 24kW PV,28.5kWh storage,8kVA×3=24kVA inverter distinct units. Fig7names four batteries each5.7kWh=22.8, not28.5. Actual voltage/DoD/autonomy/sun-hours/efficiency numerical inputs not supplied, so sizing cannot be independently reconstructed.

## Table 14

| Priorities | Number of People | Reasons for the Need for Electricity Access |
| --- | --- | --- |
| Education | 73 | • To help students study at night. • To get access to good studying materials, e.g., laptops and internet access. |
| Health | 145 | • To give the townspeople access to 24/7 healthcare services • For good storage facilities for drugs and vaccines. • To improve existing healthcare facilities. |
| Communication | 46 | • Keep in contact with friends and family members who have moved from Yeboahkrom to other towns or cities. • To stay informed about national and global news through radio, television, the internet, etc. |
| Economic activities | 79 | • To give farmers access to state-of-the-art storage equipment for farm produce. • To increase productivity and efficiency to reduce strain on farmers. • To help traders store perishable goods for longer periods and sell cold products such as ice water and ice cream to students. |
| Domestic activities | 43 | • To provide households with an alternate form of cooking to alleviate the problems with traditional cooking methods. • To provide better storage for cooked foods. • To provide lighting to aid visibility during night-times and reduce the risk of fire outbreaks that candles and lanterns can cause |

- All five counts and13reason bullets preserved. Counts145health/43domestic matchTable1/Fig4, conflict Results267/80. Requested/expected benefits do not measure realised causal changes.

## Table 15

| Community | Generation Capacity (kVA) | Household | Impact |
| --- | --- | --- | --- |
| Wayokope | 20 | 57 | System not working |
| Aglakope | 33 | 128 | Works only during the day |
| Kudorkope | 33 | 175 | Works only during the day |
| Yeboahkrom (SoAMIRural) | 24 | 80 | Working smoothing with AMI for load monitoring |

- All four communities/eight numeric/four qualitative outcomes preserved. Unequal sizes20/33/33/24kVA and57/128/175/80households, nonrandom selection and no comparable observation window prevent isolating AMI causal impact. Literal working smoothing retained in rows.

## 图形、公式与方法边界

- Figure 1: Location map with municipality/national/world context, scale and roads; not outcome or reliability evidence. Caption2021, not current administrative map verification.
- Figure 2: Housing location/photos, laterite/wood/aluminium and rammed-earth proposal; proposal is not implemented renewable-energy effect.
- Figure 3: School/clinic/shrine map/photos; caption housing conditions versus drawn existing community infrastructure preserved.
- Figure 4: All five printed counts73/145/46/79/43 match tables1/14; axes people versus categorical priority, descriptive preferences.
- Figure 5: Entire needs→scenarios→technology→technoeconomic→business→financing framework and feedback arrows. MCDM/HOMER are possibility/example labels, not proof those simulations ran.
- Figure 6: AMI conceptual PV/inverter/battery/smartmeters/DCU/DCP/masterstation/API/thirdparty roles. API/banking/ATM/POS diagram capability does not establish deployed transactions or cybersecurity validation.
- Figure 7: All inverter/breaker/surge/bus/earthing/RCD/loads and diagram legend. V1/V2/V3 printed8kW hybrid versus prose8kVA; fourBAT1..4each5.7kWh conflicts Table13bank28.5kWh. Cables labelledmm versus areas not redesigned here.
- Figure 8: 3D panel layout is design illustration, not power-output time series or independent energy verification.
- Figure 9: Fullfive assembly groups; dimensions1000×2000mm panels,38mm×1000mmangle,5000mmsteelbar,115×254mmpipe,100×2438mmpipe preserved. Structural loads/material safety not independently tested.
- Figure 10: Photograph showing physical installation supports illustrated implementation; no longitudinal output, lifespan or causal livelihood estimate derivable.
- Figure 11: Equipment photograph caption calls simulation of generation/output voltage; instantaneous display230 and phase232/245/230 cannot establish95%accuracy or capacity time series.
- Figure 12: Configured control-station photograph; visible installation not software/source-code/threshold-test validation.
- Figure 13: 24hour category axis/printed0/.01/.02/.03 labels, consumptionyaxis lacks unit; prose sayskWh for26Feb2022. Snapshot does not establish sensor95%accuracy or universal household consumption; different date fromFig14.
- Figure 14: All12daily labels29Dec2021..9Jan2022 and3.11/7.59/8.36/10.51/6.65/16.64/9.58/10.9/5.14/16.79/17.5/19.02 directlyread. AxisConsumption has no unit; do not infer kWh solely from axes. Different scale/date thanFig13.
- Figure 15: All24hour markers,Energyconsumption(kWh) axis0..4.5, daytime trough7..16 and18..19peak. No exact unprinted ordinates invented; date not shown, no errorbars/uncertainty. Energy per hourly interval differs from instantaneouskW and dailytotal.

- SingleGhana case installation, survey and illustrative AMI monitoring; no random assignment or matched pre/post quantitative control. Three other locations have unequal sizes and no harmonised outcomes/window.
- Abstract5%error/95%accuracy lacks operational accuracy denominator, independentmeterreference, testcount/errors oruncertainty. Sample-size error margin is not classifier/sensor accuracy.
- Eq1 prints q%p%z/e% without square or supplied q,p,z,e numerical execution; no sample-size reproduction or statistical confidence claim added.
- Literal Algorithm1 sets threshold from same consumption and compares consumption>1.1consumption, false for nonnegative values; units of AL+5 and fixed historical baseline/current consumption roles unspecified. No code/runtime supplied, so actualrelayfailure not inferred.
- Eq4 fixed r in summationj and numeric r=k=n equated to a set are primary notation defects; declared conditional intended varying-j normalisation separated from literal uniform result.
- Eq6 dimensions Wh/V areAh for stated autonomyday ratio, notkWh; voltage/DoD/autonomy/efficiency not printednumerically. kW PV andkVA inverter are distinct.
- Printedtable demand versus observedhourlygraphs cannot be equated without actualmeasurement dates/usercount/units/dailyallocation. Current max/min plotted trends do not validate long-term battery-life/causal education/health/sustainability claims.
- Data onrequest/privacyLivingLab restriction,IRB/consent Notapplicable and noconflict are author statements retained; no externalcontact/access/approval inferred.
- Setup/operatingcosts/abilitytopay/TOU and AMIattack vulnerabilities explicitly futurework; not resolved by concept API diagram.

[全部精确算术及来源](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/complete-ghana-table-equation-figure-science-review-v14.json)。当前为原文核验，不是整篇科学判断批准。
