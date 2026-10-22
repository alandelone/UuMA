# 五 Agent 迁移实施状态

## 账号池 worker 最新进度

最新状态见 [有界 worker 与服务器账号池实施记录](pool-worker-implementation.zh-CN.md)。
下文保留早期按时间顺序记录；其中“尚未授权”的描述不代表当前账号池状态。
三个账户已就绪，Brainstormer 试点 worker 已验证；五个生产入口尚未切换。


## 当前结论

已开始实现，尚未完成生产迁移。当前 mission 仍为 verification / pending_review。
服务器的五个 Agent 尚未接管生产入口；Orchestrator、Scholar 和浏览器仍在工作站。

2026-10-21 只读检查发现：当前 profile 指向的生产控制库
`C:\Users\Alandelone\AppData\Local\UuMA\uuma.db` 返回
`database disk image is malformed`。解析后的实际位置在 Codex LocalCache 下。
原 DB、零字节 WAL、SHM 已复制为原始证据并记录摘要；这不是已验证的一致性备份。
未替换、重建或恢复生产控制库。恢复候选必须在独立文件验证，不能用开发会话库替代。

## 已落地的基础代码

| 工作项 | 实际范围 |
|---|---|
| ControlClient | 身份认证、任务/Run/结果/审批 API；远端配置缺失时拒绝本地回退 |
| 远端语义 MCP | Control/Knowledge 的 HTTP 与 stdio 转接；按认证身份隔离子进程，保留现有知识审批 |
| A2A SDK 1.2.3 | 正式 Agent Card/JSON-RPC 路由、Hermes Adapter、任务状态与取消请求 |
| 传输回执 | 原请求摘要、派发收据、未知结果隔离、重复请求复用、旧 epoch 拒绝 |
| 节点绑定 | 与现有 Agent 注册关联，通过原控制事件链保存可信 endpoint |
| 桌面连接器核心 | 操作白名单、权限回查、30 分钟期限、回执去重与不确定结果隔离 |
| 发布引擎 | 固定目标 commit、内容/依赖摘要、真实 gateway 影响范围、停靠钩子和发布回执 |
| 发布接单门 | 在 Run 注册事务中检查接单状态，原控制事件链保留发布停靠记录 |
| 迁移工具 | SQLite backup API、一致性检查、表/行/内容摘要；拒绝覆盖备份 |
| 两节点描述 | profile 分工、端口、SSH 转发脚本、CPU 与预算配置 |

这些基础接口尚不能等同于完整可发布系统。`uuma-release` CLI 当前提供 preview/receipt；
实际 apply 的通用 OS/backend 与 CLI 已接齐，真实服务维护钩子和生产校验仍需完成。

## 仍须完成并验收

1. 用户已明确允许放弃旧 UuMA 控制历史；新控制基线已在服务器建立。接下来核对运行方式并逐项切换，不再等待旧历史完整恢复。
2. 审查现有工作区的发布基线，固定 Hermes、Yonc Graph、eSchematic 的版本与依赖锁；
   engine_versions 已固定四个引擎的来源 commit、含本机修改的源快照摘要与版本包摘要；仍需形成可审查的 Git 发布基线。
3. 验证真实 Hermes /v1/runs 与 guard 对已分配 Run 的绑定，避免额外注册 direct Run；
   生产 Runtime 的身份、持久幂等能力、进度/结果回报、重启与 SSE 重连尚待端到端验收。
4. 实现并接齐受限咨询的实际调度、预算和工具白名单；topology 中的咨询/并发数目前是配置，
   不是已完成的全链路强制约束。
5. 将桌面连接器接到实际 Windows/ChatGPT 工具并挂载认证入口；
   处理 ChatGPT Bridge 自己的控制库依赖，不能继续读取迁出后陈旧的本机控制库。
6. 完成 Linux profile 配置生成、gateway 消息入口分区、服务安装、profile 托管内容合并、
   单组件 apply/回退、模型授权及 Notion/通知等领域依赖。
7. 完成产物上传下载/路径映射、Observatory 节点和版本视图、SOUL/SKILL/权限矩阵的完整对齐。
8. 按控制源、Brainstormer、Yonc/Graph、Honc、Wisdom、Forge 顺序逐项切换和验收。

服务器只读检查：没有 Hermes、agy 或 ~/.hermes；8765/8766/8768/8769/8770 无监听。
新建隔离候选环境用于 Linux 软件检查，不启用生产消息入口，不携带浏览器登录态。

