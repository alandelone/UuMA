# honc Telegram 操作手册与 Graph 核查

记录日期：2026-10-20，Asia/Kuala_Lumpur。

**后续更新：用户已要求并加入明确任务完成的自动 Graph 同步。** 最新规则和实现见
[完成报告自动同步](honc-graph-completion.md)。缺少完成标准时先补标准再勾选，这是用户
明确选择。下文“Project Graph 的实际情况”保留本次最初只做手册时的审计历史；其中地址
和普通完成流程的缺口已在后续任务处理，一般未完成进度仍只存账本。

用户本次提出两件事：确认 honc 记录既有工作时是否会补充 Project Graph；增加一个
Telegram slash 操作手册，方便临时新增习惯、安排休息和记录实际发生的事情。

## 已加入的入口

在 honc 的 Telegram 私聊中输入 `/honc`，查看目录和例子（可直接点击对应命令链接执行）：

| 入口 | 内容 |
| --- | --- |
| `/honc_habits`（或 `/honc habits`） | 新增、修改、暂停、恢复习惯，配置提醒，记录打卡 |
| `/honc_rest`（或 `/honc rest`） | 暂停专注去休息、午休习惯、提醒时间、起床与睡前 |
| `/honc_work`（或 `/honc work`） | 关联已有任务、开始专注、记录进度、结束与核对完成 |
| `/honc_history`（或 `/honc history`） | 补记、查询、更正、撤销、日记和身体记录 |
| `/honc_graph`（或 `/honc graph`） | 哪些记录会进入 Graph，哪些先保存在 honc |

手册由本地固定命令返回，不调用模型，不创建习惯、不记录完成、不修改提醒或 Graph。
要执行例句，需要把那句话单独发给 honc，再通过原有模型与语义工具保存。
原生 `/model`、`/new`、`/stop` 不变。操作指南的最新文字由
`integrations/hermes/uuma_honc_commands/__init__.py` 管理。

## 可以直接发送的例句（Telegram 点击即可一键复制）

指南中的例句均使用 Telegram 原生单行代码格式包裹（轻点即可复制至剪贴板）：

- 新增休息习惯：`新增一个习惯：午休，按分钟记录，不设提醒。`
- 新增定时习惯：`新增一个习惯：伸展，每天15:00提醒一次，按分钟记录。`
- 实际发生后：`记录午休习惯：今天午休了20分钟。`
- 修改提醒：`修改伸展习惯的提醒，改为每天16:00一次。`
- 专注中休息：`暂停当前专注，我要休息一下。`
- 继续专注：`恢复当前专注。`
- 暂停习惯：`暂停伸展习惯。`；恢复：`恢复伸展习惯。`
- 补记：`补记昨天的伸展习惯：昨天做了15分钟伸展。`

暂停专注不累计暂停期间的工时；暂停习惯保留历史并停止未发送的提醒。
休息可以作为习惯，使用固定时间、窗口或指定星期配置提醒。目前情境触发只支持
起床和睡前；“每次休息时自动触发其他习惯”没有实现。
以上是用法示例，本次没有把这些示例创建为用户的真实习惯或记录。

## Project Graph 的实际情况

| 输入／操作 | 现有代码行为 |
| --- | --- |
| 一般工作进度、成果、Next、Blocker、补记 | 追加到 honc 执行账本；返回 `graph_update_status=NOT_REQUESTED` |
| 关联任务的专注开始／结束 | 调用 Graph `focus-events`；现有返回标签本身不证明远端成功 |
| 明确报告任务完成 | 角色流程要求核对目标与 `done_when`，再调用完成决策接口并保存回执 |
| 习惯、身体、日记、起床／睡前 | 写入生活记录；不自动修改 Project Graph |
| 项目层级、里程碑、优先级 | 由 Yonc 管理 |

因此，目前不能认为 honc 会把你每一次提到的旧任务进展自动补入 Project Graph。
“进展已记录”和“Graph 已更新”必须分别报告。

本次只读核查还发现实际连接配置存在缺口：

- honc 的 `honc-execution` 没有配置 `YONC_GRAPH_URL`，代码默认连接 `http://localhost:8000`；
  对该地址的 `/api/v2/health` 检查连接失败。
- Yonc 当前配置指向 `http://127.0.0.1:8766`，该服务健康检查 HTTP 200，
  提供完成决策、回执和专注事件接口。
- honc 的真实账本中没有任务快照、完成评估或 Graph outbox 回执。
  当前 `get_context` 读取的是已有任务快照，没有直接拉取 Graph 节点的实现。
- 本次交付新增手册，保持 MCP、模型、Graph 配置和原有生活调度不变。
  Graph 地址修复、任务读取及普通进展同步仍是后续功能范围，不能当成已经交付。

honc 数据保存在 `%LOCALAPPDATA%/UuMA/honc/honc.db`：工作执行使用执行账本，
生活记录使用同一 honc 专用库中的 `life_*` 表，类型和来源分开。
本次没有向 Graph 写入测试任务、修改真实任务完成状态或发送测试聊天消息。

## 验证与部署记录

新的指南测试校验 honc 专属注册、原生命令保留、只显示不执行、各页长度、
示例通过现有真实消息授权规则、查询不授予完成写入，以及部署保留模型／MCP／凭据原文。
同时运行既有生活手册示例校验。

本次结果：18 项测试通过，新文件 Ruff 检查通过。实际 Hermes 命令注册表已找到
`/honc`，六个页面均可读取；安装副本与仓库源码一致。Telegram default、private、group
三种菜单范围均已读回确认 `/honc` 排第一。原有网关完成启动，honc Telegram 已连接。
模型、MCP、生活配置与原配置比较一致；本次未调用模型、发送测试消息或修改 Graph。
原生验证回执见 `.uuma-local/honc-guide-20261020/native-verification.json`；
Graph 只读核查见同目录 `graph-audit.json`。

部署脚本为 `scripts/deploy-honc-commands.py`；菜单脚本为
`scripts/sync-honc-telegram-menu.py`。备份与只读审计记录在
`.uuma-local/honc-guide-20261020/`。全局 mission gate 保持 verification / pending_review。
