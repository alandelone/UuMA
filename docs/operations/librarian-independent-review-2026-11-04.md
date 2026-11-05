# Librarian independent Git and acceptance review — 2026-11-04

结论：有真实部署和备份进展，但不认可执行报告的“18 项 PASS”作为完整验收结果。下面是独立复核，不改写原执行报告，也未修改线上服务或执行生产恢复。

## Git 与验证范围

- 本地 HEAD、远端 origin HEAD 和 master 均为 `bfad28af15a583ff9ff8730d58ae247f70eea772`（2026-11-03，`feat: extend specialist research and orchestration`）。通过 `git ls-remote` 直接核对远端，没有 fetch/merge/push。
- 今天的验收报告、交接规格及部分 profile 文件仍未跟踪；guard、worker、测试与若干运维文档仍是未提交修改。最新线上部署与最新 Git 提交不是同一个状态。
- 复查现有 Worker 类型化输入和 guard 变更；本次未改产品源码。
- 当前本地相关测试：**205 passed / 23 skipped / 1 warning**。跳过项主要为 POSIX/Linux/Windows 符号链接权限要求；不能宣称这些平台分支本次都通过。受影响 worker/guard/profile 测试的 Ruff 通过。
- 额外只读读取服务器 intake/publication 账本、当前语义目录和定时器；对 NAS 清单重新计算摘要，未对全部密文对象再次重哈希。
- 审查本地私有验收脚本，并以全合成数据对恢复验收器做失败注入。未使用真实恢复密钥、调用网络或恢复生产数据来复现该缺陷。

## 审查发现（按重要性排列）

### R1 — P1：恢复验收脚本吞掉数据库完整性失败，可能误报 PASS

位置：`.uuma-local/librarian-implementation-20261029/verify_isolated_restore.py:93`。

脚本把 SQLite 打开、`PRAGMA integrity_check` 和完整性断言放在同一个 `try` 内，随后 `except Exception: pass`，并在第 97 行返回 `True, "PASS"`。因此真正的数据库损坏与完整性断言失败都会被当作“普通非 SQLite 文件”吞掉。

独立全合成失败注入让 `integrity_check` 返回非 ok，实际仍得到 `(True, "PASS")`，已复现。最初使用真实损坏夹具还暴露了异常路径连接未关闭导致 Windows 临时目录清理失败；该首次失败保留，随后用不持有文件句柄的模拟完整性结果单独验证吞错问题。

建议：依据清单的捕获方法/已识别格式区分 SQLite 与普通文件；SQLite 打开及完整性失败必须返回失败，连接始终关闭。先增加损坏库/非 ok/异常的负向验收，再重新执行相关恢复。当前发现不表示已证明真实备份损坏，而是验收器不能可靠拒绝损坏。

### R2 — P1：六个数据库样本不满足“全范围恢复”标准

位置：`docs/operations/librarian-acceptance-report-2026-11-04.md:57`；私有脚本 `verify_isolated_restore.py:53`。

脚本固定选择六个来源、每个最多前三个 CAPTURED 条目，只读取各批次最新修订。未全量恢复所有声明来源，未展示逐来源旧恢复点和删除前内容恢复，也没有验证全部关联文件和应用层关系。项目全树仍未捕获，却将第 16 项写为 PASS，与交接标准不符。

建议：第 16 项先标 PARTIAL，明确六个样本的真实证据；补齐覆盖矩阵、全量对象恢复、历史恢复点和关联检查之后再申请完整验收。

### R3 — P1：临时 PEM 导出测试不能证明独立密钥保管完成

位置：执行报告第 18 项（第 59 行）、第 145 行；私有脚本 `verify_offline_recovery_key.py:18`、`:20`。

脚本使用代码中的测试口令，在 `TemporaryDirectory` 内调用 `export_offline`，再加载临时 PEM 解密本地 Phoenix 样本；临时目录退出即删除。它证明导出/加载/解密功能可行，但未展示用户长期持有的独立介质副本、用户掌握口令或脱离原工作站环境的恢复。报告称“user passphrase”和“Air-Gapped”超出了该脚本证据。

建议：保留“导出功能及口令解密测试通过”，独立密钥保管标为未完成/待用户操作。提供用户本地交互导出、独立介质与独立恢复环境的回执；不在报告、代码或聊天中保存真实口令。

### R4 — P1：读取工具上线不等于新增备份来源可检索

位置：执行报告第 15 项（第 56 行），并影响第 10 项（第 51 行）。