## 本轮验证证据

- Windows：93 项相关检查通过，另 5 项 subtest 通过；新增文件的 Ruff 检查通过。
- Ubuntu 服务器：修正后的隔离候选 30 项检查通过；192 个源文件逐项 SHA-256 核对一致。
- 源候选 ID：`903a9782a761af69d2540709213dd1817e2818ec776f58f15ddfbf7eaedaacdd`。
  它是工作区候选，不是已批准的 Git 发布，`production_ready=false`。
- 服务器证据目录：`~/.local/share/uuma/staging/<候选 ID>/`；包含校验报告、测试结果与解析后的依赖版本。
  依赖环境复用首轮隔离 venv，并重新绑定到修正后的独立源码目录。
- 本机证据：`.uuma-local/distributed-candidates/<候选 ID>/`；原始控制库证据位于
  `.uuma-local/migration-baselines/20261021T070807Z-control-raw/`。
- 找到的有效旧控制库备份是 `backups/chatgpt-bridge-20260922T205816420755Z/uuma.db`，
  含 115 个事件、26 个 Task、26 个 Run。未采用它替换当前数据。
- 首轮 Linux 22 通过、1 失败记录保留在首轮候选目录。原因是测试夹具两次取时间，
  使三十分钟区间多出微秒；改成同一固定时间点，并增加超出一微秒必须拒绝的检查。
- Windows 首轮的缺少 source=direct 夹具错误、Yonc 查询回归失败均已修正。
  Yonc 失败路径曾打开默认控制库并在初始化的 journal_mode 检查处报错；之后的独立只读检查确认
  当前原库及其原始副本连 schema 都无法读取。没有据此重建、替换或恢复原库。
- Windows 控制启动脚本默认端口已改为 8765；配置远端控制时拒绝启动另一本机控制源。
  此脚本未用于启动或重启服务，未纳入 Linux 核心源候选。

## 保留边界

- Scholar 的科研任务保持 PAUSED；46/126 成功窗口与失败历史不恢复、不重试。
- 控制、知识、领域数据库及 Hermes state.db 不混用；未重启现有 OpenSPG/Notion 服务。
- 测试夹具、协议软件验证与实际模型/机器人/离线迁移验收分别记录。
- 所有既有未提交修改保留；本次代码未自动批准阶段门，也未推送或发布。

## 控制库恢复专项记录

用户确认没有较新备份。文件没有丢失：原文件为 1,146,880 字节；恢复完成后复查其
SHA-256 仍为 `d4019ec3143b306a61275ea8af6a1d953f1aedada29aa6ae72d4e78ac6b9e039`，
与保留的原始副本一致。没有覆盖生产文件，也没有把开发会话库当成恢复来源。

使用官方 SQLite 3.54.1 工具，在独立工作副本执行排除 freelist 的恢复。
工具导出的独立数据库结构检查通过，但表归属存在错误：部分事件被放入 tasks 表。
因此初步提取的 62 个任务、80 个 Run 不能直接作为可靠的生产恢复数量；
仅凭 integrity_check=ok 不能据此上线。

随后直接解析副本的数据页，按事件原有算法逐条校验摘要：

- 当前文件找回 323 条摘要正确的事件，最高序号为 428；
- 2026-09-22 备份与当前找到的重叠事件无摘要冲突，可补入 30 条；
- 合计保存 353 条通过逐条校验的事件，仍缺 75 个序号；
- 已找到的相邻事件摘要链接无冲突，但缺口意味着完整事件链尚未恢复；
- 另提取 84 个任务和 83 个 Run 的页记录候选，尚未验证其投影、时效或业务完整性，
  不能据此恢复任务或推断当前接单状态。

证据目录：`.uuma-local/migration-baselines/20261021T080953Z-recovery/`。
`recovery-summary.json` 记录缺失序号和校验结果；`verified-event-fragments.db`
仅保存带来源的事件片段，**不是生产 uuma.db，production_ready=false**。
恢复 SQL、结构恢复候选与页记录单独保留。另一轮同结果的提取目录也保留，未清理。
初次用 Python 解码恢复 SQL 时遇到无效 UTF-8；改由 SQLite CLI 在独立文件载入，
没有以替换字符修改业务内容。中间错误曾输出部分恢复 SQL 到本地命令结果，其中可能含
历史业务链接/令牌；不将该原始输出或恢复数据上传服务器、Git 或共享报告。

