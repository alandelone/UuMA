# Agent 开发、Git 与手动上线操作手册

更新日期：2026-10-23。供后续开发及发布 Agent 执行。
本页记录已迁移的位置和发布约束，不代表整套发布工具或架构验收已完成。
上线时以实时服务配置、来源摘要和回执为准；迁移时的快照不是当前版本证明。

## 1. 源码在哪里，实际在哪里运行

UuMA 主开发仓库：`C:/Users/Alandelone/CodeSpace_Local/UuMA`。
以下目录均相对该仓库；五个 Agent 定义共用一个 Git 仓库，无需每个拆库。

| Agent | 工作站开发入口 | 生产节点 | 服务器领域数据根目录 |
| --- | --- | --- | --- |
| Brainstormer | profiles/brainstormer | alandelone-server-001 | ~/.local/share/uuma/production/brainstormer |
| Yonc | profiles/yonc | alandelone-server-001 | ~/.local/share/uuma/production/yonc |
| Honc | profiles/honc | alandelone-server-001 | ~/.local/share/uuma/production/honc |
| Wisdom | profiles/wisdom-oldman | alandelone-server-001 | ~/.local/share/uuma/production/wisdom-oldman |
| Forge | profiles/forge-lab-bot | alandelone-server-001 | ~/.local/share/uuma/production/forge-lab-bot |

- 部署后的 profile：`~/.local/share/uuma/pilot/home/profiles/<profile-name>`。
- 共享运行 home：`~/.local/share/uuma/pilot/home`；定义副本不等于开发仓库。
- 控制库唯一生产所有者：服务器 `~/.local/share/uuma/data/uuma.db`。
- Wisdom：wisdom.db、wisdom-content；Forge：lab.db、eschematic、commerce；
  Honc：honc.db。Brainstormer 状态和 Yonc Graph 的具体文件路径从正在使用的
  unit/env/迁移清单读取，不凭目录名称猜测或初始化新库。
- Orchestrator、Scholar 的 Agent 运行位置保留工作站。Scholar 的领域后端可能
  独立演进，必须读取当前配置，不把早期 FieldKG 位置或队列暂停状态当作现状。
- 浏览器、交互登录、硬件及桌面连接器保留工作站。Forge 的 Notion 中继、
  所需凭证和请求回执已迁到服务器；它不再依赖工作站的 Notion 中继或 SSH 反向转发。
- 源码运行快照在服务器的版本目录中；不是一个可随意 git pull 的生产 checkout。
  查明 unit 的 ExecStart、WorkingDirectory、EnvironmentFile 和真实 Python 导入路径。

### Forge 工作区及独立引擎

`Z:/Hardware-Lab-Workspace` 与服务器 `/mnt/nas/Hardware-Lab-Workspace`
是同一个 NAS 目录，包含同一个 `.git`，不是两个可相互同步的 clone。
先协调停止会修改同一文件的 Forge 工作，再由单一主机写文件、commit 或切分支。
缺少 Z 映射时先恢复 NAS 访问，不自动创建 C 盘替代目录。
旧 `C:/Users/Alandelone/CodeSpace_Local/Hardware-Lab-Workspace` 已删除。

Yonc Graph 开发仓库为 `C:/Users/Alandelone/CodeSpace_Local/yonc-graph`。
RSTV4、Yonc Graph、eSchematic 保持各自仓库；从当前组件配置核实实际引擎位置，
分别记录 commit 和内容摘要，不把它们整个复制进 UuMA Git。

## 2. 接手时先做什么

1. 读 AGENTS.md、mission_status.json、当前 gate、最新 HANDOFF.md，按 session
   lifecycle start/resume、包装命令并在结束前 handoff/check/close。
2. 读本页、production-topology.json、forge-workspace.json 和相关组件运维记录。
3. 查看 Git branch、status、diff、已有暂存内容、远端配置及近期提交。
   工作区有大量并行开发内容，保留无关文件，不 reset、clean、全量 stage 或自动 stash。
