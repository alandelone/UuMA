# Flash3.8：原文到 PaperSkeleton 续作核验

**当前状态：三篇端到端通过；十篇整体尚未通过。指定 Flash3.8 上游两次返回503，剩余提取被阻塞。**

完整范围保持十篇、126个窗口、1286个原文区块。沿用原冻结DSPy四层提示与严格来源检查。原批次31个窗口通过，95个窗口服务失败；31个成功窗口的模型请求没有重跑。
三篇共279个区块已通过原生保存、四层完整检查点、HTTP读回、重复保存不产生新版本、实际页面逐单元原文/保存结构比对与重新开页检查；三篇原生Skeleton任务现为SUCCEEDED。另一个成功窗口属于policy论文，因整篇尚缺12个窗口而未发布局部Skeleton。

| 论文 | 原区块 | 通过窗口／总窗口 | 失败窗口 | 完整Skeleton保存及页面 |
|---|---:|---:|---:|---|
| PTHP | 162 | 18／18 | 0 | [已验证](http://127.0.0.1:8893/?view=all&paper=paper_6ab2ae52d0536c8addc36a3ee01494ae) |
| URB | 60 | 5／5 | 0 | [已验证](http://127.0.0.1:8893/?view=all&paper=paper_3a5ca5e9c786512b865dc66b59cc8597) |
| fridge | 57 | 7／7 | 0 | [已验证](http://127.0.0.1:8893/?view=all&paper=paper_c27dce12d5511dec4130e1ffe7f66f7a) |
| PHS | 164 | 0／16 | 16 | 待完整提取 |
| carport | 184 | 0／17 | 17 | 待完整提取 |
| policy | 143 | 1／13 | 12 | 待完整提取 |
| stochastic | 111 | 0／10 | 10 | 待完整提取 |
| Ghana | 109 | 0／10 | 10 | 待完整提取 |
| Ethiopia | 151 | 0／17 | 17 | 待完整提取 |
| retractedGA | 145 | 0／13 | 13 | 待完整提取 |

## 阻塞与已修正问题

原95个失败：54个HTTP530；15个含429配额错误；26个仅报告路由冷却。2026-10-19保留原失败后进行了两次间隔超过五分钟的单窗口恢复试探，均收到Google模型上游503高需求；每次在第一个失败请求立即停止。模型服务目录可访问不代表该模型可完成提取。
保存核验的摘要格式错误已修正：原生内容摘要使用原生摘要函数，实验血缘摘要保持实验函数。162个首篇原文/三层结构/第四层角色/原生摘要全部精确复核；没有修改已保存提取内容或放宽断言。
测试采集原24小时活动时限因两天等待已耗尽。原暂停和完整数据库快照保留，正常预算历史追加“当前已用时间加一小时”，仅完成三篇已验证缓存的任务登记，随后恢复PAUSED。没有启动通用采集或新的模型工作进程。
四层展示接口与页面的12个原生回归检查，以及转义、版本归属、旧返回隔离和读取重试检查已通过；本轮确认源码摘要与通过时一致。实际Browser核验三篇279个单元全部匹配，并保存页面证据。

## 完整清单与证据

- [本次95个失败窗口逐项清单](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/flash38-all95-failures.md>)
- [本次全部126个窗口、每篇状态、完整错误与恢复血缘](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/flash38-all126-window-status.json>)
- [先前40个来源未通过、7个提取缺失、2个科学未决窗口完整清单](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/old-40-7-2-full-list.md>)
- [旧49项完整原记录及全部8个原提取失败案例](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/old-40-7-2-full-list.json>)
- [实际浏览器核验](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/native-browser-checks-20261019-v2/record.json>)
- [原生保存及完整读回核验](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/native-publication-v2/status.json>)
- [三篇缓存采用的真实原生任务记录](<C:/Users/Alandelone/CodeSpace_Local/UuMA/.tmp/flash38-skeleton-stability-20261017-v1/ready-native-cache-job-completion-20261019-v3/record.json>)
- [完整机器可读续作结果](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/result.json>)

## 科学与上线边界

此处279个单元的精确保存与显示检验说明可用三篇的软件链路通过。原文覆盖检查和结构检查不等于每个科学命题经独立专家判定正确。Flash3.8目前没有完整十篇结果、独立语义复核或同模型基线比较，因此不能证明科学准确率或DSPy提升。
结果位于单独的真实原生验收Catalog（8893）；主Catalog本轮没有写入。主库原四个NEEDS_REVIEW来源状态及全部十篇PDF摘要已只读确认保持原记录。默认深读引擎没有切换；FieldKG的原区块意图消费还未适配本次原子意图数组。第四层完整角色/置信度/理由保存在核验过的检查点，现有单元页面显示角色。
旧3.7科学报告及40／7／2边界全部保留；没有新评分、缺失分数填补、科学批准或mission阶段/门禁推进。

## 续跑条件

同一冻结失败窗口必须先能取得所指定gemini/gemini-3.8-flash的有效返回。其后采用独立恢复记录继续95个失败窗口，复用原31个成功窗口与所有已成功层的响应；整篇完整后再保存、读回及核验页面。两个已失败恢复请求均为终态，原错误和ID须保留。当前没有后台模型批次继续发送，也没有自动轮询任务。

三篇完整四层提取导出，包含279个原文单元及第四层完整字段：[ready-three-paper-skeletons.json](<C:/Users/Alandelone/CodeSpace_Local/UuMA/docs/reviews/scholar-rstv4-2026-09-30/flash38-text-to-skeleton-2026-10-19/ready-three-paper-skeletons.json>)。
