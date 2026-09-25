# Question Orbit Engine 部署到 Wisdom Oldman 的计划

## Topic document delivery extension (2026-09-24)

The Orbit is now an execution attached to a durable topic/question graph rather than the owner of a
standalone answer. Broad topics receive a bounded first-principles frontier, related questions reuse
the topic across sessions, short follow-ups use the originating route, and user focus adds a HIGH
frontier without resetting accumulated budget. The configured automatic default is user-authorized
DEEP; explicit tool calls still cannot self-escalate a budget.

Every preflight answer and completed cycle advances an append-only human-readable topic document.
The loopback UuMA service renders its latest text and history as the default page and offers a
secondary read-only relationship view. Important notifications carry a digest, source URLs, and the
stable local page link. Full Knowledge Map editing and remote access remain outside this extension.

## Runtime reliability completion (2026-09-22)

The deployed Windows runtime now has two complementary tasks: the Runner starts at user logon, and a
one-minute repeating Watchdog starts it only when the exact profile-scoped process is absent.
`MultipleInstances IgnoreNew` and the runner's cross-process lock preserve the single-runner
invariant. Deployment starts the Runner by default, allows operation on battery power, does not stop
it when power changes, starts missed runs when available, and retains failure restart settings.

A production recovery drill terminated the exact two-process Python runner tree, observed zero
remaining runner processes, and then observed automatic recovery at the next scheduled minute. The
recovered state contained two Python shim/runtime processes in one runner tree. A separate
`orbit-runner-lifecycle.log` records launcher starts, normal exits, and launcher errors without
requiring administrator access. Windows rejected enabling its system-wide Task Scheduler Operational
channel from the limited user context; enabling that optional OS channel still requires an elevated
administrator command and is not required for runner self-healing.

Final regression after hardening: 176 tests passed with the existing third-party Pydantic warning;
Ruff, all four deployment PowerShell parsers, `git diff --check`, the live acceptance report, and the
current singleton task state passed.

## Deployment completion evidence (2026-09-21)

The Phase 1 Question Orbit Engine is deployed and enabled for Wisdom-Oldman. The per-user hidden
Scheduled Task now resolves packaged-app LocalAppData redirection to the same physical `wisdom.db`
used by the Knowledge MCP, holds a cross-process singleton lock, removes only exact profile-scoped
orphan runner processes during reinstall/uninstall, and preserves all knowledge and Orbit history.

A controlled production acceptance Orbit recovered the same expired Cycle at attempt 2, ingested
two public RFC sources, created 40 located evidence records, delivered FIRST_USEFUL_ANSWER and
BUDGET_EXHAUSTED notifications to the originating Telegram route, and terminated at the QUICK token
budget. The event chain remained valid, no claim was accepted and no Patch was applied automatically.
After restoring Docker Desktop from one stale socket (moved to a timestamped backup), OpenSPG/KAG
replayed all 440 pending jobs: projection watermark 596/596, lag 0, 456 jobs APPLIED.

Verification: 172 tests plus 5 subtests pass; full source/test/script Ruff, PowerShell syntax, and
`git diff --check` pass. Wisdom exposes 40 Knowledge MCP tools, the runner task is active with one
runner tree, and `UUMA_QUESTION_ORBIT_ENABLED=true`. The repository mission gate intentionally
remains `verification / pending_review` until the separate user/Orchestrator review boundary.

## 实施状态（2026-09-21）

第一阶段已在当前主机部署并启用。`wisdom.db` 持久化 Orbit、可解释前沿、Cycle 租约／
心跳／三次恢复、发现用量和通知 outbox；独立 `uuma.orbit_runner` 由隐藏的用户级 Windows
Scheduled Task 在登录时启动，全局只租用一个研究 Cycle。Knowledge MCP 提供问题预检、
启动／复用、状态、列表、前沿、暂停、恢复和停止，Direct Run 预检继续在模型之外绑定
UuMA task/run 与原会话路由。

发现顺序已实现为用户 URL、OpenAlex、Crossref、配置的 RSS／Atom／站点地图，以及存在
本机密钥时才启用的 Brave Search。抓取器逐跳验证 DNS 和重定向，阻止私网／保留地址、
超限内容、错误 MIME、DOCTYPE／ENTITY XML、登录、付费墙和 CAPTCHA，并遵守 robots、
主机限速与 Retry-After。Brave 保持每月 950 次硬上限。重要事件通过持久 outbox 调用
Hermes `send` 返回原平台／chat／thread，失败最多尝试三次。

当前 Wisdom profile 的 `UUMA_QUESTION_ORBIT_ENABLED` 为 `true`，Scheduled Task 正在运行；
新环境的部署参数仍保持显式 opt-in，避免未安装 Runner 时误建队列。所有变化继续进入
hash-chain `knowledge_events`，新知识只形成候选，Wisdom 不能自行批准 Patch 或提高预算。
CopyCat Gemini Deep Research、XHS 只读采集和 Knowledge Map UI 仍属于后续阶段。

## 概要

