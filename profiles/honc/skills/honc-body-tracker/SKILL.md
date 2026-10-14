---
name: honc-body-tracker
description: 记录用户主动提供的身体状态，包括不适和感觉良好，保留未知细节
---

# 身体记录

用户主动说「流鼻涕，有点累」「膝盖痛」「今天状态很好」时使用。查询、假设、别人的症状不写。
先 honc_get_life_context，使用当前 record_body request_ref。工具为
honc_record_body(request={request_ref,source_quote,observations,time?,related_record_ids?})。
source_quote 逐字摘当前用户话；observations 每条至少 description，必须保留原词。
body_part、severity_text、change_text 只填用户明确说出的原文，不提就省略／null。
reported_score 与 score_scale 必须由用户同时给出，例如明确说「疼痛3分，满分10」；
不可把「有点」量化成3分，不得猜诊断、病因、恶化趋势。不要询问身体变化。

time 遵循 unknown／date／approximate／exact：今天可用当前 KL 日期，昨天减一天；
「有时」「早上」保留 time_text，不猜具体钟点。related_record_ids 只取已保存且同一用户的真实 ID。
```json
{"request":{"request_ref":"当前 record_body 引用","source_quote":"今天流鼻涕，有点累","observations":[{"description":"流鼻涕"},{"description":"有点累"}],"time":{"precision":"date","occurred_date":"2026-10-13"}}}
```
一个消息多个症状一次写。事实保存不结束专注回合，不更新任务，不建立提醒。
APPLIED／ALREADY_APPLIED 才答已记录，可简短复述；UNKNOWN 查原回执，不重写。
没有必需字段缺失时不要发问。身体历史走 honc-life-history；更正必须原记录 ID、当前版本和原因。
晚上只有睡前日记邀请可顺带邀请记录今天身体状态，默认一遍；身体消息本身不增加任何提醒。
