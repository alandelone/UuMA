# honc 生活模块运行与维护协议 v1

日期：2026-10-14，Asia/Kuala_Lumpur。适用现有 Hermes/honc，沿用原 Agent loop。
功能说明与验收入口：`docs/reviews/honc-architecture-2026-10-13/live-setup-review.zh-CN.md`。
本文件不批准 UuMA 全局 gate；mission_status.json 仍是该状态的唯一来源。

## 启动边界

`uuma.honc.mcp --life-config <honc profile/plugins/honc_life/runtime.json>` 在原 honc-execution
服务注册10个生活工具，与9个原工作语义工具同服。旧 honc_check_habit 不在已部署 include 清单，
其自动创建习惯及默认数量写入路线不能用于本功能。uuma-worker 仍仅5个控制运行工具。
两个服务的 resources/prompts 使用 Hermes 原生 tools.resources=false、tools.prompts=false。
工具名、系统提示和 Skills 在新运行实例／会话边界加载，不改正在运行回合的系统提示缓存。

原 Hermes skills 工具集包含 skill_manage；honc_life 宿主 hook 拒绝它的执行，
同时拒绝任意 cron、连接管理、终端、代码执行、文件修改、委派与 kanban 写入。
skills_list／skill_view 保留，生活管理使用后端语义工具。两项区别应在权限验收中分别记录：
不声称 skill_manage schema 不存在，必须实际验证调用被宿主阻断。

## 可信输入

插件在 pre_gateway_dispatch 核实 honc 私聊平台、现有绑定 owner/chat、消息ID和网关授权。
即使该 hook 发生在网关主授权判断之前，也调用同一个网关授权检查，不将收到消息等同已授权。
语音保留已验证 envelope，后续仅绑定该条实际转写。内部、bot、委派与 cron 消息不能冒充用户事实。
本地 CLI 使用当前 OS 用户直接输入；已有 Hermes cron 环境与父会话标记阻止调度／子代理伪装。

pre_llm_call 创建当前 turn 的随机 capability，数据库只存散列，有效期2小时；新 turn 撤销旧上下文。
当前 source/request refs 注入临时上下文，pre_tool_call 覆盖模型提供的 context_ref。
用户、profile、session、消息来源、操作类型都在事务内再次检查。
来源接收器与 owner/收件人设置不是模型工具。查询没有副作用授权；计划和假设不成为完成事实。
明确报告按句分离授权，一个未来运动计划不应抹掉同消息真实身体报告；现有习惯名称与别名来自后端。
Hermes模型负责理解实际意图和构造语义参数，hook 不另建语言解析／对话框架。

## 读取与写入

总览是简短习惯索引。打卡直接传 habit_name 或索引 object_id 到 honc_get_life_context，
返回单一习惯的定义和实例，补记同时给 business_date。多时段复制对应 instance_id、habit_revision。
实例保留定义快照；日后单位修改不能重释旧事实。不得根据长输出被裁剪而猜ID或再次问已明确的时间。
已声明单个习惯与时段时，先读精准上下文，不搜索会话、资源或自造 MCP prompt。

写入使用当前 request_ref、逐字 source_quote。每消息每域一笔原子操作，多个习惯为1—8条 entries。
同引用相同参数返回同记录与回执，修改参数与已经提交的引用冲突；事务未提交的输入错误可补齐原请求。
APPLIED／ALREADY_APPLIED 才确认，UNKNOWN 查原操作，不换引用重写。CONFLICT 重读版本。
身体细节来自原话，数值评分和标度必须显式提供；没有细节不发追问。
日记原文和唯一日记习惯打卡同事务；更正／撤销关联事实同事务，历史不删。
独立身体消息不结束工作回合；工作 Graph 的身份与规划权限沿用原边界。

历史 effective 用最新有效版本，audit 返回版本链。签名 cursor 绑定 owner、过滤条件和版本截止点，
同快照续页不会因相同时间的新写或更正而重复／跳过记录。未知发生日按明确标记的记录日检索。
数值统计按习惯、类型、单位分开；周目标以 KL 周一到下周一聚合有效事实，未知单位不可混加。

## 提醒事务与投递

compile_day 生成稳定 owner/habit/slot/business_date 实例；修配置不换ID重置额度。
未开始实例采用新配置；已用额度、原投递回执和不确定尝试继续保留。
参数在配置事务内验证，不能存入乱序或窗口外发送时间后才把定时器跑坏。
明确提前起床／睡前推进同实例，无聊天时仍可08:00／21:30兜底，不伪造事实锚点。
窗口含开始不含结束，固定点默认30分钟；过期不晚间补催。同刻合并通知，每成员各消耗1次额度。

