---
name: honc-life-settings
description: 增改暂停恢复退休习惯和提醒设置，使用版本检查及明确发生实例规则
---

# 生活设置

用户明确要求修改后，先 honc_get_life_context，取得当前 configure_habit／update_settings 引用和版本。
不要将「我有哪些习惯」「能不能提醒」当作已授权配置。source_quote 逐字来自本消息。

新增：honc_configure_habit(request={request_ref,source_quote,action:"create",definition,reminder?})。
definition 至少 name、record_type，类型 boolean/count/quantity/duration/text/number/selection。
quantity 必须 unit，duration unit 只能 second/minute/hour；number 可保留旧未知单位。
target_value 为正数，target_period 为 day/week；text 不设数值目标，diary 只能 text。
aliases 保留已有名称，selection_options 仅 selection 使用。没有提醒需求可不传 reminder。
reminder 示例：
```json
{"enabled":true,"count":1,"importance":"normal","recurrence":"daily","slots":[{"key":"afternoon","trigger":"time_window","start":"15:00","end":"16:00"}]}
```
窗口包含开始、不包含结束；跨午夜可以。固定时间使用 trigger=fixed_time 与 fixed_time。
起床／睡前使用 trigger=wake/bedtime，不混 fixed_time/start/end；不设置厕所、休息情境触发。
count=0 不发，默认1；count>1 必须每个 slot 给数量匹配、顺序明确、窗口内的 send_times，不能凭重要度添次数。
weekdays 时给 weekdays（周一0到周日6），daily 不给。slot key 稳定，不为重发而换 key。

修改：action=update，habit_id、expected_revision 必须当前值，definition_patch／reminder_patch 至少一个非空。
例如只改名称 definition_patch={"name":"新名"}；只改重要度 reminder_patch={"importance":"high"}。
保留未改字段。pause/resume/retire 使用同工具，仅 ID、版本、动作，不能混 patch。
retire 保留历史与旧回执；不可删除数据库。暂停立即停未投递提醒，恢复不重置当天已用额度。
未开始实例可采用新设置；已发送和不确定投递不能重置或当作未发重来。

全局：honc_update_life_settings(request={request_ref,source_quote,expected_revision,patch})。
未保存默认 revision=0，取实际返回版本。默认 wake_fallback_time=08:00、bedtime_fallback_time=21:30、
default_reminder_count=1、default_importance=normal、fixed_point_grace_minutes=30（至少1）。
全局默认供新配置使用；已有显式规则单独改。禁止改用户／收件人／时区，禁止身体追问和晚间追催。
APPLIED 才确认修改；CONFLICT 重读并依据同一用户意图重新组织 patch，不覆盖他人新变化。
UNKNOWN 查原回执。只有影响用户决定的歧义需补问，其他机械操作自己完成。