把 Question Orbit Engine 实现为 Wisdom-Oldman 的持久化后台研究子系统。

- Wisdom 收到问题后先查询 KAG；若判定为调查型问题，且知识满足度为 INSUFFICIENT 或 PROVISIONAL，并存在值得研究的缺口，则自动启动 Orbit。
- 当前会话先返回已有答案和 orbit_id；后台继续检索、形成证据、扩展问题前沿，直到满足停止条件。
- 第一阶段不增加 UI，使用 Knowledge MCP 查询、暂停、恢复和停止。
- CopyCat Gemini Deep Research 与 XHS 采集推迟到第二阶段；第一阶段只预留受控采集器接口。

## 核心实现

### 状态与知识边界

在 wisdom.db 中增加事件化投影：

- QuestionOrbitRecord：根问题、研究目标、关联 UuMA task/run、预算、状态、满足度和停止原因。
- FrontierItemRecord：关联问题与缺口，保存相关性、不确定性、影响、创新性、成本、优先级档位及理由。
- OrbitCycleRecord：每轮选择的问题、KAG 水位、检索请求、采纳来源、证据、生成的新问题和继续／停止判断。
- DiscoveryUsageRecord：按提供商、Orbit 和月份记录调用量。
- OrbitNotificationRecord：待发送、已发送、失败和去重信息。

沿用现有 QuestionRecord、GapRecord 和 ResearchRun，仅添加带默认值的 orbit_id、当前问题、循环次数和搜索用量字段，保持旧记录兼容。
所有改变进入现有 hash-chain knowledge_events；OpenSPG/KAG 仍是可重建投影。新结论只生成候选知识或 Patch，只有 Orchestrator／用户审查才能应用。

### 语义接口

新增 Knowledge MCP 操作：

- knowledge_question_preflight：KAG 回答、调查分类、满足度判断，并在符合规则时原子启动 QUICK Orbit。
- knowledge_orbit_start
- knowledge_orbit_status
- knowledge_orbit_list
- knowledge_orbit_frontier
- knowledge_orbit_pause
- knowledge_orbit_resume
- knowledge_orbit_stop
- knowledge_orbit_set_budget (explicit user/Orchestrator review only)

这些接口只暴露问题、证据、前沿和状态语义，不暴露 SQLite、Brave 或其他供应商原始 API。
新增 wisdom-question-orbit skill；更新 Wisdom SOUL、技能白名单和 Hermes 部署脚本。uuma_control_guard 的 Wisdom 预检改用 knowledge_question_preflight，并在模型之外绑定原始会话、UuMA run 和通知路由。

### 自动启动与前沿选择

仅在以下条件同时成立时自动启动：

1. 输入被结构化分类器判定为调查、比较、因果、机制、趋势、冲突或证据型问题。
2. KAG 满足度为 INSUFFICIENT 或 PROVISIONAL。
3. 至少存在一个有明确价值理由的知识缺口。

问候、控制命令、简单事实查询和 KAG 已充分回答的问题不创建 Orbit。相同规范化根问题复用已有活动 Orbit，避免重复研究。
前沿按 HIGH → MEDIUM → LOW 选择；同档依次比较相关性、影响、不确定性、创新性、较低成本、创建时间和稳定 ID，不使用一个不可解释的全局加权分数。

## 后台运行与信息来源

### Orbit Runner

增加独立 uuma-orbit-runner，通过 Windows Scheduled Task 在登录时隐藏启动：

- 全局最多运行一个研究循环，其他 Orbit 排队。
- 每个 Orbit 使用数据库租约、心跳和幂等 cycle key；进程重启后从最后完成的 Cycle 恢复。
- 可恢复错误最多重试三次；用户停止和安全阻断不自动重放。
- 每轮执行：KAG 重查 → 选择前沿 → 来源发现 → 安全抓取 → 版本化入库 → 证据／候选知识形成 → 满足度复评 → 更新前沿 → KAG 同步 → 必要通知。
- 提供 UUMA_QUESTION_ORBIT_ENABLED 总开关；关闭 Runner 不删除状态或历史。

### 预算与停止条件

默认自动启动 QUICK，采用以下预算：

- QUICK：10 分钟、10 个来源、50k 模型 tokens、最多 20 次 Brave 查询。
- STANDARD：60 分钟、30 个来源、250k tokens、最多 75 次 Brave 查询。
- DEEP：6 小时、100 个来源、1M tokens、最多 250 次 Brave 查询。
- 自动任务绝不自行升级预算；用户或 Orchestrator 才能恢复为更高档位。

完成条件为满足度达到 SUFFICIENT／STRONG 且没有 HIGH 前沿；其他终态包括用户停止、预算耗尽、无可用来源、需要登录／CAPTCHA、持续失败。

### 第一阶段信息来源

按以下顺序使用：

1. Wisdom KAG、全文索引和已摄取资料。
2. 用户明确提供的文件和公开 URL。
3. RSS/Atom、站点地图及已摄取文献的引用链接。
4. OpenAlex 和 Crossref 学术元数据及开放获取位置。
5. Brave Search 作为通用发现补充。

