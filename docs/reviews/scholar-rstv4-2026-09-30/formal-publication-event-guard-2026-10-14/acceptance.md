# 发表事件入口守卫与原子提交

真实复现并修复 PUBLISHED 事件绕过阶段校验的问题：之前会先提交事件，再直接写PUBLICATION，既没有正式版本/科学复核检查，也不写阶段历史。现在它与正常阶段切换共用同一个守卫，在同一个BEGIN IMMEDIATE事务内检查、写阶段/历史并追加事件。任一步失败全部回滚。已在PUBLICATION时另记一次事件也先完整验证；合法重复登记不重复增加阶段revision/history。

**验证结果**：修复前新用例8失败、2通过，完整日志保留；修复后41相关检查通过，Ruff通过。当前完整回归1088通过、20条既有警告，307个src/tests/scripts文件在执行前后冻结一致；耗时483.45秒。未弱化原断言或删除失败记录。测试内模型/编译替身和legacy-stage/scientific-review SQL是明确的软件夹具，不是科学批准、原生操作或真实外部发表。

**真实HTTP实跑**：独立精确109表副本，模型/worker/作业恢复禁用。现有零版本DRAFTING稿的PUBLISHED请求422，现有Stage3稿直接PUBLISHED也422；每次拒绝后全部109表/schema精确保持。原r62/v5稿合法进入FINALIZATION_SUBMISSION后，PUBLISHED登记201，独立GET工作面200并读回事件与阶段历史。共5次真实HTTP：422×2、200×2、201×1。事件明确标记软件验收，不代表外部期刊提交、接收、发表或科学认可。

**数据审计**：109表/schema保持，106表完整精确；manuscripts仅该稿stage/writing_status/revision/updated_at变化（revision+2）；manuscript_status_history只追加该稿两条，submission_events只追加该稿一条。全部旧行、原210意见/3审稿轮/5版本、非空回复、核对、修改链接、作者r62/v5、模型/作业/科学记录保持。源目录及全部原文件精确保持，副本旧数据文件精确保持。HTTP服务已正常退出。

**源码约束**：唯一产品修改studio.py：73e31e84d3fadb51a46ec9c50e44e0763cccde98be6cac519a2db480923e6797 → 04d222b466d774fb1d82f681fc9b87e2711947c60e2a9a7f90c824102678f0da。仅set_stage区域及record_submission_event两块变化，按字节反向替换完整重建旧封存源码。新增10个回归案例。runtime v11保留全部v9检查，只接受这两个精确块及最终307文件向量。schema、API请求格式、前端、原生产数据库均未修改。

**独立复核**：只读审查确认同阶段早退在所有检查之后；同连接事务及异常rollback覆盖事件、阶段和历史。结果只覆盖本次修复。

**临时服务收尾**：RE10本轮新建的49414/49415/52898共6个自有应用进程已按PID、创建时间、精确命令及工作目录验证后关闭，端口空闲，数据库保持。第一次收尾因Windows conhost工作目录与应用目录不同而在任何terminate前停止；只读诊断后v2明确不结束Windows console host，保留所有应用归属校验。原Writing Studio、GPU已完成任务、用户要求保留的采集页未动，未清空临时文件或批量结束node。

**封存执行记录**：v1封存器在创建报告目录之前停止：新digest封装把旧v9的PriorPopoverBytes当作Path构造。v11只对真实Path执行studio精确反向校验，旧v9代理原样交还原digest，保留全部旧HTML/Bib/模型桥检查。没有改产品或数据，没有重跑HTTP/模型/完整回归。失败的v10/v1文件保留。

**完成边界**：本批完成发表入口的现有版本/科学/阶段守卫与事务修复；不表示WF09/WF10全通过。ACCEPTED先决条件、固定投稿/终稿版本与校样/归档完成权威链、原生事件交互、RE10/RE11尚缺的原生分支、最终同源码11组贯通及原118整体验收仍未完成。mission维持verification/pending_review，没有批准gate或科学结论。

另已封存的A206接口归档/恢复报告见 ../formal-reply-archive-http-2026-10-14/acceptance.md；它明确是接口证据，原生页面未完成，不能计作通过。
