# ALL4 科学评测：全部九个原未决窗口的成对复核

预先固定的 18 个案例均已进入独立审计；可评分配对 7/9，覆盖 5 个论文组。完整科学评测仍未完成，尚未证明优化总体有效。

两版候选、源参考、原判断及 DSPy 提示保持冻结。保留全部原负面、失败和未决记录；未决分数不补零。原来 11 个个别未决窗口中有 2 个同时缺失基线输出，仍列在原提取缺失组，不从本轮遗漏账目。

| 论文 | 窗口编号（从 0 起） | 基线综合分 | 优化综合分 | 差值 |
|---|---:|---:|---:|---:|
| PHS | 0 | 0.764434 | 0.767048 | +0.002614 |
| 政策 MCDA | 0 | 0.720952 | 0.751577 | +0.030624 |
| 政策 MCDA | 6 | 0.441726 | 0.433671 | -0.008056 |
| PTHP | 2 | 0.650459 | 0.665437 | +0.014977 |
| PTHP | 9 | 0.613662 | 0.655181 | +0.041519 |
| PTHP | 10 | 0.680655 | 未决或评审失败 | 不计算 |
| URB | 1 | 0.684669 | 0.672727 | -0.011942 |
| 光伏车棚 | 6 | 0.894737 | 未决或评审失败 | 不计算 |
| 光伏车棚 | 14 | 0.800926 | 0.774444 | -0.026481 |

未决及失败的逐案原因（原评审文字保留，未按期望结果改写）：

- PTHP 窗口 10 / optimized：The reference evidence location points to text describing a figure surface rather than equation (6).；Several reference relations (r1 -> r3, r3 -> r4, r11 -> r12) lack corresponding actual candidate relations in the extracted candidate relations list.
- 光伏车棚 窗口 6 / optimized：Reference r0 bundles multiple distinct variable definitions into a single monolithic claim instead of providing atomic reference statements corresponding to the individual extracted candidate facts.；Reference r0 bundles multiple distinct variable definitions into a single monolithic claim instead of providing atomic reference statements corresponding to the individual extracted candidate facts.

仅对上述可评分配对按论文等权：综合差值 +0.000745，描述性论文重采样区间 [-0.015535581754069149, 0.016817238268159063]，探索性符号翻转 p=0.875000，七指标 Holm p=1.000000。选择依赖原未决状态，分析未预注册，论文组数较少，不能推广为十篇论文总体效果。

| 指标 | 基线 | 优化 | 差值 |
|---|---:|---:|---:|
| L1 原子覆盖 | 0.946154 | 0.943333 | -0.002821 |
| 条件召回 | 0.946154 | 0.935333 | -0.010821 |
| L2 关系 F1 | 0.259174 | 0.251063 | -0.008111 |
| L3 意图 F1 | 0.493307 | 0.515237 | +0.021930 |
| L4 角色准确率 | 0.776136 | 0.784470 | +0.008333 |
| 不受支持原子比例 | 0.000000 | 0.000000 | +0.000000 |
| 综合分 | 0.692686 | 0.693430 | +0.000745 |

未决原因逐案保存在完整记录中，包括源参考缺陷、未决原子及未决关系。格式通过和评分可复算不表示论文原科学结论被验证；AI 参考仍不等于专家金标准。

实际请求：400 次逻辑调用，398 个不同实际运行，394 个接受阶段，6 次原验证器再次确认的被拒输出。

跨协议已有 77/126 个不同窗口可比较，剩余 49 个：40 个源参考未通过、7 个提取缺失、2 个本轮仍未决或评审失败。各协议与选择队列分别报告，未拼成一套总体统计。全部 20 个整篇候选的原状态保留。

[逐案证据与精确指标](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/paired-scientific-evaluator-successor-v2.json)
[全部请求与拒绝审计](C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/scientific-evaluator-successor-v2/independent-rejected-attempt-and-request-inventory-audit-v1.json)
[原十篇科学诊断](C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/full-scientific-evaluation-2026-10-08/final-scientific-assessment-v1.md)