OpenAlex 支持无需密钥的基本免费查询；Crossref 公共接口无需注册，并按返回的限流信息退避。参考文末来源 1 和 2。
Brave Search 仅使用 Search 方案的月度免费额度。计划制定时，价格为每 1,000 次请求 5 美元，并提供每月 5 美元免费额度。系统设置每月 950 次硬上限，不进行付费超额调用。参考来源 3 和 4。
不持久化完整 Brave 响应或未采纳的摘要；只记录查询审计、用量、提供商请求标识，以及实际选中并独立抓取的公开来源。

### 自主抓取要求

- 遵守 robots、主机限速和 Retry-After。
- 逐次验证初始 URL、每个重定向和最终地址，阻止私网、回环、保留地址、嵌入凭据和非 HTTP(S) URL。
- 保持 20 MiB、超时和允许内容类型限制。
- 不绕过付费墙、登录、验证码或访问限制。
- 按规范化 URL、DOI 和内容摘要去重，并保存抓取时间、位置和版本。

## 重要变化通知

只通知以下事件：

- 首个有用答案。
- 主要结论发生实质变化。
- 出现关键证据冲突。
- 需要用户决定、登录或处理 CAPTCHA。
- 完成、预算耗尽或失败。

Hermes 插件在模型之外捕获原始 profile、平台、chat 和 thread 标识。Orchestrator 所属通知派发器读取语义 outbox，并调用对应 profile 的 hermes send 发回启动会话；Hermes 官方支持脚本化一次性发送，见来源 5。
发送失败最多重试三次并保留待处理记录；不得静默改发主频道。凭据、Bot Token 和 Cookie 不进入 wisdom.db。

## CopyCat 与 XHS 第二阶段边界

第一阶段只定义 DiscoveryProvider 和 DiscoveryArtifact 契约，不执行 CopyCat 或 XHS：

- CopyCat 继续由 Orchestrator 独占；未来只允许调用已审查、健康且允许回放的 gemini_deep_research_collect 动作。
- CopyCat 遇到登录、验证码、页面变化或不确定点击时暂停等待人工，不允许 Wisdom 直接控制 GUI。
- XHS 未来由 Orchestrator 的只读适配器执行；禁止点赞、评论、收藏、发布或账号修改。
- XHS 数据标记为易变的用户生成内容，保存帖子／作者标识、URL、发布时间和采集时间，不能单独支撑高风险事实。
- CopyCat/XHS 输出必须转成带来源清单和内容摘要的 DiscoveryArtifact，再经 Wisdom 正常摄取，不能直接写入知识图谱。
- 接入 XHS 前必须取得有效、可审查的仓库或现有 MCP 契约。目标仓库为 alandelone/multimode_data_process_xhs，见来源 6。

## 部署与验证

### 部署安排

- 扩展 Hermes 部署脚本，安装新 Skill、配置 Runner、Brave key 引用、Hermes API／发送能力和健康检查；密钥只保存在本机环境或 Hermes secret 文件。
- 以加法方式升级 wisdom.db；升级前备份，回滚时只停 Runner 和撤销路由，不删除事件或研究状态。
- 当前仓库保持 verification/pending_review；实现完成后把新证据追加到当前验证 Gate，只有 Orchestrator／用户审查才能通过 Gate。
- 实施过程遵循 UuMA managed session：启动或恢复 session、包装命令、生成最新 handoff，并在最终交付前通过 close。

### 测试覆盖

- 旧数据库升级、事件链验证和投影重建。
- 自动启动正例、简单问题不启动、重复问题复用 Orbit。
- 父子问题可追溯、前沿排序、停止条件与显式预算升级。
- Runner 崩溃恢复、租约互斥、取消、三次重试和幂等摄取。
- Brave 月度／单 Orbit 限额、429／配额耗尽及免费来源降级。
- OpenAlex、Crossref、RSS、站点地图和引用追踪使用完全伪造响应；常规测试禁止实时网络。
- 重定向 SSRF、私网地址、超大内容、错误 MIME、付费墙和 CAPTCHA 阻断。
- 重要事件通知、去重、原会话路由和失败 outbox。
- 候选知识不能自动接受，Wisdom 不能直接调用 CopyCat、XHS 或外部消息工具。
- 部署与卸载脚本、技能白名单和总开关。

### 验收场景

一个知识不足的调查型问题在首轮返回已有答案与 orbit_id；Runner 重启后继续研究，摄取至少两个独立来源，生成完整证据轨迹，在原会话发送重要更新，并在满足度达标或预算耗尽时终止，全程不自动批准候选知识。

## 参考来源

1. OpenAlex API https://help.openalex.org/api/
2. Crossref API 访问与认证 https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/
3. Brave Search API https://brave.com/search/api/
4. Brave 免费额度说明 https://api-dashboard.search.brave.com/documentation/resources/help-feedback
5. Hermes CLI 命令参考 https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/cli-commands.md
6. XHS 目标项目 https://github.com/alandelone/multimode_data_process_xhs