4. 确定本次改的是 Agent 定义、共享运行代码、领域引擎还是 NAS 项目文件；列出依赖。
5. 发布前经 SSH 读取实际 unit/env 的非敏感字段、来源摘要、运行版本、活动任务及入口。
   不输出 token、账户池凭证、私钥或整个可能包含凭证的环境文件。

### 已知 Git 基线问题（2026-10-22）

迁移评审分支 `codex/five-agent-migration-20261021T095318Z` 的迁移/清理记录
截至 `5235b013fa45fd94805d8ee0d68578b3a0a0c61a`；没有在本手册任务中合并或推送。
本次读取主工作区为 `master`，HEAD 为
`67516d29e8a94ab002a9e00fa6a4737ee45d0ccd`，与早期迁移时的 HEAD 不同。
另有 provider-pool 修复评审分支和其他正在开发的修改，必须重新核对 ancestry/diff。
这些只是观测值，禁止硬编码成下次发布目标。

日常开发前整理需要纳入的迁移提交与后续修复，审查差异和依赖，再选择性整合。
不要直接切整个脏工作区、盲目 merge/cherry-pick 全分支，或让旧迁移快照覆盖后续修复。
生产曾包含未提交但已有摘要的保留改动；commit 相同也不能证明部署内容相同。

## 3. 日常开发与 Git

默认在工作站改源码，SSH 用于读取服务器和手动部署。需要远程编辑时使用开发副本，
完成后把明确差异纳入版本控制，不把生产版本目录当作开发目录。
NAS 项目属于共享活跃工作区例外，编辑会立即改变文件，不具有发布隔离。

示例（在目标仓库运行）：

```powershell
git status --short
git diff -- <本次相关文件>
git add -- <本次相关文件>
git diff --cached
git commit -m "feat(wisdom): describe the change"
```

`<...>` 是占位符，先换成实际路径。只提交自己本次的改动；同一文件混有他人修改时
用选择性暂存或隔离索引，且保留原暂存区。新分支默认使用 `codex/` 前缀。
提交和 push 都不代表上线；核实远端与用户范围后才推送。
凭证、生产数据库、会话、模型缓存及发布私有回执不能作为源码提交。
Agent 可独立改进，各组件不用拥有相同 commit；记录实际内容与兼容接口版本。

## 4. SSH 与服务边界

已验证 SSH 别名：`ssh ubuntu-server`，用户 alandelone，服务器 alandelone-server-001。
已验证地址为 192.168.55.2；连接细节见 repomemory/server-ssh-access.md。
使用既有 known_hosts 校验；认证失败先修复访问，不关闭主机密钥验证。

| 服务器服务 | loopback 端口 |
| --- | --- |
| UuMA control | 8765 |
| Yonc Graph | 8766 |
| Wisdom view | 8767 |
| A2A | 8768 |
| semantic MCP | 8769 |
| Hermes native API | 8772 |
| Brainstormer navigation | 8773 |
| Forge Notion relay | 8776 |
| Wisdom CPU KAG | 8891 |
| OpenSPG shared graph service | 8887 |
| Scholar FieldKG bridge | 8892 |

这些是既定服务器端口，工作站转发端口可能不同，以当前隧道配置为准。
Scholar 当前的完整图谱检查需要工作站 loopback8887 和8892 均转发至服务器同号端口；
只验证8892健康会遗漏 project/schema/底层只读检查。见 scholar-fieldkg-server-20261022.md。
工作站桌面入口 8770，ChatGPT bridge 8787。语音转写直接调用服务器 UnlimitedLLM API：
服务器 Agent 使用 `http://127.0.0.1:8080/v1/audio/transcriptions`，工作站客户端使用
`http://192.168.55.2:8080/v1/audio/transcriptions`。原工作站 STT 8774 中继及其反向转发
已退役，不为语音重新创建该依赖。详见 [语音直连运维记录](speech-server-direct-20261104.md)。
Forge 原工作站 Notion relay 8775 已停止，并从当前启动清单移除。
服务器使用 loopback8776；现存共享8787隧道中的旧8775转发通道在下次重连时退役，
当前 Forge 不使用该通道。不要为此中断仍在运行的 ChatGPT bridge 工作。
隧道叠加逐身份认证，服务不因部署而绑定公网；不用另一 Agent token 冒充身份。
服务器持有自己的模型账户池，不复制工作站浏览器或全部账户凭证。