当前无法证明全部生产控制历史已恢复，因此控制源切换和依赖其状态的生产发布继续停靠。
服务器的软件验证证据已取回本机；原控制库、Scholar 队列及机器人入口均未切换。

## 用户澄清后的继续实施（2026-10-21）

用户明确表示：旧 UuMA 控制资料可以丢失，真正的 Agent 运行方式不能丢失。
据此取消“完整恢复旧控制历史后才能继续”的实施依赖；原损坏库和恢复片段保留存档，
不再用旧历史阻止新控制源建设。这一授权不用于重置 Wisdom/Forge/Honc/Graph 的领域资料，
也不用于恢复 Scholar 的暂停队列。

已完成的新进展：

- 七个实际运行 profile 的配置、SOUL、技能、插件和文件摘要已存为忽略目录下的私有基线；
  包括 Agent 真正使用的 MCP 名称、工具过滤器、模型和额外配置。没有上传浏览器登入态。
- 新增 node_bootstrap：只在不存在的新目录初始化控制库，保留七个 Agent 定义及权限，
  不导入旧 Task/Run，逐 Agent 暂停接单，生成独立身份令牌和授权回执。
- 服务器 `/home/alandelone/.local/share/uuma/data/uuma.db` 已初始化且通过完整性和事件链校验。
  新任务、Run 都为零。`uuma-control.service` 已启动，绑定 `127.0.0.1:8765`；认证 fleet 查询
  确认 control_owner=server。没有启动机器人接收方，没有设置开机启用。
- 控制 API 支持知识资料尚未迁移时返回明确等待；没有因启动 API 创建空 wisdom.db。
- Hermes 0.21.3 对应的固定源快照（3037 个文件）及 Linux 独立环境已安装，命令界面可启动。
  普通 wheel 安装被 Hermes 拒绝，按其错误提示改为对固定版本目录执行 editable 安装成功。
  第一次下载逾时及 wheel 错误日志保留；未调用模型、登录或启动 gateway。
- Hermes、Yonc Graph、eSchematic、RSTV4 的源快照固定本机修改和 SHA；只有前三者传到服务器。
  RSTV4 源码只读，Scholar 模型、队列和环境仍在工作站。
- CLI apply 与通用 OS 维护接口已实现；预览固定 OS 配置摘要及受影响 Agent/服务，
  检查真实活动工作和暂停环境、固定版本展开、实际版本校验及失败回执。
- A2A Hermes 使用独立 assigned session；guard 向 Worker MCP 核对原 Task/Run/epoch，
  防止再建 Direct Run；逐工具边界重新检查，拒绝暂停和失效执行。
- 浏览器队列在远端模式使用工作站 desktop/chatgpt.db，任务权限从权威控制 API 核对；
  缺少远端控制时拒绝读取陈旧本机任务。原本未配置远端的工作站保留兼容路径。
- workstation_node 在 8770 的一个服务容纳 A2A 与 /mcp 下的 ChatGPT/XHS 语义入口。
  XHS 和 ChatGPT 的 Agent 白名单保留；实际服务尚未在工作站启动。
- 五个 Linux profile 候选已生成，保留模型、角色、MCP 名称、工具过滤器和插件；
  Windows 路径已映射，ChatGPT/XHS 指向工作站。候选仍未切换接单，模型授权尚待完成。
- Wisdom、Honc、Forge、Yonc Graph 分别做 SQLite 一致性备份并通过完整性校验：
  36/23/20/25 个表，共 81167/512/2087/1667 行。只是迁移快照，当前写入者仍在工作站。

最新 Linux 核心候选为 `8cc288db86d224129a10c701018baa4c1755853667322040df6e01dc11fc96c6`，
205 个源文件逐一核对，108 项检查通过。Windows 本轮整合 143 项通过，随后路径修正相关
72 项通过。Ruff 新增/修改模块检查通过；这些不是模型、机器人和离线协作的完整验收。
Linux 的前一候选暴露了 Forge 对 Windows 绝对路径的错误解释；已修正为 Linux 拒绝外来
Windows 路径，并保留目录穿越与大小写边界。原失败证据没有删除或降级断言。

部署配置和权限仍须在真实服务确认。Antigravity CLI 采用官方 manifest 下载并固定版本，
独立服务器登录尚未完成；不复制工作站浏览器登录态或自动改用其他模型。

