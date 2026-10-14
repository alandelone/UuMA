# honc｜生活能力语义工具合同 v1（拟建）

日期：2026-10-13。状态：接口设计草案；下列新工具尚不存在，不能直接调用。
对应 [架构设计](honc-agent-tool-architecture-2026-10-13.zh-CN.md)与
[运行手册草案](honc-life-runtime-manual-v1.zh-CN.md)。
保留现有工作执行工具；本合同讨论生活扩展和相关历史读取的修正。

## 1. 所有工具共同遵守的规则

### 1.1 身份与可信来源

认证和有效 user/profile 来自运行进程及真实输入入口，不接受模型参数 user_id 来切换用户。
真实用户消息登记 source_ref，关联 sender、channel、profile、session、message_id、原文与收到时间。
工具输出、cron、引用／转发或其他 Agent 不能生成用户授权；拒绝其配置修改／完成打卡路径。
所有读取、修改、回执查找都检查所有者；只知道别人的 ID 不能读取其记录。

写入共同必填 `request_ref`：由可信入口／上下文服务生成并持久保存的本消息操作槽引用。
例如同一消息分配 habit、body、diary 等独立 ref；每个域的多个条目作为一个原子列表提交。
模型不得生成随机 ref、从历史聊天借用 ref、借用另一用户／会话／profile 的 ref。
恢复原操作可查回执；新的用户更正须使用当前消息的新 ref 并引用原记录。

同 ref＋同内容返回原结果，同 ref＋不同内容返回 CONFLICT。
同消息换工具重报相同事实应被来源效果登记拦住；新的事实槽通过来源登记服务分配。
不得只用原文 hash 去重真实不同消息。来自受控批量导入的来源另有迁移专用身份，
不提供给日常模型任意建立可信输入的工具。

### 1.2 时间字段

记录工具共同可选 `time`：

| 字段 | 类型与含义 |
| --- | --- |
| occurred_at | RFC3339 带时区时间或 null；只有明确时间才填 |
| occurred_date | YYYY-MM-DD 或 null；允许只知道日期 |
| time_text | 用户的时间原话或 null，如“昨晚”“刚才” |
| precision | exact／date／approximate／unknown |

后端用可信接收时间和 Asia/Kuala_Lumpur 解析相对日期，检查字段一致性；
不接受模型自行编造的分钟、时区或过去日期。未给发生时间时保存 unknown，
recorded_at 由服务填写。记录时间归集视图需明确标注，不能冒充发生日期视图。

### 1.3 输出合同

所有工具输出 JSON 对象；模型不得从纯文本“OK”推断多个系统都成功。

| 字段 | 必填内容 |
| --- | --- |
| ok | boolean |
| status | READ_OK／APPLIED／ALREADY_APPLIED／NEEDS_INPUT／CONFLICT／FAILED／UNKNOWN／NOT_FOUND |
| effect_state | none／committed／unknown |
| operation_id | 写操作／已分配回执 ID，读取时可为 null |
| records | 实际记录列表，每项含 id、kind、revision、occurred 时间信息；无记录时为空 |
| data | 查询或当前配置内容；写工具可以为空对象 |
| receipt_refs | honc 操作回执、来源引用；相关投递／投影回执另列 |
| next_action | NONE／ASK_USER／READ_OPERATION／RELOAD_OBJECT／REPORT_FAILURE |
| retry_policy | none／lookup_only／retry_same |
| errors | 错误列表，每项 code、field（可为空）、message |

业务写入 APPLIED 与外部同步／提醒投递分开；可增加 `projection_status`、
`delivery_status`，但不能用其 PENDING 否定已经持久提交的事实。
跨域操作分别返回结果，回复聚合可以为部分成功；每个单域调用不返回隐含半提交。
失败不能带貌似成功的假 record_id。ALREADY_APPLIED 返回原 record_id。

参数 schema 严格拒绝未定义字段；单位、枚举、数组大小、日期和版本在服务边界校验。
读取默认 limit 20、最大 100；事实列表最大 8；过长输入返回明确错误，不截断后保存。
这些限额属于拟定工程容量，可以后续调优，不代表用户习惯数量或全年历史被限制。

## 2. 拟建工具目录与精确输入

### 2.1 honc_get_life_context（读取）

用途：在本轮正确定位设置、习惯、单位、版本、实例和来源操作引用。

必填 `purpose`：habit_checkin／habit_config／body_record／diary／anchor／history／settings。
可选：`habit_query` string、`date` YYYY-MM-DD、`include_inactive` boolean 默认 false。
返回该场景需要的最小 data：有效设置与 revision；习惯 id／名称／类型／单位／revision；
候选执行实例；与本消息绑定的 request_refs；时间解释和读回的原始 source_ref。
多个习惯匹配时返回候选和 NEEDS_INPUT；零匹配不自动新建。
body_record 不加载全部习惯和历史症状；单纯历史查询不发放写入授权。

### 2.2 honc_configure_habit（配置写入）

