---
name: honc-checkin
description: 用当前用户消息记录真实习惯打卡，保留数量、单位、原文和发生精度
---

# 习惯打卡

1. 调用 honc_get_life_context。默认仅返回简短习惯索引。已明确习惯时可直接
   honc_get_life_context(habit_name="锻体tod")，或用索引的 object_id 传 habit_id。
   这次返回该习惯的完整定义与 occurrences；补记时同时给 business_date。
   读取对应 ID、revision、definition 与 occurrences，
   以及当前消息 record_habit 的 request_ref。省略 context_ref，插件会注入。
2. 逐字摘 source_quote，匹配已有名称／别名。找不到或多个候选，只问习惯名称；不要自动建习惯。
3. 调用 honc_record_habit(request={request_ref, entries:[...]})，同消息多个习惯一次提交。
   每个 entry 必须有 habit_id、habit_revision、outcome、source_quote。其他字段按用户事实提供。
4. completed 表示用户明确完成，partial 表示部分实际完成，not_done 表示明确没做，skipped 表示跳过。
   「准备」「明天」「如果」「他说」「做了吗」均不记录完成。没提数量不填 1 或 0。
5. boolean 不填数值／单位；count 填整数次数（unit=time 或省略）；quantity 使用习惯配置的单位；
   duration 使用 second／minute／hour，20 分钟不是 20 次。number 是旧习惯未知单位数值，不能猜单位。
   text 保存用户原文；selection 保存 selection_values，如 {"散步":2,"厕所":null}，类别逐字来自原文。
6. time 的 precision 可为 unknown（没有发生时间）、date（今天／昨天日期）、approximate（保留 time_text）、
   exact（用户确实给出时间，必须有时区）。未知不能默认刚刚发生；recorded_at 由后端保存。
7. 多时段先按 habit_id／habit_name 单独读上下文，避免长结果丢失实例。
   明确属于某餐／某次的，取 occurrences 的对应 instance_id，habit_revision 复制该实例返回值。
   用户说「上午九点那次」，就选 due_at 当地09:00的那条，别再次确认已经明确的时间。
   只有一实例时后端可绑定。漏传 instance_id 返回 INSTANCE_NOT_BOUND 时，单独读取后补齐原请求；
   此时 effect_state=none，没有提交事实。不要搜索会话、MCP资源或自造 prompt 去找实例。
   早餐记录不完成午餐；昨日补记不完成今天；多实例不确定时只补问对应哪一次。
8. 日记通过 honc_save_diary 保存，它会原子关联日记习惯，不要再调 record_habit。
   身体状态走 honc_record_body；工作执行走原有工具，以上均不结束回合。

示例结构（ID、版本、request_ref 必须换成当前上下文返回值）：
```json
{"request":{"request_ref":"当前 record_habit 引用","entries":[{"habit_id":"当前习惯ID","habit_revision":1,"outcome":"completed","source_quote":"今天锻体20","value":20.0,"time":{"precision":"date","occurred_date":"2026-10-13"}}]}}
```

APPLIED／ALREADY_APPLIED 才可确认已记录。UNKNOWN 调 honc_get_life_operation 查原 request_ref，
不得换引用重写。CONFLICT 重读当前习惯版本；SOURCE_QUOTE_MISMATCH 重用真实逐字原文；
单位或目标不清只问必需字段。未记录是未知，不能说没做。查询加载 honc-life-history；
调整定义加载 honc-life-settings；工作日报仍用 honc_get_report。
