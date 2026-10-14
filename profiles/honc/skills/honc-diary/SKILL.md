---
name: honc-diary
description: 保存原文日记并原子关联日记习惯，支持补记、更正与撤销
---

# 日记

用户说「记一下日记」「今天的日记是…」时先 honc_get_life_context，取 save_diary request_ref。
调用 honc_save_diary(request={request_ref,source_quote,content,diary_date?,linked_record_ids?})。
content 必须当前原文，不改写为模型总结；source_quote 要完整覆盖正文，不能选不相关句子。
明确今天／昨天时按上下文 KL 日期解释 diary_date；没有日期省略，不能猜是今天。
已存在的 semantic_role=diary 习惯会由后端原子写一条关联打卡；不要再次 honc_record_habit。
若有多个活动日记习惯，后端返回歧义，需要先明确配置；不选一个随意完成。
linked_record_ids 只放本用户已保存的实际记录 ID；日记中症状如需要独立身体记录，
只能用当前消息 record_body 授权，不能从历史日记补造身体事实。

默认睡前 21:30 提醒一次，也可因用户明确提前准备睡觉推进同夜实例。
提醒只是邀请记录日记和今天身体状态，不追问变化，不追催未完成习惯。
用户未回应时不再提醒；重要度不增加次数。已写当晚日记可取消尚未发出的本次日记提醒。
昨日补记不能取消今日日记提醒。

APPLIED／ALREADY_APPLIED 才确认。UNKNOWN 查原回执。更正／void 使用 honc_correct_life_record
指定日记原 ID、expected_revision、reason 与 corrected_text 或 void=true；关联习惯也会同事务更正／撤销，
不能另写新的打卡抵消。原文和各版本一直保存在 audit 视图。查询详见 honc-life-history。