必填 `request_ref`、`action`：create／update／pause／resume／retire。
update／pause／resume／retire 必填 `habit_id` 和 `expected_revision`。
create 不接受既存 habit_id；由服务分配新 ID。

create 必填 definition；update 可提交 definition_patch、reminder_patch 中至少一个：

- definition：name string；record_type boolean／count／quantity／duration／text；unit string 或 null；
  target_value number 或 null；target_period day／week；description string；aliases string[]。
- reminder：enabled boolean；count 非负整数；importance low／normal／high；
  recurrence daily 或 weekdays＋明确 weekday 列表；slots 非空列表。
- slot：key 稳定标识；trigger fixed_time／time_window／wake／bedtime；
  fixed_time 必填 HH:MM；time_window 必填 start／end HH:MM；wake／bedtime 使用对应设置，
  可以明确覆盖 fallback_time；各分支不接受其它触发方式。
- 每个执行 slot 有独立提醒额度；count 不能因为 importance 自动变化。
- count 为 0 表示关闭该规则的主动提醒，习惯仍可打卡；count 大于 1 需有明确发送时刻列表，
  其数量与 count 一致、处于窗口内，不能由模型现场推算补催间隔。

update 的 patch 只改显式提交字段；原配置生成新版本并保留旧版。
pause／resume 只改变启用状态；retire 移出活动清单并保留历史。
单位或记录类型已存在历史时，改变只影响新版本，不能重解释旧数值。
同名 create 返回候选，不擅自复制一项；不在更新中隐式创建新 habit。

### 2.3 honc_update_life_settings（全局设置写入）

必填 request_ref、expected_revision、patch。
patch 允许：wake_fallback_time、bedtime_fallback_time（HH:MM）；
default_reminder_count（非负整数）；default_importance（low／normal／high）。
R1–R4 已接受，拟建设置合同包含已确认的默认政策：suppress_when_complete=true、
missed_window_policy=expire、fixed_point_grace_minutes=30、group_simultaneous=true、
advance_bedtime_anchor=true。实际支持的 patch 字段和修改行为须与
[政策合同](honc-reminder-policy-contract-v1.zh-CN.md)及设置版本一致；此文不修改运行配置。

不暴露修改 user_id、通知收件人、认证信息、数据库路径或 body_followup 的参数。
当前“身体不主动追问”是强制业务规则，不受 importance／提醒模板覆盖。
习惯显式覆盖优先于全局默认；更新默认不改已经发出的提醒或旧记录。

### 2.4 honc_record_habit（打卡写入，拟替代日常入口的旧 check_habit 路径）

必填 request_ref、entries（1–8 项）。每项必填 habit_id、habit_revision、
outcome、source_quote；可选 instance_id、value、unit、text、reason、time。

- outcome：completed／partial／skipped／not_done。
- boolean completed：value 为 1、unit 为 null；不能用未回复推出 0。
- count／quantity／duration：用户提供数量时传非负有限数和匹配单位；
  服务按定义转换明确单位，不从时长猜运动次数。未提供量可以记录发生事实但标明目标未知。
- text：保存用户原文，不用任意填 1 表示内容已存在。
- skipped／not_done：value 为 null；只表示该次明确报告，不作为完成、负数抵消或系统推断。
- “没做”不是“以后停用”；“以后做”不是发生事实。

source_quote 必须与当前来源相符；后端检查习惯存在、版本、时间和实例归属。
instance_id 不明确时允许无实例事实先记入历史，返回关联待处理，不猜早餐／午餐。
所有 entries 验证后同事务保存；一个失败则整个该域调用无提交，错误指向具体条目。

### 2.5 honc_record_body（身体观察写入）

必填 request_ref、source_quote、observations（1–8 项）；可选 time、related_record_ids。
每项必填 description（忠于用户表达），可选 body_part、severity_text、reported_score、
score_scale、change_text；没有说的字段为 null。
明确评分时 score 与 scale 必须同时有效，不能把“有点累”转换成 3／10。
描述可以包括舒服、精神好等正面记录；相关记录必须同用户且实际存在。
本工具没有“安排追问”“诊断”“健康建议”等输出副作用。

### 2.6 honc_save_diary（日记写入）

必填 request_ref、content、source_quote；可选 diary_date、linked_record_ids。
content 保留用户正文；代理整理的版本只有在用户要求整理时另存派生版本，保留原文。
服务检查日期和链接所有者。日记保存后关联相应文字型习惯实例，生成同事务打卡引用；
模型不能再调用 record_habit 把同一份日记打两次卡。
包含身体叙述的日记可以与 record_body 的回执关联；同一身体事实不因再次 save_diary 复制。
修改旧日记通过 correct_life_record，不能 save_diary 悄悄覆盖旧正文。

### 2.7 honc_record_anchor（作息锚点写入）

