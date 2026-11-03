# Forge Notion 中继迁到服务器

2026-10-23 已完成用户要求的迁移。当前运行位置以本页、
`deploy/forge-notion-relay.json` 和实际服务配置为准。

## 当前所有者

| 内容 | 位置 |
| --- | --- |
| Notion 中继 | alandelone-server-001，uuma-forge-notion-relay.service |
| 监听 | 127.0.0.1:8776，仅服务器 loopback |
| Forge 日志消费者 | uuma-forge-journal.service，同机访问中继 |
| Notion 凭证 | ~/.config/uuma/forge-notion-relay/connection.json，0600 |
| Forge 身份注册表 | 同目录 tokens.json，仅含 forge-lab-bot，0600 |
| 中继回执 | ~/.local/share/uuma/production/forge-lab-bot/notion/relay-receipts.db |
| Lab 领域数据 | 原服务器 production/forge-lab-bot/lab.db，未迁库或改 schema |

工作站关机不会中断这条 Notion 同步链。浏览器、硬件、桌面和 ChatGPT bridge
仍按各自运行位置工作，本次没有迁移它们。原工作站 Hermes 配置同时供其他
Notion 工具使用，未删除其共享授权；Forge 的服务器服务独立读取上述服务器配置。

## 权限和来源

只通过既有、校验主机密钥的 SSH 搬移所需 Notion 请求头，没有复制整份
Hermes 配置、浏览器登录态或其他 API 凭证。中继继续限制 Forge 身份、两类日志
数据源、候选知识状态和命名操作；没有开放任意 URL、请求头或原始数据库接口。

复用已部署的固定运行快照，未覆盖或全量发布开发工作区：

- Source：`~/.local/share/uuma/wisdom-forge-cutover-20261022/8d751df2ca0f2dfee43853ba5bc279009b6760343c0d251f4dd4f9a3a33cd9d0/source`。
- Relay module SHA256：`fe064cae608423f8016d11d5659529f23fb9469e3d167655a8895578d366fc4e`。
- Python：原 staging/b34a766098ef3e11277e7c858e5aedef5f9fa7c0ddeda2f4af3d19c1c99e2338/venv/bin/python。
- Forge journal endpoint 从服务器上的反向转发8775改为同机8776；实际进程环境已读回。
- Journal 增加对中继服务的 systemd 启动依赖，两项服务均 enabled。

## 切换与检查

1. 明确预览；暂停 Forge 接单，确认无活动日志写入。
2. 停靠原 Journal，使用 SQLite 一致性备份保留 Lab 数据。
3. 等原中继请求结束，再停止工作站中继；一致性备份全部回执。
4. 在服务器核对177笔原始回执的全部字段与摘要，再启动服务器中继。
5. 校验原回执可鉴权读取、匿名访问被拒绝、Notion 用户和两个真实数据源元数据可读。
6. 仅更改 Journal 的中继地址，恢复服务及接单；观察到正常 POST /call 200。

原177笔回执全部为 COMPLETE，逐行迁移保持原样。原 Lab 的12笔 SYNCED、
1笔 CANCELLED 和1笔 SENT 通知保持；没有恢复或重试旧任务。
没有发起示例 Notion 写入、模型调用或消息发送，没有新增或运行自动化测试。
原服务继续其已授权的正常同步；不把只读检查当作新的业务写入验收。
共享 Hermes gateway 没有重启，五个 Telegram 接收方保持连接。

## 工作站退役配置

已停止原中继及其启动进程，8775不再有工作站监听；当前
`.uuma-local/workstation-node-production-20261022/startup.json`
移除了 forge_notion，并从未来的共享反向隧道参数移除了8775。
当前共享隧道仍为 ChatGPT bridge 提供8787，它携带的旧8775通道暂时空置，
下次正常重连时消失。Forge 的生产消费者不再访问该通道。
原回执保留为退役备份，不能用它启动第二个生产中继。

## 回执与回退

本机私有记录：`.uuma-local/forge-notion-server-20261023/`。
服务器记录：`~/.local/share/uuma/forge-notion-server-20261023/`，含 prepared、
maintenance、applied、runtime-verification 和一致性 Lab 备份。
连接文件和注册表不纳入 Git 或公开回执。

迁移后的中继会继续追加回执。若需回退，先暂停 Forge、停靠 Journal，确认没有
在途请求，并备份服务器最新回执；核对全部新增状态后再转移消费者。
不得直接恢复旧工作站回执库或旧 Lab 数据覆盖新记录，也不得同时运行两个写入中继。
正常更新优先保留服务器所有权，只切换固定代码或配置引用。