先 BEGIN IMMEDIATE 原子预留、创建 fence 和租约；在投递边界复查 fence、完成情况与配置。
原生 execution ID 在外部交接前写入 honc.db；短本地 enqueue 在最后事务边界内执行，网络投递由原队列完成。
QUEUED／SENDING／DELIVERY_UNKNOWN 保留预留，重启只查原 native ID，不重新创建发送。
DELIVERED 才消耗已投递计数；原生 failed 可能已有网络效果，保持 UNKNOWN。
原生 suppressed 终止该次，不当成可重试失败。策略层未发的完成／暂停抑制可在显式更正／恢复后重新判断。
备用工作者丢失 fence 不能发送。只在证明未发生外部效果时释放并允许重试。

新增的唯一调度是 honc profile 的 no_agent 每分钟检查脚本，存于该 profile/scripts。
空 stdout 使外层检查安静，不跑模型，不产生额外消息；真正到点的冻结业务通知只入原生队列。
现有单一共享网关扫描每个 profile 的独立队列，并使用对应已连接适配器。不能再启动第二个 honc bot poller。
网关离线或错过窗口按规则过期；不能承诺断网后通知仍即时送达。

## 安装、切换与恢复

安装器 uuma.honc.life_setup 限定现有 profiles/honc 和 honc.db，要求已存在的单一私聊绑定。
先备份本次拥有的 config、SOUL、9份Skills、插件和脚本，使用 SQLite backup 一致复制 honc.db。
模型配置和 .env/auth 凭据按散列核对不变；不重写凭据，不运行含旧默认token的部署脚本。
初始化已接受默认设置一次；再次安装保留用户修改，不覆盖已有默认版本。
原8习惯由显式 CONFIGURATION_IMPORT 来源迁移，禁止借配置导入授权伪造身体或打卡事实。
旧JSONL保存原行、原ID、原日期和文件散列；原文件不动。旧未知单位、未知属性不猜。

新原生任务先暂停；独立启动核验插件、19+5工具、平台能力和宿主阻断。
现有网关空闲后走官方 pause-for-update 排空／退出及 gateway start，不杀相关或无关进程。
若多 profile 连接超过探针等待时间，只延长观察并核对原启动PID，不再重启一遍。
启动完成后才启用唯一调度，并查原生最后执行结果与真实 honc.db 状态。
生产事实不能用于验收填充；真实模型评测在隔离 owner、profile和数据库里，使用原生产模型与相同工具。

恢复：先通过原生 pause_job 暂停安装回执中的新任务，按 backup_manifest 只恢复拥有的路径。
保留新增记录／版本／操作回执；不将旧 honc.db 覆盖到已产生新用户事实的数据库。
原始迁移缓存和日志不删除，其他 profile、Wisdom知识库与 Hermes state.db 不用作本模块控制数据。

## 最终实测与运行边界（2026-10-14）

当前聚焦回归264项、21个R1-R4场景全部通过，手册JSON示例按实际输入模型验证。
原有生产模型 gemini-3.8-flash / antigravity-oauth 在隔离 Hermes CLI 配置上完成8个实际场景：
27次模型API调用、18次工具调用。最后的部分成功场景出现2次控制结果参数校验错误，
模型自行纠正后完成汇报；身体事实只提交一次，不存在的习惯未创建。保留实际错误、
最终回复、操作ID、持久化内容及耗时，不能写成全程零错误。未切换强模型。

实际共用网关PID11784、honc Telegram connected；唯一原生提醒任务3381ec71b9d2
已启用，连续自动tick成功且外层静默。重载探针原90秒等待不足以覆盖多个profile连接，
后续官方状态证明原启动已完成，因此没有再次重启。隔离队列测试使用fixture发送回调，
本次没有人为发送测试Telegram；真实到点投递回执仍由正常运行产生。

最终插件安装版与源文件AST一致（仅格式差异），托管SOUL区与源一致，9份手册逐字一致。
实际MCP读取隔离域状态并确认同一隔离控制库中的8个真实Direct Run。详见最终源码状态审计、
生产模型回执和综合验证文件。历史foundation126项/设计检查文件保持为当时的历史证据。