必填 request_ref、kind wake／day_start／bedtime、source_quote；可选 time。
只接受用户明确报告当前起床、启动当天计划或准备睡觉；后台定时不证明真实锚点发生。
保存锚点事实并调度合资格提醒实例，返回 reminder refs 与 QUEUED 等状态，
不能把排队当作已送达。wake 与 day_start 在同日共用晨间实例身份。
R4 已接受：明确当前提前准备睡觉可提前触发，共用当晚实例额度，21:30 不重复。
未来睡觉计划／引用不消费当前提醒实例；发送成功与事实发生时间仍分开。

### 2.8 honc_get_life_history（读取）

可选 kinds（habit／body／diary／anchor／activity）、habit_id、start_date、end_date、
record_id、limit、cursor、view effective／audit（默认 effective）。
至少提供日期范围或 record_id；日期仅由可信当前时间解释。
返回类型、原话、时间精度、发生／记录日期、有效版本、来源和 next_cursor。
audit 显示原记录及更正链；effective 显示当前有效内容并保留链入口。
数量型按 value／unit 汇总，时长型按时长汇总；“未记录”不能生成失败次数。
身体和日记不进入工作成果列表。未知发生日的记录另列，不能偷偷塞到当天发生记录。

### 2.9 honc_get_life_operation（读取）

必填 operation_id 或 request_ref（只允许其中一个）。
返回持久操作状态、实际 record IDs、错误和下一步。检查当前用户及原来源作用域。
恢复结果 UNKNOWN 必须保留未知；未找到不自动写入，也不被解释成旧操作绝未发生。

### 2.10 honc_correct_life_record（更正写入）

必填 request_ref、record_id、expected_revision、reason；可选 corrected_time、
corrected_value、corrected_unit、corrected_text、corrected_observations、void。
根据原记录 kind 只接受相应字段；void 与其它修改互斥。
保存新更正引用，effective view 更新，原始记录不删除。服务返回更新后的统计。
不允许自动选“最近一条”作为目标；明确 source/report 指向或先查询候选。
配置修改使用 configure_habit；项目 ACTION 反向操作仍走既有 Graph 合同，不能借本工具越权。

## 3. 完整例子（拟建合同）

以下 ID 是明确的软件设计样例，不是真实用户记录；例子不得用于初始化生产资料。

用户「刚才拉伸了二十分钟」。上下文返回：habit_1、revision 2、duration／minute、
request_ref req_h1。本轮发生时间只知道“刚才”。

```json
{
  "request_ref": "req_h1",
  "entries": [{
    "habit_id": "habit_1",
    "habit_revision": 2,
    "outcome": "completed",
    "source_quote": "刚才拉伸了二十分钟",
    "value": 20,
    "unit": "minute",
    "time": {"occurred_at": null, "occurred_date": "2026-10-13", "time_text": "刚才", "precision": "approximate"}
  }]
}
```

```json
{
  "ok": true,
  "status": "APPLIED",
  "effect_state": "committed",
  "operation_id": "op_h1",
  "records": [{"id": "event_h1", "kind": "habit", "revision": 1, "occurred_at": null, "occurred_date": "2026-10-13", "precision": "approximate"}],
  "data": {"habit_name": "拉伸", "recorded_value": 20, "unit": "minute", "target_status": "met"},
  "receipt_refs": {"source_ref": "source_1", "operation": "op_h1"},
  "next_action": "NONE",
  "retry_policy": "none",
  "errors": []
}
```

重复同调用返回 ALREADY_APPLIED 和原 event_h1；不能创建 event_h2。
如果请求没收到结果：调用 get_life_operation(request_ref=req_h1)，
查询得到 APPLIED 才确认；UNKNOWN 则说明暂时无法确认，不重写。

用户「流鼻涕，也有点累」：

```json
{
  "request_ref": "req_b1",
  "source_quote": "流鼻涕，也有点累",
  "observations": [
    {"description": "流鼻涕", "body_part": null, "severity_text": null},
    {"description": "有点累", "body_part": null, "severity_text": "有点"}
  ],
  "time": {"occurred_at": null, "occurred_date": null, "time_text": null, "precision": "unknown"}
}
```

成功后只确认所保存的感受；不注册身体复查 cron。

## 4. 兼容与发布

旧工具与旧记录保持存在，不把“未实施新合同”误写成“旧工具失效”。
实施时建立显式迁移适配：当前 habit_tick／quantity 语义保留，旧 boolean／number
定义需核对单位和目标，不能自动把旧数值变成 duration。

新 profile 在新会话边界采用新生活工具；旧 check_habit 入口是否继续对旧客户可用，
必须经过可信来源和重复写入修正后决定，不能让旧入口绕开新约束。
保留既有工作工具但避免两套生活写入口同时被日常模型看到；具体工具清单以实际模型 Eval
决定，冻结版本并注明生效会话，不能在一轮中临时增删工具。

本合同不是已注册 MCP schema。开发前需要将字段转换成实际严格类型／schema，
并验证手册例子与它一致；不得把文档校验声称为工具调用已通过。
