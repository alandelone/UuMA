# Brainstormer 导航服务迁移

工作站默认保持 `127.0.0.1:8772`。服务器 Hermes API 使用该端口时，导航服务使用
另一个已检查为空闲的 loopback 端口，例如 `8773`。

服务器导航进程必须同时设置：

```text
UUMA_DATA_DIR=/absolute/owner/data
UUMA_NAVIGATION_DATABASE_PATH=/absolute/owner/navigation/brainstormer-navigation.db
UUMA_REQUIRE_SEPARATE_NAVIGATION_DB=1
UUMA_NAVIGATION_TOKEN_REGISTRY=/absolute/control/data/tokens.json
UUMA_NAVIGATION_COMMAND_SECRET_FILE=/absolute/private/navigation-command.secret
UUMA_NAVIGATION_COMMAND_USERS=123456789
```

`UUMA_DATA_DIR/brainstormer` 是正式领域文件目录。独立导航库保存用户议题绑定、讨论记录和
提交回执，不使用控制库 `uuma.db`、Wisdom 知识库或 Hermes `state.db`。

在该 profile 的 `uuma_brainstormer_commands` 插件配置中设置：

```yaml
navigation_url: http://127.0.0.1:8773/api/v1/navigation
navigation_identity: brainstormer
navigation_token_file: /absolute/private/brainstormer.token
navigation_command_secret_file: /absolute/private/navigation-command.secret
```

## 复制旧导航表

先停靠原导航写入者，制作一致的 SQLite 快照，再使用固定版本环境运行：

```text
python -m uuma.state_daemon --migrate-navigation SOURCE_SNAPSHOT NEW_NAVIGATION_DB
```

此命令在启动任何导航 daemon 之前退出。它仅复制 `user_bindings`、`discussion_turns`、
`commit_receipts` 和对应索引；不修改源文件，不覆盖已有目标，不复制控制表。
源快照缺表时停止，不自动制造空的替代历史。核对三个表的内容摘要和行数后，才启动配置好
独立路径的导航进程并验证议题切换与保存。启动端口通过 `--port 8773` 指定。

启用 `UUMA_NAVIGATION_TOKEN_REGISTRY` 时，所有 HTTP 入口需要 Orchestrator 或 Brainstormer
的独立 Bearer 身份；审批只允许 Orchestrator。缺失 registry 会停止启动，不能自动创建身份。

`/topics new` 保留为人类明确命令：受控插件签名完整请求、Telegram 用户、时间戳和 nonce。
服务器只接受配置用户在五分钟内的有效签名；普通 Brainstormer token 不能自行创建结构或审批。
独立导航库的 `navigation_commands` 表在执行前保留意图，成功后保存回执；重复请求返回原回执，
未确定结果的意图需要核对，换 nonce 也不会重新执行。既有回执可在签名过期后读取。

命令 secret 由服务器独立生成，至少 32 字节，存放在受控文件中。该能力属于可信插件进程，
不构成同一系统用户下任意代码之间的安全边界。服务保持 loopback，经受控工作站入口访问。
未配置认证的既有工作站保持兼容。