实际读取当前生产 `semantic-archive/catalog.json`：仍只有 `brainstormer-index` 和 `yonc-graph` 两个来源，均标 PARTIAL，总共 59 条记录。Phoenix/ChatGPT bridge 进入恢复 intake 是真实进展，但没有进入当前语义目录。备份 Yonc 数据分片本身也不证明当前工作站对话/文件与服务器项目能够联合查询。

建议：保留已通过的 MCP 基础设施与既有 A2A 证据，来源读取覆盖及完整跨端项目查询标 PARTIAL，并按来源补真实搜索、读取、版本和关联的结果。

### R5 — P1：仍有无法采集条目，不能以事件数量证明“全部记录”通过

位置：执行报告第 4 项（第 45 行）、第 6 项（第 47 行）。

本次直接读取当日 intake 最新清单：

- `antigravity-core`：41,420 个条目，PARTIAL，1 个 UNAVAILABLE。
- `codex-app-roaming`：25,027 个条目，PARTIAL，77 个 UNAVAILABLE。

Phoenix 的 trace/span 数量、Observatory 事件数以及 source 注册数，不证明原始对话、全部工具输入输出、附件及所有 agent 关联文件已齐全。内容采集还可能未启用或被截断。

建议：保留这些部分备份，明确剩余条目与无法取得内容；以来源/记录族对账决定状态，而不是将整项直接计 PASS。

### R6 — P2：性能保护配置不等于“几乎不影响工作”已实测

位置：执行报告第 9 项（第 50 行）。

源码确有 4 MiB/s NAS 发布限速和可选 I/O pressure 检查；这是保护机制。报告未提供代表性任务基线、备份期间的耗时/CPU/内存/磁盘数据，也不能仅凭源码推定运行时阈值开关已配置。交接稿要求的实际工作影响仍未证明。

建议：状态改为“机制已有、负载验证待完成”；性能阈值按交接稿注明是建议值，实测后再定 PASS。

### R7 — P3：NAS 数量应区分修订与批次

位置：执行报告第 18、58 行。

账本实测为 **153 个修订，对应 152 个不同批次**，不是 153 个不同批次。匹配的未发布修订数为 0。历史修订保留是正常行为，不应把它重复计为新批次。

建议：更正报告计量单位；“100%”限定为当前 intake 已接收修订的发布完成率，不能解释为用户所有资料 100% 完成。

## 已独立确认的进展

| 项目 | 本轮核对结果 | 证据边界 |
| --- | --- | --- |
| NAS 已恢复发布 | 发布 timer enabled/active；intake 和 publication 各 153 修订，未匹配修订为 0 | 已接收修订发布闭合，不是所有目标资料已采集 |
| NAS 清单可回读 | 重新读取 153 份清单并计算摘要，0 缺失、0 摘要不匹配 | 本次未重新读取全部密文对象，因此不声明本轮全对象重哈希 |
| Phoenix 当日清单 | COMPLETE，1 条捕获记录，0 UNAVAILABLE | 数据库对象已接收，不代表已完成全应用级恢复与可读索引 |
| ChatGPT bridge 当日清单 | COMPLETE，1 条捕获记录，0 UNAVAILABLE | 本地 bridge 状态不等同云端全部对话 |
| 服务器 daily capture 与 semantic 服务 | timer/service enabled/active | 服务健康与来源完整性分开判断 |
| 本地相关软件回归 | 205 passed，23 skipped；受影响文件 Ruff 通过 | 不代替线上全范围验收 |

## 建议交回执行 agent 的修正清单

1. 先修恢复验收器吞错与连接清理，保留损坏输入的负向证据，再重跑真实恢复。
2. 重写验收矩阵：把基础设施、样本恢复、全来源恢复、可读覆盖和独立密钥保管分别计量；不要继续用“18 PASS”表示全部已验收。
3. 补全部来源/文件/附件及历史恢复对账；保留当前 PARTIAL 与源缺失清单。
4. 完成新增来源的可读目录与项目联合检索，再做实际负载验证。
5. 更正 153 修订/152 批次；审查并选择性提交新增报告、profile 与修复，避免线上版本无法从 Git 重现。不自动 stage 整个并行工作区。

本轮没有批准 mission gate、修改验收器或原报告、恢复生产数据、重启服务、commit 或 push。相关私有只读回执位于 `.uuma-local/librarian-implementation-20261029/audit-live-metadata-20261104.log`；失败注入复现脚本为同目录 `probe-restore-false-pass-20261104.py`。
