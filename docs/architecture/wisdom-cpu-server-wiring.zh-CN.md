# Wisdom 服务器 CPU 接线检查

状态：候选环境接线契约；不表示 Wisdom 已完成生产切换。

## 独立运行边界

- KAG 固定为 0.8.0，保留其 `mcp==1.6.0`，不安装整套 Hermes/UuMA 依赖。
- UuMA Knowledge MCP 在自身环境中运行，通过 loopback 语义 HTTP Bridge 使用 KAG。
- Bridge 使用候选 KAG Python，加上固定版本 UuMA `src` 路径。
- Bridge 还需要独立安装 FastAPI、uvicorn；仅成功导入 `kag` 不足以证明 Bridge 可启动。
- 实测 Linux Python 3.12 环境的 165 个依赖版本固定在
  `deploy/wisdom/requirements-cpu.lock`；KAG 源码仍由发布清单单独固定，不从该锁文件推断源码。
- 已有 OpenSPG 项目 1、服务、容器和数据保持原有所有者；服务器 Bridge 不管理其生命周期。
- 生产 `wisdom.db`、源文件和 projection outbox 仍须分别停靠写入者、备份和核对后切换。

## Bridge 环境

生成配置时必须将下列占位项解析成已核对的服务器绝对路径，不直接执行示例：

```text
PYTHONPATH=<固定 UuMA 源码目录>/src
UUMA_KAG_CONFIG=<服务器候选 kag_config.yaml>
UUMA_KAG_BRIDGE_PORT=8891
UUMA_KAG_IDLE_SECONDS=0
UUMA_BGE_BACKEND=onnx
UUMA_BGE_M3_PATH=<已核对摘要的 BGE-M3 目录>
UUMA_BGE_ONNX_THREADS=2
UUMA_BGE_BATCH_SIZE=1
UUMA_BGE_MAX_LENGTH=2048
CUDA_VISIBLE_DEVICES=
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
USE_TORCH=0
USE_TF=0
KAG_PROJECT_HOST_ADDR=http://127.0.0.1:8887
KAG_PROJECT_ID=1
UUMA_KAG_LLM_MAX_RETRIES=0
UUMA_KAG_LLM_TIMEOUT_SECONDS=60
```

不得设置工作站的 `UUMA_KAG_COMPOSE_FILE`。已有 idle monitor 会执行 compose stop，
不适用于服务器上共享的 OpenSPG 项目。独立 user service 只监管 Bridge，端口占用即停止。

Knowledge MCP 初次接线使用 `UUMA_KAG_BRIDGE_URL=http://127.0.0.1:8891` 和
`UUMA_KAG_AUTO_RECOVER=false`，避免 systemd 与按需启动器竞争同一监听地址。
将来启用按需启动前，必须先统一进程生命周期的所有者。

## KAG 配置

- 显式提供本地候选配置，防止误用工作目录里的旧配置或自动拉取另一份项目配置。
- 只读实测项目 ID 为 1，namespace 为 `Uuma`；不得覆盖其已有值。
  schema、embedding dimensions 必须与服务器项目实测一致。
- 服务器同机访问 OpenSPG 使用其实际 loopback 地址，不照抄 Windows 路径。
- 本地候选的 `vectorize_model.type` 拟使用 BGE-M3，路径指向服务器模型目录，维度为 1024；
  这不表示共享项目当前已使用 BGE，也不构成更新共享项目的授权。
- `kag_bridge._configure_local_bge_runtime` 在初始化 KAG 前替换上游 BGE-M3 loader，
  保留 registry 和调用契约。必须显式选择 ONNX；缺失模型时失败，不能回落到 Torch。
- checkpoint、日志等运行目录独立于固定版本源码目录。
- 不上传 schema、不恢复项目、不排空 outbox 来完成健康检查。

### 项目 1 的只读实测

按服务器已安装 SDK 的实际 API 前缀，读取
`GET http://127.0.0.1:8887/public/v1/project?projectId=1`，得到：

- namespace 为 `Uuma`。
- 项目配置的 `vectorize_model` 为 `type: mock`、`vector_dimensions: 1024`。
  这只是已保存的配置，不能证明现有向量由 mock 生成，也不能当作实际 embedding 验收。
- `openie_llm` 配置键出现乱码；本地候选修复键名不等于修改共享项目配置。

私有实测回执保存在服务器
`runtime-envs/kag-cpu-0.8.0/project-1-readonly-inventory.json`；配置摘要为
`abee35fc4f0b7ca76f6ac80f1322cac1e02bc28c6086906442d3ff7675792779`。
回执不导出账户凭证或完整项目配置。

