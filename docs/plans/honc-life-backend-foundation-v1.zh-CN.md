# honc 生活后端组件 v1：开发接入手册

日期：2026-10-13。这是已实现组件的手册，不是上线后的 Skill。
总体方向遵循 [现有 Hermes 架构设计](honc-agent-tool-architecture-2026-10-13.zh-CN.md)，
完整目标见 [语义工具合同](honc-life-tool-contracts-v1.zh-CN.md)。本文明确这批可调用范围和差距。

## 1. 模块与事实归属

- `src/uuma/honc/life_models.py`：严格字段、操作参数、时区／时间精度、单位、结果与提醒快照。
- `src/uuma/honc/reminder_policy.py`：纯规则判断／分组／提前锚点；不会保留次数或发送。
- `src/uuma/honc/life_store.py`：复用 HoncStore 的连接，增加独立生活表和 append-only 防护。
- `src/uuma/honc/life_service.py`：当前消息授权、原子业务写入、版本冲突、回执与历史。
- `src/uuma/honc/life_mcp.py`：向既有 FastMCP 实例注册 9 个语义工具；无默认身份、环境回退或新进程。

`LifeStore` 要求传入指向 `honc.db` 的 `HoncStore`。旧 `honc_schema_migrations` 保持原版本，
新 `honc_life_schema_migrations` 自己记版本。禁止传入 Hermes state.db、uuma.db 或 wisdom.db；
不可先用 HoncStore 初始化那些库。未生成新会话入口前，不实例化真实用户数据库来试用组件。
生活服务不更新 rounds、execution_events、任务 Graph、控制状态或知识声明。

## 2. 可信入口和模型参数的边界

入口是未完成的集成工作，不能用模型参数模拟。接入者必须完成如下顺序：

1. 从真实传输入口核实用户、profile、session 和不可变的消息 ID。排除 assistant、cron、引用文本和其他 Agent 输出作为授权来源。
2. 构造 `LifeService(store, owner_id=..., profile=..., session_id=...)`。这些值来自宿主，不来自工具调用。
3. 入口调用 `receive_user_message(adapter_id, source_event_id, raw_content, received_at, granted_operations)`。
   `granted_operations` 默认空元组；核实用户授权以后才加入 configure_habit／update_settings／record_habit／record_body／save_diary／correct_record。
4. 服务持久化 source_ref，并为各领域产生一个 request_ref。同一实际消息重放返回同一引用；内容、会话、时间或授权发生变化则拒绝重用该消息 ID。
5. 宿主使用 `bind_source(source_ref)` 生成当前消息独立的服务实例。不得跨并发请求修改共享对象的当前消息。
6. `register_life_tools(existing_server, service_provider)` 的 provider 必须返回当前调用绑定的实例。
   注册函数本身不认证 Hermes 消息。禁止暴露 receive_user_message／bind_source 为模型工具。
7. 模型先读取 `honc_get_life_context`，只能使用该上下文返回的当前领域 request_ref。

同 request_ref、同参数返回 ALREADY_APPLIED 和原 ID；同引用、不同参数返回 CONFLICT。
未提交的校验失败不消耗引用。多个真实消息表达同样的文字仍是不同来源，不能按原文 hash 合并。
当前每个消息／领域只允许一次原子操作，不能由模型自由生成事实序号来领取更多引用。

## 3. 已注册接口与参数

写入工具均以严格对象 `request` 作为参数。未定义字段会被 MCP／Pydantic 拒绝。

| 工具 | 输入与用途 |
| --- | --- |
| honc_get_life_context | 无模型身份参数；读配置、习惯版本、当前 request_refs |
| honc_configure_habit | HabitConfigureRequest：request_ref、source_quote、action；创建提供 definition 和可选 reminder，旧项提供 habit_id／expected_revision，更新用 definition_patch／reminder_patch |
| honc_update_life_settings | SettingsUpdateRequest：request_ref、source_quote、expected_revision、非空 patch |
| honc_record_habit | HabitCheckinRequest：request_ref、1–8 个 entries；每项有 habit_id／habit_revision／outcome／source_quote，其他字段以 schema 为准 |
| honc_record_body | BodyRecordRequest：request_ref、source_quote、observations；可选 time／related_record_ids |
| honc_save_diary | DiaryRecordRequest：request_ref、source_quote、content；可选 diary_date／linked_record_ids |
| honc_correct_life_record | RecordCorrectionRequest：request_ref、source_quote、record_id、expected_revision、reason；选择 void 或与原 kind 相符的 corrected_* 字段 |
| honc_get_life_operation | operation_id／request_ref 二选一；按当前用户查已提交回执 |
| honc_get_life_history | record_id 或完整 start_date／end_date；view effective／audit，limit 1–100、offset 非负；返回 next_offset |