手动发布用法及尚未接齐的真实 OS 钩子见 `manual-component-release.zh-CN.md`。
五个 Agent 的正式迁移、领域数据最终停写核对、机器人单入口切换、真实咨询预算、
产物/Observatory、手动发布端到端验收仍未完成。阶段门保持 pending_review。

### 后续服务器实证与授权边界

- Git 已建立独立审查分支 `codex/five-agent-migration-20261021T095318Z`，
  初始提交 `1b3cd895b57f471d0f5887af5d692d57bcc92993`，显式纳入 93 个迁移及相关实际行为文件。
  使用独立 Git index，原分支、工作区及原暂存内容保留；阶段门、会话历史和无关 public-access
  工作没有纳入，未推送。该分支是可审查基线，不表示生产发布已获批准。
- 固定提交的初始发布预览已经产生，16 个运行业务组件需要初始化；无定时拉取或自动发布。
- 五个 Agent 的 MCP 程序在 Linux 上分别完成真实 stdio 初始化和工具列举，且各身份能连接
  新控制 API。Worker MCP 列举 92 个原始工具，Knowledge MCP 列举 43 个；profile 的原工具
  过滤器继续限制各 Agent 的实际可用范围。这不是所有工具业务动作或真实模型执行的验收。
- Yonc Graph 在复制出的验证数据库上通过 API 健康检查，读到 691 个节点；没有启动生产
  Graph 监听器或更改工作站 Graph 数据。
- 五份无凭证 profile 候选已上传服务器：327 个文件逐一摘要核对。原 `.env`、auth.json、
  浏览器会话、Git 元数据及缓存没有传输；配置中的凭证字段已替换为服务器待配置标识。
  Telegram 接收方没有启动。
- 四个领域数据库快照及 102 个原始内容文件（10,571,747 字节）已传输并核对为候选副本，
  工作站仍保留当前写入者；正式切换仍须停写并最终同步，不能把早期副本当作最新资料。
- 19 个 BGE-M3 CPU ONNX 及 tokenizer 文件已传输并完成摘要校验，包含原 ONNX 外部权重。
  未改动工作站的共享模型环境，未进行 embedding 推理。KAG 0.8.0 源快照另行固定，
  Linux CPU 环境安装正在进行，尚未宣称知识引擎已就绪。
- Antigravity CLI 1.4.4 已按官方 manifest SHA-512 校验，安装于固定版本目录。
  已生成每次调用前检查二进制 SHA-256 的启动入口，并配置禁用自动更新的环境变量。
  尚未调用模型或完成服务器登录。
- 自动安全审查拒绝了两项操作：一是用真实提示启动服务器模型登录（授权后可能产生模型用量）；
  二是上传包含现有 profile 凭证的配置包（服务器凭证应另行配置）。已分别请求用户确认
  单次 OK 验证及仅五个 Telegram Bot 凭证的搬移，没有绕过拒绝。无凭证配置的传输已完成。
  在用户回复前不进行相关模型调用或凭证搬移；其他准备继续执行。
- 迁移备份工具已改为让新快照使用 DELETE journal 模式，避免复制 WAL/SHM 作为活动状态。
  新检查证明备份独立且原库仍为 WAL、原记录保持不变。此前候选伴随文件保留为历史证据。

KAG CPU 安装下载 jieba 源包时长时间无进展。仅终止了命令和隔离环境路径完全匹配的
本轮 pip 安装进程，保留日志与缓存，并改成服务器上的独立安装作业继续执行。
状态文件为 `~/.local/share/uuma/runtime-envs/kag-cpu-0.8.0/install-status.json`，
作业回执为同目录 `install-job.json`。这项作业只安装依赖，不登录、不调用模型、不启动
机器人；最终 READY 前仍不算知识引擎完成。新一轮备份/配置相关 93 项检查通过；
独立 WAL 快照及凭证移除的 14 项检查通过。完整运行方式仍须在授予模型与 Bot 授权后验收。


## 服务器账户池与授权入口续批（2026-10-21）

用户已同意一次 OK 模型验证，以及仅五个 Telegram Bot 凭证的 SSH 搬移。
五份 Bot 凭证已单独保存于服务器私有目录；接收方没有启动，其他现有模型凭证没有搬移。
此前登录认证超时，没有完成模型调用；不是已经可用的账户池。