## 5. 手动上线流程（Agent 应执行的步骤）

### A. 生成具体预览

记录目标节点、组件、准确 commit、未提交差异摘要（若存在须明确纳入审查）、
文件/依赖/profile/技能内容摘要、接口兼容版本、当前版本、数据库变更、备份位置、
受影响任务、服务重启范围与回退步骤。目标内容变化必须重新生成预览。
没有变化的组件标为已符合目标，不重启。

修改 Wisdom 定义通常只涉及其 profile；若定义使用新增工具，还要发布该工具服务。
修改 Brainstormer Telegram 插件时核对 navigation/state-daemon 是否需要同步升级。
共享 ControlClient、权限、MCP 或 gateway 变更可能扩大范围，不能仅看文件夹名称。
每节点一个共享 Hermes gateway；重启 `uuma-hermes-pilot.service` 会影响服务器五个
Agent，必须在预览中列出全部五个，即使只修改一个 profile。
保留 gateway 已固定的 Hermes、UuMA 和 provider-pool 导入路径，不能遗漏账户池修复。

### B. 应用指定预览

用户要求开发不自动等于要求上线；用户已明确授权本次上线时按其范围执行。
不要重复索取已给出的同一项授权。遇到超出范围的破坏性操作再明确说明。

1. 校验预览内容仍然一致，端口、依赖、NAS 挂载、凭证可用且没有并行发布。
2. 暂停受影响接单，等待活动任务结束。共享 gateway 重启必须覆盖其全部影响。
   长任务未结束则延后；保持原暂停任务、恢复标识和执行版本，不擅自取消或重放。
3. 对要变更的数据使用 SQLite 一致性备份并保留文件摘要、表/关键记录与回执。
   无 schema 变更也记录当前数据所有者和回退限制；不直接复制活动 WAL 数据库。
4. 准备固定版本目录和独立依赖，staging 使用独立数据、端口、身份及测试入口。
   运行数据放在版本目录外；不要覆写已发布快照或用 git pull 替代发布。
5. 切换相关配置引用，只重启必要服务。逐项记录旧/新值和实际执行结果。
6. 做本次范围内已授权的健康/权限/版本核对；真实模型调用、消息发送、外部写入
   按用户授权范围执行，不重复历史授权验证或科研队列。
7. 确认唯一机器人接收方、数据库所有者和实际导入版本后恢复接单。

### C. 查看并保存回执

回执包括预览标识、时间、操作者、节点、旧/新摘要、来源 commit、实际 Python/引擎版本、
重启服务、任务停靠结果、备份、验证证据、未完成项及回退入口。凭证值不写回执。
健康进程、Telegram 连接、真实模型回复是不同证据，分别记录，不把其中一项当作全部通过。

**当前限制：**完整的组件级发布 OS hooks 尚未全部接通。已有泛用预览可能缺少实际
revision 并错误扩大到两台机器，不能直接 apply。先补齐本次范围的具体发布步骤和
固定内容预览，再手动执行并保存回执；不得宣称自动化发布已完成。

## 6. 回退、数据与离线约束

- 代码回退可恢复旧引用；一旦新端产生业务写入，先核对新增数据再规划数据回退。
  禁止直接恢复旧库覆盖新写入。不要让两台机器同时打开同一生产 SQLite 文件。
- 旧 C 盘已核验迁移副本及部分本地 final snapshot 已删除，不再作为回退来源。
  原始服务器备份/NAS 仍保留，精确位置查 cleanup 记录及对应迁移回执。
