# 固定终稿与出版归档

Paper 保持六阶段。`PUBLICATION` 是接收后的工作阶段；`ARCHIVED` 是作者核对校样并完成归档的内部投稿事件，不是第七阶段。

新投稿事件通过 Studio 的同一服务处理。界面始终提交实际正在显示的 `generated_version_id`；投稿、发表和归档必须使用当前成功生成的版本，作者输入和科学绑定不能过期。仅有上传成功、生成成功或 PUBLICATION 阶段不能证明归档完成。

每个新事件在同一事务内追加原 submission_events 行及 studio_submission_bindings 快照。快照固定事件原字段、生成版本和作者 revision、content/inputs 摘要、生成 job、原作者结构和模板来源；不能用后来 active 版本回填历史。旧事件保持原字节/字段，缺快照显示 UNBOUND，不构成进入出版的接收依据。旧稿的其他编辑部事实可以继续登记为未绑定元数据；没有正式成文的稿件不能通过新 SUBMITTED 事件提交。

Stage 4 或 Revision 的稿件进入 PUBLICATION 前，必须有当前生成版本的明确 ACCEPTED 事件。PUBLISHED 和 ARCHIVED 还必须匹配相同 venue、round 和固定版本；同一轮后来的撤回、拒绝或返修请求会使原接收不再授权新的发表/归档。编辑部后到的历史事件可以明确绑定旧版，但不能把旧版当当前终稿提交。

ARCHIVED 要求当前版本已有有效接收及发表事件，终稿和校样均为本稿 READY DOCUMENT，实际文件位于受管目录且大小/SHA256与登记一致，并有作者明确确认。快照固定两份文件及其角色、原接收事件、前一个同轮事件。原稿件阶段、阶段历史、投稿事件、绑定快照在同一写事务提交，任何一步失败全部回滚。

工作面返回 publication.completion。当前版本、作者 revision、科学状态、接收及文件都有效才为 CURRENT；后来内容/科学依据/接收变化为 STALE；原文件缺失或内容变动为 UNAVAILABLE。历史事件、原摘要与文件名均保留，读取不重写历史。文件真实性与校样科学内容仍由作者核对，软件不推断外部期刊接收或代替科学批准。

`operation_id` 固定一次记录意图。同一 manuscript、同一 operation_id 和完整相同请求返回原事件；改请求或换稿件使用同一键返回冲突，不能重复落库。POST 已确认而工作面刷新失败时，界面只重新读取；网络结果不明时保留输入并用同一键核对原请求。

Schema 14 只新增 studio_submission_bindings 和索引，原109表结构/行保持，除了 catalog schema_version 明确从13变14及 applied_at。没有迁移旧事件、伪造接收/终稿版本或重跑生成模型。初始化仍须验证旧资料保持与重复初始化幂等。
