# 服务器模型账户池

## 边界与实际状态

这是 `alandelone-server-001` 上的 Antigravity 模型账户池，供五个服务器 Agent 使用。
不是 UuMA 用户、Telegram Bot 或工作站浏览器账户。
旧插件依赖 Windows Anti-Tools 的切换脚本，不能直接在 Linux 上复用。
服务器不导入工作站模型凭证；用户在工作站完成 Google 授权，服务器保存本次新授权，
并由固定版本的官方 CLI 检查是否可用。

账户池、操作页面和五份 profile 接线候选已准备；正式 Agent 接收方尚未启动。
账户只有在官方 `agy models` 检查成功后才标为可用；存在凭证文件本身不代表授权成功。
模型实际可用性仍须另行验证。此前单次 OK 登录尝试在认证阶段超时，没有完成模型验证。

## 从工作站加入账户

使用本机保存的完整管理入口链接（含临时管理口令），进入账户池页面：

1. 在已有账户位置按“登入”，或填写名称后按“新增并登入”。
2. 打开该次 Google 授权链接，选择要给服务器使用的账户并同意授权。
3. Google 自动回到工作站的 loopback 回呼地址，经 SSH 隧道送到服务器；不用贴授权码。
4. 返回原管理页，等待“交换 Google 授权”及“检查 CLI 连接”完成。
   页面显示“可用”后才能供 Agent 选用。重复以上操作加入其他账户。

新版回呼等待上限五分钟；可以取消等待，逾时后重新按“登入”，不要复用旧链接。
管理页面不发送模型提示。每次登录有独立 state 和 PKCE verifier；回呼只消费一次。
Google token endpoint 交换成功后查询 userinfo，确认已验证邮箱并拒绝重复 Google 身份，
随后保存 consumer OAuth 的 CLI 相容格式，最后检查官方 `agy models`。
已存在的授权文件不被覆盖；若已保存授权但 CLI 检查失败，可单独按“检查授权”。
需要重新授权时，先新增独立账户位置，再停用旧位置。

“设为首选”调整后续选择顺序；“停用”阻止后续选择，不撤销已执行的外部动作。
名称是操作者设置的标签；成功回呼的 Google 身分另行核对并保存在服务器私有元数据。

## 执行规则

- 每个账户有独立 HOME、配置及 OAuth 文件；池元数据不保存 OAuth 值。
- 显式关闭共享 D-Bus keyring 路径，防止 CLI 读取其他账户的系统 keyring，使用该账户的独立文件。
- 目录权限为 0700，授权文件为 0600。官方 CLI 及启动入口固定版本并检查摘要。
- 通过 Linux 文件锁租用账户；同一账户同一时间仅供一个 CLI 请求使用。
- 优先选启用、已授权、未冷却且空闲的账户；同优先级按最近使用时间轮换。
- 子进程继承租约描述符；即使外层进程终止，仍运行的 CLI 不会被误判为空闲。
- 所有账户占用或不可用时返回明确错误，不自动打开 Google 登录，不偷偷采用其他身份。
- 原生 CLI 的明确 quota 错误使该账户冷却 30 分钟，下一请求可选备用账户。
  这不是实时剩余额度查询；当前实现不承诺识别所有供应商错误格式。
- 当前请求不会因为 quota、网络错误或响应丢失而在账户池中自动重放。
  已有外部业务动作的核对与重试由 UuMA 的执行回执承担。
- 使用原插件的一次性请求路径，传递完整 Hermes 消息；闲置的持久 worker 不占用账户。
  SOUL、MCP 名称、工具过滤器和审批规则保持原配置。

## 操作入口与发布

服务器操作页面仅监听 `127.0.0.1:8771`，工作站 SSH 转发为 `127.0.0.1:18771`。
这两个端口是新增的操作者入口，不占用原计划的 8765–8770。
API 使用独立操作者 Bearer 口令，修改请求检查 Origin 与 JSON 类型；不接受 Agent 身份。
回呼以 state 和 PKCE 校验，不依赖 Google 无法携带的管理 Bearer；其余 API 仍要求管理授权。
页面不写入浏览器永久存储，授权码不进入 HTTP 日志。浏览器刷新后应重新使用完整入口链接。
服务尚未设为开机自动启用；关闭 SSH 转发后，工作站页面不可访问。

