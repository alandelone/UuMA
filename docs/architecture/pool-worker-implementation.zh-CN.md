# 有界 worker 与服务器账号池实施记录

本记录对应五个 Agent 迁移的试点进展。五个生产机器人尚未切换；工作站上的
Orchestrator、Scholar 和浏览器继续留在原处。

## 已实现

- `gemini-worker` 保留原 MCP 名称、任务输入、调用身份、工作目录限制和结果回执。
  默认仍用原 Gemini CLI；服务器试点显式选择 `account_pool`，通过已授权的三个
  Antigravity 账号执行，无需再登录一套 Gemini 账号。
- 服务器入口校验固定 wrapper 的 SHA-256，使用 plan 模式和原生 sandbox，提示词从
  stdin 传入。超时结束本次调用的进程组；没有可用账号、入口摘要不符或供应商失败时
  返回阻塞/失败，不自动切换到其他后端，也不重放模型请求。
- 工作目录白名单限制任务入口，不等同操作系统文件隔离。worker 不声称已独立审计
  模型的文件访问；需要审计的业务仍须由所属服务核对结果与写入回执。
- 回执区分请求的模型与供应商实际报告的模型。实际模型未提供时保留未知。
- `configure-pool-worker.py` 只在显式执行时修改选定 profile 的 worker 配置，保留
  调用身份及 SOUL；修改前按摘要备份，生成绑定回执，不启动机器人或登录账户。

## 实际验证

服务器试点已接入 Brainstormer 的 worker MCP，真实 stdio 初始化与工具列举成功。
独立测试文件包含未出现在提示词中的随机标记及比较数据；一次实际调用返回正确标记和
比较结果，调用前后文件清单与内容保持一致。该结果仅证明这次测试，不代表任意任务都
不会产生文件变化。成功测试不重复执行。

A2A 查询已独立核对 Hermes 原执行：原试点结果仍在 UuMA `REVIEW`，未获验收；
原 Hermes 执行因轮数耗尽而失败。A2A 现在如实返回失败及 `accepted=false`，保留原
执行标识，不为消除失败记录而重跑任务。结果验收与运行状态是独立信息。

## 手动更新范围

- worker 源码归 `bounded-worker`，使用者为 Brainstormer、Wisdom、Forge、
  Orchestrator、Scholar；Yonc、Honc 没有因此获得调用权限。
- CPU 准备工具归 `knowledge`，影响 Wisdom；不会让 Scholar 重建本地 FieldKG。
- profile 绑定工具归 `server-gateway`；需要共享 gateway 重启时，预览列出服务器五个
  Agent 的影响范围。组件依赖计算不能代替实际服务的重启影响核对。
- 现阶段仍有工作区候选部署，不能将其冒充固定 Git 提交的正式发布。正式更新须重新
  生成固定提交预览，应用指定预览，再查看回执。

## 正式切换的剩余条件

Wisdom CPU 依赖与 FastAPI/uvicorn 已在隔离环境安装，实际 CPU encoder 和 HTTP 健康检查
通过；之前下载超时与导入失败记录保留。项目 1 命名空间实测为 `Uuma`，配置仍为 mock
向量模型。同步模型请求格式已验证，完整 KAG 客户端限制、向量兼容性与检索仍须核对。
详见 [Wisdom CPU 接线检查](wisdom-cpu-server-wiring.zh-CN.md)。

Hermes 的现有 profile 热扫描不会因 `telegram.enabled=false` 自动断开已存在的
接收器。正式切换必须确认旧接收器真正停止，再启动服务器接收器；不能只改配置便
宣称单入口成立。共享 gateway 排空会影响该节点全部 profile，须按真实影响范围安排，
保持 Scholar 已暂停任务及其恢复环境。

领域数据最终停写同步、Hermes 会话与记忆、桌面连接器、离线等待、其他四个 Agent
运行验收及完整手动发布仍未完成。阶段门保持 `pending_review`。
