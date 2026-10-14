---
name: honc-life-history
description: 查询原生活记录与稳定分页，更正或撤销明确记录并保留所有版本
---

# 查询与更正

先 honc_get_life_context。读取用 honc_get_life_history，选择 record_id 或 start_date/end_date。
kinds 可筛 habit/body/diary/anchor/activity，habit_id 可指定；limit 默认20、最大100。
effective 返回当前有效事实，排除撤销；audit 返回各版本。记录时间和发生时间分别展示。
未知发生日期用 recorded_date 标记检索依据，不能说当天发生；旧 activity 原文与旧日期保持原样。
numeric aggregates 按习惯、类型、单位分别汇总，不能把分钟与次数、未知单位与毫升相加。
无记录是未知；不能推断没做、身体恶化或改善。

继续页面使用返回 cursor，并保持相同日期、视图、kinds、habit_id，offset保持0；
cursor 绑定用户与冻结快照，不自造／修改。新写或更正不会把已浏览的同一分页快照挤乱。
若要最新状态重新从第一页查。跨用户／参数不匹配 cursor 是错误，不绕过过滤。

更正必须用户当前明确要求。读取目标记录 ID 与当前 revision，摘 source_quote 和 reason，
使用当前 correct_record request_ref，调用 honc_correct_life_record。
request 至少 request_ref/source_quote/record_id/expected_revision/reason。
habit 数字替换用 corrected_value，原单位保持；corrected_unit不能把旧值偷换成另一单位。
text／diary 用 corrected_text；body 用 corrected_observations，每条原词来自当前更正消息，未知仍未知。
selection 用 corrected_selection_values 替换具名计数，标签逐字来自当前更正原文并符合原选项。
时间用 corrected_time 精度协议。撤销用 void=true，不能同时提供替换字段。
不能更正配置对象；习惯设置用 honc_configure_habit。日记的关联打卡由同一事务同步更正／撤销。
原版本不删。APPLIED／ALREADY_APPLIED 才确认；CONFLICT 重读当前版本，UNKNOWN 查原回执，
NOT_FOUND 不猜记录 ID。查询旧记录不会授权重新复制为新事实，也不会修改 Graph 工作状态。