- 不创建第二套本地 uuma.db、wisdom.db、lab.db 或 Graph 生产库；保留 remote-owner guards。
- 工作站离线时服务器继续已授权且不依赖桌面的工作；桌面/登录步骤明确等待，
  重连先核对审批、有效期和回执，不盲目重放。
- Wisdom 知识 apply/reject/reverse 保持 Orchestrator/用户审查；Orbit 正常空闲退出不算故障。
- 不因开发/上线自动恢复 Scholar、重试历史任务或重建 FieldKG。
- mission gate 仍为 verification/pending_review，普通开发/发布 Agent 不自行批准。

## 7. 相关记录

- [迁移检查点](distributed-cutover-20261022.md)
- [NAS 工作区](forge-nas-workspace.md)
- [Forge Notion 中继迁移](forge-notion-server-20261023.md)
- [旧副本清理及保留备份](migrated-source-cleanup-20261022.md)
- 配置：deploy/production-topology.json、deploy/forge-workspace.json。
- 私有回执：.uuma-local/ 下各组件 cutover、provider-runtime-repair 和 cleanup 目录。

历史运维记录保留当时状态；与本页冲突的旧 C 回退说明或“Forge 仍待迁移”字样已失效。
对正在并行改进的生产组件，始终用当前 SSH 只读观测和最新回执确认。


## Scholar Catalog fixed-release entry point (2026-10-26 candidate)

The workstation Scholar service has an opt-in fixed-release pointer at UuMA .uuma-local/scholar-catalog-runtime/active-release.json. scripts/resolve-scholar-catalog-runtime.ps1 verifies complete source/parser manifests, the unchanged data/resource owner, interpreter/configuration/base binary and effective dependency versions, then invokes the fixed Catalog's read-only owner admission. It never initializes a database or starts a service. The existing service launcher uses this resolution only when the pointer exists; the pointer has not been activated by the candidate tests. Preserve the Live Agent branch and shared Hermes/other specialist processes.

The native Windows release-admission suite is tests/windows/test-scholar-catalog-release.ps1; it writes only a newly supplied fixture root and starts no real service or task. Existing tests/windows/test-service-recovery.ps1 remains required for the shared launcher. Fixed-source admission, native fixture guards, actual upgraded-owner checks, full isolated-runtime regression, canonical migration and observed supervised operation are distinct evidence. A prepared environment or a passing fixture is not a deployment receipt.

Keep parser-only artifact reuse separate from private manual requests. Per-paper PARSE/INITIAL/FULL evidence scopes do not require every paper to be deep-read. The original explicitly requested deep acceptance sample still requires its complete native/content/purpose chain before this release. Retain original artifact paths and all raw model provenance; do not restart the successful extraction or transplant an entire staged database.


## Scholar Catalog worker-only runtime override (2026-10-30)

The workstation currently has two fixed-release manifests under
`.uuma-local/scholar-catalog-runtime/` in the UuMA project:

- `active-release.json` supplies Catalog Web, the configured native Catalog MCP launcher,
  and the bounded content-index runner. It is not the Reading task's current manifest.
- `reading-release.json` supplies `UuMA Scholar Catalog Reading`; its scheduled action
  passes this path explicitly to `run-scholar-catalog-reading.ps1`.

The Reading-only performance release selects four texts per automatic embedding batch.
Its schema, task/prompt contracts, parser and other application sources remain compatible
with the shared release. This permits a worker-only restart without interrupting the Web
or an already-running compatible content-index batch. Inspect the actual task action,
both manifests, imported engine roots and current jobs rather than assuming one shared
pointer governs every component.

Future shared schema, parser-contract, task-registry or PaperSkeleton-profile releases
must coordinate both manifests and every affected consumer. A shared-pointer-only update
does not update this Reading task. Preserve its principal, triggers and settings when
changing only its action; wait for a real worker checkpoint and retain durable requests.
Rollback changes only the relevant action/manifest at an appropriate checkpoint, never
by restoring an old database over newer writes. Runtime manifests, private receipts,
databases and credentials remain local operational artifacts, not source-control content.