新增 Linux 账户池、互斥租约、独立 HOME、受控优先级和状态检查，配套五份无凭证 profile
绑定候选。SOUL 与 MCP 配置摘要未变；Linux 不调用 Windows Anti-Tools 身份切换脚本。
管理页面通过 SSH 转发在工作站访问，服务器仅 loopback8771，工作站18771；独立管理口令，
不开放 Agent 管理入口。页面走原生 CLI 空交互式 OAuth，不发送模型提示。
本机浏览器控制被设置禁用，打开面板只回报 queued；已把完整受保护入口链接交给用户自行打开。

用户首次交互发现 Google 400：client_id 重复。确认原因是终端 OSC8 隐藏 URL 与可见 URL
在 BEL 处没有截断；已修正完整链接解析和重复参数拒绝，22 项 Linux 隔离检查通过，
Ruff 检查通过。修复仅切换管理页面服务，不切换五个机器人或工作站数据。
当前管理页已回到等待操作，仍没有授权可用账户。账户接入和实际模型验证尚待用户完成。
参见 server-account-pool.zh-CN.md；候选、账户池状态和源码摘要回执保存在忽略目录。

KAG CPU 原安装作业已经超过1800秒并退出；旧 INSTALLING 文件是未捕获超时留下的状态，
不能当作仍在安装或已经 READY。环境和日志保留，仍待完成依赖安装及实际 CPU 接口核对。
五个 Agent 的正式切换、领域资料最终同步、桌面连接和手动发布验收继续待办；阶段门未批准。


### 对照 Anti-Tools 后的自动回呼修正

用户实际反馈代贴授权码后一直确认、最终超时。只读检查服务器账户目录：没有 token 文件；
原生 CLI 日志只有 OAuth 开始及未登录错误，没有保存授权的实证。检查本机 Anti-Tools1.17.1
的 startOAuthLogin、addAccountViaOAuth 与 CliIntegrationService：采用 loopback callback、
交换 token、确认 userinfo 身份再登记账户，与旧网页转贴终端的路径不同。

已新增 provider_oauth，改用 Google 官方桌面 OAuth + PKCE/state，经同一 SSH 转发自动回呼；
每个 callback 只消费一次，确认邮箱/身份、拒绝重复主体，按 CLI consumer 格式保存私有授权，
然后由固定 agy models 检查。独立应用设置源于已安装扩充套件的公开客户端配置，未读取或搬移
其任何已存账户凭证。设置在服务器私有 oauth-client.json，不进 Git。独立账户显式隔离共享
D-Bus keyring，保留每个账户自己的 native token 文件。

网页无需复制或粘贴授权码，显示交换授权与检查 CLI 两阶段；允许取消等待。旧 PTY 仅留作诊断，
Enter 输入也从 LF 修为 CR，但生产网页不再依赖这个路径。新版32项 Linux隔离检查通过、Ruff通过；
测试使用假供应商响应，不等同真实 Google/模型验收。实际新回呼链接参数单值、地址与 SSH转发
核对正确，服务已更新。旧失败版本和日志保留；五个机器人和领域数据未切换。

操作入口需带 ?v=callback 重新打开，以加载自动回呼页面。当前已启动 account-01 的新登录等待，
尚未收到 Google callback、尚无保存的授权或可用账户；仍须用户完成真实 Google 同意。


### 首个真实账户接入完成

Google callback 成功并保存账户授权后，CLI仍报未登录。以 strace 只追踪文件路径和连接，
证明固定 agy1.4.4 读取 antigravity-oauth-token，而不是先前插件注释所指的新名称。
保留原授权文件和摘要，在同一账户下绑定正确文件；真实 models 随即退出0并返回模型清单。
程式优先读取原生 CLI 的实际文件名，新 OAuth 直接写该名称；手动检查返回明确成功消息，
更新账户为可用并清除旧失败提示。34项Linux隔离检查、Ruff通过；先前失败证据保留。

按既有用户单次授权，使用原 profile 解析的 gemini-3.8-flash-medium / medium，只执行一次
Reply with exactly: OK，实际输出OK、退出0。私有 approved-model-verification.json 用独占创建
防止重复，历史认证超时记录不重置。没有重跑第二次，没有启动任何 Agent 接收方。
当前首个账户的授权、CLI和基本模型连接已经确认；空的 account-01 位置继续保留，不冒充已授权。
五个 Agent、领域资料、A2A与桌面运行的正式切换继续待办，Scholar仍暂停，阶段门未批准。
