---
name: honc-wake-bedtime
description: 明确起床开始一天或准备睡觉时记录事实，推进同一提醒实例
---

# 起床与睡前

用户明确当前「起床了」「开始今天」「准备睡觉了」才调用 honc_record_anchor。
「明天五点起床」「如果早起」「想早点睡」「他说起床了」是计划／假设／转述，不写事实。
先 honc_get_life_context，取 record_anchor 引用；request={request_ref,source_quote,kind,time?}。
kind 为 wake（已起床）、day_start（明确开始今天）、bedtime（现在准备睡觉）。原句逐字保存。
没有用户报告时间，time precision=unknown；后端单独保存实际收到时间用于当前实例推进。
用户说「五点多」用 approximate 与原始 time_text，不猜05:00；确切时间带时区和exact精度。

早于08:00的明确 wake/day_start 可推进同一天晨间提醒；早于21:30的明确bedtime可推进同夜提醒。
实例 ID 和额度不变：先发过早起提醒则08:00不再发；先发过睡前提醒则21:30不再发。
默认每实例一次，只有明确次数设置可变。晚于兜底不意味着补催；错过窗口自动过期。
计时器08:00触发提醒不证明用户醒了，不写起床事实；只支持这两类情境，无厕所／休息自动锚点。
记录成功只说事实已保存；NOT_SENT／QUEUED／UNKNOWN 不能说提醒已送达。投递走 Hermes 原队列。
日记写入详见 honc-diary；身体记录详见 honc-body-tracker；不要主动问身体变化。