配置 patch 经过完整对象合并后再次验证，未提供字段保留旧值。创建同名活动习惯需要先查看候选，
不会自动覆盖。暂停／恢复／退役产生新版本；退役不可由 resume 偷偷恢复，原历史保留。
未提供 reminder 的新习惯只创建定义，不自动开启日程。多个提醒要求明确独立的 send_times。

settings_revision=0 表示配置尚未持久化，第一次写用 expected_revision=0。
配置中的 revision 由服务增加，不能放在 patch 里。body_followup、nightly_unchecked_habit_chase、
身份、收件人、时区和 importance_does_not_change_count 不开放修改。
单点宽限分钟数必须是正整数；0 会产生空区间，因此返回输入错误，默认仍是 30。

## 4. 写入、时间、修改和恢复失败

各业务写入、记录版本、头版本和操作回执放在同一 BEGIN IMMEDIATE 事务。
数据库约束保证同 request_ref 只有一个回执；独立连接也不能同时插入两个有效结果。
sources、requests、operations、revisions 禁止 UPDATE／DELETE，头指针只用于当前有效版本。

source_quote 必须是当前用户原文的子串。身体 description／body_part／severity_text／change_text
也必须使用原文；服务不生成诊断或趋势。分数需同时给出显式 scale，服务不会自动补分数；
分数与原文数值的完整语义一致性仍需可信入口和真实模型验收，不能宣称机械校验已覆盖所有自然语言。
日记内容必须来自原文，自动改写不在这批接口内。

HabitCheckin 数值按明确单位保存，不做隐式转换。未知数值保留 null；未知时间保留 unknown。
只有 exact 时间接受带时区的 occurred_at；日期和模糊表达不补造分钟。服务的 recorded_at 是另一个字段。
定义的 name／type／unit／target 存在 definition_snapshot 内，因此未来改成小时不会把过去的分钟重新解释。
补记按发生日期查询；无发生日期的记录按入库日期筛选，并明确 range_basis=recorded_date。

当前只接受活动习惯的当前版本打卡，未知 ID 不自动建习惯。未验证 instance_id 返回 INSTANCE_NOT_BOUND；
暂不能据此取消真实提醒。日记暂不会自动生成习惯事实。历史筛选缺少 kinds／habit_id 和稳定 cursor，
当前 offset 不能在并发新增记录时保证跨页快照一致。

修正／撤销追加同一 record_id 的新 revision。不能更改 record kind，不能用生活修正调用改任务或习惯配置。
修正习惯数值仍校验原始 definition_snapshot，第二次修正不会丢掉原版本。
void 与 replacement 字段不可一起传入。已 void 的显式恢复流程尚未实现，不自动重建事实。

| 状态 | 模型下一步 |
| --- | --- |
| APPLIED／ALREADY_APPLIED | 只确认 records 中有回执的事实，保留 ID |
| NEEDS_INPUT | 只针对缺少或冲突的信息澄清，不因此追问身体变化 |
| CONFLICT | 查看当前配置／原操作，不能改 request_ref 偷渡第二次写入 |
| FAILED／UNBOUND_REQUEST | 当前入口没有对应授权；不编造来源，不声明保存成功 |
| UNKNOWN | 仅 get_life_operation 查询；不自动再提交，不猜写入失败 |
| NOT_FOUND 的回执查询 | 缺少回执本身不证明不曾写入，仍保持 lookup_only |

## 5. 提醒规则组件的实际范围

`ReminderOccurrence` 是一个待评估发送时间点的不可变快照，delivery_status 对应当前发送尝试；
配置多次提醒时，后续发送时间点必须由持久实例／尝试服务重新构造快照，共享 consumed_count／reserved_count。
当前纯函数不会自己生成后续时间点，也不提供 exactly-once 的真实投递保证。

- evaluate_reminder 先识别已发送、未知投递、在途和已有保留，再判断完成抑制、窗口和额度。
- 窗口开始包含、结束不包含；显式窗口不再附加 30 分钟。过期的下午实例不能挪到晚上的日记邀请里。
- plan_reminder_groups 按 owner／bound target／due_at 分组，重要度高到低，再按 ID 稳定排序。它不领取额度。
- advance_on_anchor 只接受同用户、同业务日、明确更早的 wake／day_start／bedtime；已有保留或发送不再次提前。
  同一实例 ID 和额度保留，fallback 保存原计划时间；真实锚点认证不是纯数据模型提供的能力。
- 发送失败没有“不曾产生外部效果”的证明时，只查回执；DELIVERY_UNKNOWN 不能盲目重发。

提醒实例事务、预约与真实投递回执、原习惯迁移、Hermes 接入、Skill 与模型 Eval 属于下一批。
完整产品合同和 21 项跨组件提醒场景仍未通过，参见
[第一批 review](../reviews/honc-architecture-2026-10-13/backend-foundation-v1.zh-CN.md)。