启用 BGE 前，必须核对已有向量的实际来源、模型版本、归一化方式、维度和索引兼容性。
同为 1024 维不代表来自相同向量空间。不得自动重建索引、重投影、覆盖或恢复项目 1；
需要改变已有向量或索引时，应另行准备可审查的备份、变更与回退方案。

## 模型账号仍是独立接线条件

KAG 的 `openie_llm`、`chat_llm` 需要 OpenAI 风格 HTTP 客户端契约。
服务器三个 Antigravity 原生账号就绪，不代表它们已接入这一接口。
需要新配置服务器凭证或实现明确的账号池适配；不搬移工作站 API key，
也不以 mock 模型冒充实际可用。缺失时保留明确的降级/等待状态。

可验证的候选接法是服务器 Hermes root profile 的
`http://127.0.0.1:8772/v1/chat/completions`，复用 Antigravity 模型账号池。
该 root profile 应仅提供模型计算：工具集为空、memory 关闭、无 MCP；
使用其独立服务令牌，不能误用 Agent profile 令牌或 UuMA 控制身份。
该接口已通过一次实际同步请求格式验证；完整 KAG 同步/异步客户端、失败语义与生产接线
仍需分别验证。生产 Agent 配置未修改。
验收须覆盖 KAG 消息格式、模型名称解析、非流式 JSON/文本返回、错误/超时语义、
上下文隔离和账号池并发限制。LLM 输出仍进入候选知识和既有审批流程。

KAG `OpenAIClient` 的 `base_url` 应为 `http://127.0.0.1:8772/v1`，客户端追加
`/chat/completions`。当前上游默认携带 `chat_template_kwargs.enable_thinking=false`，
同步和异步调用均需兼容。显式设置 `enable_check:false`、`stream:false` 和有限 timeout；
上游构造器在项目启用 `llm_config_check` 时可能发出额外的模型验证提示。
实际响应需包含 `choices[0].message.content`，并正确处理可选的 tool_calls/usage。

上游构造 OpenAI SDK 客户端时没有传递配置里的 `max_retries`，JSON 解析方法还带有
Tenacity 重试。因此服务器需要显式启用 Bridge 的重试与超时限制；只填写 YAML 中的
`max_retries:0` 不足以证明单次执行。该限制默认关闭，工作站未设置时保留原行为。
启用后，SDK 和 KAG 构造器均受超时上限约束；只移除该 KAG OpenAI 客户端的 Tenacity
重试层，不修改供应商源码、注册表身份、其他 LLM 类或其他装饰器。

## 分阶段证据

1. 环境：wheelhouse 摘要、实际依赖版本、`pip check`、CPU provider 和实际 KAG 类导入；
   禁止 Torch、CUDA、GPU runtime。
2. 不推理接线：导入实际 UuMA Bridge；核对本地配置、模型文件摘要，检查 `/health`。
   现有 `/health` 只初始化配置并探测 OpenSPG TCP 地址，不会构建 encoder 或写知识。
3. 模型验收：在另行安排的有界验证中构建 CPU encoder，核对实际 provider/维度，
   验证 KAG 的 LLM 调用和检索。不能将第二步健康状态当成这一步的成功。
4. 正式切换：冻结单一写入者，核对最新领域数据库与文件，再开放受控投影和业务调用。
   新端产生业务写入后，回退必须先核对新增记录。

### 已完成的隔离实证

- KAG 0.8.0、ONNX Runtime 1.23.2、MCP 1.6.0、FastAPI 0.141.1、uvicorn 0.52.4
  安装完成，依赖完整性与实际 KAG 类导入通过，无 Torch/CUDA 包。
- 首次类导入因上游要求项目元数据而失败，原日志保留；检查使用不可访问的 loopback
  地址补齐导入条件后通过，没有连接项目或模型来完成导入检查。
- 实际 HTTP 健康检查通过，项目配置摘要前后相同。健康检查本身没有 embedding 推理。
- 单独一次 CPU encoder 验证生成两组不同的有限值向量，形状为 `2 × 1024`，实际 provider
  仅 `CPUExecutionProvider`，耗时约 3.7 秒；不代表共享项目的向量或检索已通过验收。
- 单独一次 KAG 格式同步 HTTP 请求经服务器账号池返回预期 JSON，耗时约 12.5 秒，
  无工具调用。服务器内部模型令牌只保存在私有候选配置，不复制工作站模型凭证。
- 服务器实际 KAG 同步/异步客户端通过成功与失败四种 HTTP 模拟检查，每种只发送一次。
  检查复用已保存的真实响应，没有额外模型调用；它证明客户端协议和重试策略，不冒充
  四次真实供应商验收。隔离 Bridge 的健康状态显示零自动重试与 60 秒超时。

这些验证没有启动 projection worker 或写入知识。生产切换、向量兼容性和完整检索仍待验收。
