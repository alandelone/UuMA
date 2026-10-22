# 本批次 API 已切换至8080的Antigravity选项

**新配置已实际使用，并通过一个原失败窗口的完整四层提取及原始回应重播核验。**

| 项目 | 原批次 | 本次续跑 |
|---|---|---|
| base_url | `https://api.95963210.xyz/v1` | `http://192.168.55.2:8080/v1` |
| 请求中的model选项 | `standard` | `antigravity` |
| 实际provider | `gemini` | `antigravity-oauth` |
| 实际回应模型名称 | `gemini-3.8-flash` | `gemini-3.8-flash-medium` |
| 推理档位 | 原API配置 | 明确指定`medium` |

原来确实调用standard，但额外排除了非指定Flash3.8的路由。本次调用现有服务器8080上的专用antigravity选项，未修改其他API配置或默认深读引擎。
Antigravity插件把Flash3.8加medium解析为CLI实际名称gemini-3.8-flash-medium。完整原始回应保持该名称。曾因核验期待无后缀名称而停下，已保留失败上下文，并复用那次成功返回的第一层，没有重新发出该成功请求。
CLI不支持temperature/max_tokens/n，因此这些参数明确不发送；不能宣称旧temperature0/max_tokens24000仍适用。请求消息、原文、四层提示和全部严格来源/输出检查保持原冻结版本。旧31个成功窗口及已有成功层按原始来源复用，原模型/provider血缘照实保留。

## 实测与续跑

原失败窗口PHS/window_index0已经完成11个区块的四层提取，最终通过的四层均绑定真实antigravity-oauth/gemini-3.8-flash-medium回应；原缓存中一个未通过格式检查的Gemini尝试也完整保留并按原程序重播拒绝，不将该尝试算作最终层输出；独立保存回应重播零模型调用，并与提取结果完全相等。
本报告读取时：34／126窗口通过，剩余92；原31个成功窗口保留。实时进度以[当前status.json](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/antigravity-continuation-20261020-v2/status.json>)为准。
原批次95个失败窗口清单仍作历史输入与错误证据，续跑会跳过新目录内已完成窗口。单个提取进程继续剩余窗口；另一个零模型调用的保存观察进程只处理整篇齐全且再次通过全部来源/四层重播核验的论文，核对原生保存、完整检查点、HTTP读回和重复保存不新增版本，再登记真实缓存采用任务。
新七篇的实际浏览器复核仍待完整论文产生后进行；十篇整体稳定性与完整科学评测尚未完成。旧3.7报告、40／7／2边界与所有原始失败均保留，未新增科学评分或声称优化提升。

## 已核实的诊断路径

- [当前已使用的API续跑配置](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/antigravity-continuation-20261020-v2/client-config.json>)
- [新通道续跑事件](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/antigravity-continuation-20261020-v2/events.jsonl>)
- [新通道提取日志](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/antigravity-continuation-20261020-v2/continue.stdout.log>)
- [新通道错误日志](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/antigravity-continuation-20261020-v2/continue.stderr.log>)
- [整篇原生保存核验状态](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/antigravity-native-persistence-20261020-v2/status.json>)
- [原126窗口清单、状态和完整错误](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/flash38-all126-window-status.json>)
- [原126窗口输入计划](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/full10-extraction/plan.json>)
- [原126窗口全部最终结果](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/full10-extraction/record.json>)
- [原窗口开始／结束及逻辑调用时间日志](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/full10-extraction/execution-events.jsonl>)
- [原worker-stdout.log](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/full10-extraction/worker-stdout.log>)
- [54个HTTP530窗口的UTC时间关联索引](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/diagnosis-log-index-20261019-v1/http530-window-correlation-index.json>)
- [原95个失败窗口续跑输入清单](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/diagnosis-log-index-20261019-v1/remaining95-resume-manifest.json>)
- [原95个失败窗口逐项错误](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/flash38-all95-failures.md>)
- [旧通道第一次503补跑记录](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/full10-recovery-20261019-v1/halted.json>)
- [旧通道第二次503补跑记录](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/full10-recovery-20261019-v2/halted.json>)

原始逐窗口记录位置：

```text
C:\Users\Alandelone\CodeSpace_Local\UuMA\.tmp\flash38-skeleton-stability-20261017-v1\full10-extraction\cases\<paper_id>\<window_index:03d>\record.json
```

原base_url已用175个保存请求的规范摘要核对。原批次主要访问GET /v1/router/status、POST /v1/runs、GET /v1/runs/{run_id}。
**54是以HTTP530结束的窗口数；底层HTTP请求总次数及精确HTTP发送时间，需要对齐Router服务端日志确认。索引保存UTC窗口开始/结束和逻辑调用事件时间，不冒充HTTP抓包时间。**
本报告与索引没有API key。完整绝对路径也保存在[result.json](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-antigravity-api-switch-2026-10-20-v2/result.json>)的diagnostic_paths中。