入口与候选位置以本机忽略目录 `.uuma-local/latest-provider-pool.json` 为准。
管理链接存于 `.uuma-local/provider-pool-operator-url.json`，不得提交 Git 或共享。
SSH 转发进程回执为 `.uuma-local/provider-pool-tunnel.json`，只处理回执对应的进程。

手动发布组件 `server-provider-pool` 是 `server-gateway` 的依赖。
变更池适配器需在预览中列出共享 gateway 影响的五个 Agent；不触发自动更新。
账户及授权目录位于版本目录外，发布新代码不会重建账户池。

## 2026-10-21 OAuth 连结修正

首次真实交互暴露了终端 OSC 8 超链接问题：BEL 分隔符未截断，把隐藏网址与可见网址
拼接在一起，造成 Google 报 `client_id` 重复。原失败候选和检查证据保留。
现改为读取以控制字符结束的完整网址，拒绝重复参数、缺少 PKCE、非预期回调或未读完的链接；
不猜测、删除或重写 OAuth state/参数。22 项 Linux 隔离检查通过，未使用真实模型。

## 对照 Anti-Tools 的回呼改造

检查本机已安装 `felix2cn.anti-tools-1.17.1-universal/out/extension.js`：
`startOAuthLogin` 使用本机 callback，token endpoint 交换后以 userinfo 确认身份；
`addAccountViaOAuth` 登记账户；`CliIntegrationService.syncKeyringIfInstalled` 定义 consumer token
封装。只参考公开应用设置和相容格式，没有读取或搬移 Anti-Tools 的已存账户凭证。

旧网页通过 PTY 代贴码，真实使用中一直等待，日志没有保存授权或完成交换。
因此生产管理入口改为直接浏览器回呼；原 PTY 代码只保留诊断兼容，手动 Enter 也改为 CR。
新版不依赖终端绘制、快捷键或复制授权码，失败时显示具体阶段和安全错误。

应用设置单独保存在服务器私有 `oauth-client.json`，不写进 Git；来源版本和摘要有独立回执。
授权及 token endpoint 分别固定为 Google 官方地址，PKCE/state 逐次生成；没有复用旧失败流程。
参考 [Google 桌面 OAuth 文档](https://developers.google.com/identity/protocols/oauth2/native-app)。

新版 32 项 Linux 隔离检查通过，包括真实本地 HTTP 回呼、重复/错误 state、PKCE 配对、
取消、超时、身份去重、私有文件权限和保存成功但 CLI 未确认的状态。使用假的供应商响应，
不代表真实 Google 帐户或模型已验收；只有真实 CLI 检查成功才标记“可用”。

## 首个真实账户的 CLI 与模型验收

首次 Google callback 已成功保存授权，但 CLI 报未登录。原生文件访问追踪证明固定的
`agy1.4.4` 实际打开 `antigravity-oauth-token`，此前按插件旧注释保存的
`jetski-standalone-oauth-token` 没有被读取。已保留原授权副本及摘要，在同一服务器账户
目录建立正确入口；没有要求用户重新授权，也没有改动其他账户。

现以原生 CLI 实际读取的名称为优先，另一名称仅用于发现和保留旧资料；新 OAuth 直接写入
正确文件。补充了拒绝错误文件名的 CLI 夹具及优先顺序检查，34 项 Linux 检查通过，Ruff 通过。
“检查授权”会返回明确结果并清除旧失败提示，按钮显示处理中。

首个真实账户已通过 `agy models`，网页 API 回报 authorized=true；按用户此前明确同意，
使用原 profile 的模型解析结果 `gemini-3.8-flash-medium` / medium，仅执行一次
“Reply with exactly: OK”，退出码0、输出为 OK。防重复回执在服务器私有
`approved-model-verification.json`；不得重新执行该次验证或重置回执。
旧认证超时的 verification 记录仍保留，不用新成功记录覆盖历史。

这确认首个账户的授权和基本模型调用可用；五个 Agent 的正式切换和完整业务验收仍未完成。
