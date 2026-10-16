# Agent CodeBook


# Harnesss Engineering  in Agent 开发

- how good harness look like ? Claude Code planning, filesystems , sub -agent, hooks, permissions

- open harness  : 基于 Vercel AI SDK, 目标是轻最、 model-agnostic 的 Cla ude COde 替代品。核心 agent loops, tools 、 sub-agents 、 MCP, permissions 已全部可用

- 🛠️ Harness 比模型更关键：验收基线、执行边界、反馈信号、回退手段

### 4.1 持久状态：让 Agent 不再失忆

- Feature List （ JSON 格式）。每个功能描述用户可见的行为和验证步骤，附带、 passes: true/false 、字段。这是项目的 ground truth 。 Agent 启动时读它就能知道还剩什么要做，不需要从代码推断。标记为完成必须经过端到端验证，不能凭感觉。

- Progress FiIe: 每个 session 结束时 Agent 更新，记录做了什么、完成了什么、留下了什么状态、下一步建议做什么。这保证了下一个 Agent 实例能在 30 秒内定位上下文，而不是花半个上下文窗口做考古。

- init.sh 标准化的环境启动脚本一怎么启动 dev server 、怎么跑数据库、怎么让应用进入可测试状态。每个 session 开头跑一次就行，省掉 Agent 每次从头搞清楚"怎么把这个项目跑起来"的 token 开肖。

- Git 作为认知脚手架。每个 session 结束必须 gitcommit （带描述性 message ）并更新 ProgressFileo 如果当前改动破坏了什么，回退到上次已知良好状态再试。这不只是源码管理一它是 Agent的"后悔药"和新 Agent 的"快速定位工具"。

- mission status ：管理任务状态； trace log ：记录任务过程一解决"它是不是又全忘了"的不安。通过结构化文档锁定项目进度与判断证据。

<details><summary>mission_status JSON:</summary>

  

</details>

### 4.2 agent legibility 执行环境：给 Agent 手和脚

- Bash + Code Executiono 与其为每个可能的操作预设工具，不如给 Agent 一个通用执行能力。SWE-agent 团队发现：把复杂命令简化为 Agent友好的版本（、 find + cat 、分、 open 、，sed 、分、 edit 、），同一个模型的成功率大幅提升。工具设计的目标不是功能齐全，而是让 Agent 容易用对。

- 沙箱。 Agent 生成的代码不在你的本地环境执行，而是在受控沙箱中运行。可以设置命令白名单、网络隔离。

- Git Worktree 隔离。每个 Agentworktree ，有自己的工作目录、分支和环境。改动在隔离中完成、在隔离中测试、通过验证后才合并。并行 Agent 共享工作区会互相踩踏一这和多线程共享内存的问题一模一样，解决方案也一样：隔离。

- 浏览器自动化。给 Agent 接上 Puppeteer ，让它能像用户一样导航、点击、填表、验证。 Anthropic加上这个工具后， Agent 的 bug 发现率产生了质的飞跃一因为它终于能看到用户会看到的东西》而不只是代码本身。OpenAl 做得更彻底：搭建了完整的本地可观测性栈LogQL 查日志、 PromQL 查指标、 TraceQL查链路一一一 Ag e n t 用和人类工程师一样的调试工具。而不是从代码猜测运行时行为。

- 一个能看代码+跑应用+查日志+看页面的Agent ，和一个只能读代码的 Agent ，是两种完全不同的物种。

- Tool Wrapper：把工具的正确用法打包进去 

### 4.3 Context Engineering 上下文工程：对抗注意力污染

- 渐进式披露（ Progressive Disclosure ）。

- 分层加载策略：始终常驻分 CLAUDE.md /AGENTS.md: 项目契约、构建命令、绝对禁止事项, 

- Entropy management 

- OpenViking is an open-source Context Database designed specifically for AI Agents.

- get-shit-done , 上下文工程  https://github.com/gsd-build/get-shit-done

### 4.4 反馈与验证：闭合回路

test-driven-development requesting-code-review verification-before-completion

- Level 0 ：退出码、 lint 、 typecheck次编辑后即时跑，最便宜

- Leve | 1 ：单元测试、集成测试正确性

- LeveI 2 ：浏览器自动化、截图对比到端用户视角一行为

- LeveI 3 ：日志、 m etri cs 、 tra ce s （可观氵则丷性）一运行时行为

- Level 4 ：人工审查产品决策、品味一架构方向、

关建原则：反馈越紧密越好，错误越早捕获越便宜。用 Hook 在每次编辑后自动跑编译检查，比在session 结束前跑一次高效得多。注意截断输出Hook 输出本身也会占上下文空生成与验证的不对称性。 P vs NP 的核心直觉在Agent 领域的体现：验证一个答案通常比生成一个正确答案容易得多。你不需要比 Agent 写得更快，你需要比它更会判断一定义什么是"完成"，识别偏差在哪里，判断方向对不对。

- 自我迭代

"如果一个任务你都说不清楚什么叫做完了，那它大概率也不适合直接丢给 Agent 自主完成。

- 在 SDD（Software Development Design）在线模式下构建 TDD 闭环自验证 Agent，本质上是将“红-绿-重构”循环（Red-Green-Refactor）固化为一个自动化状态机。这种模式的核心在于：测试代码即规格，不通过即故障。Agent 在这种模式下不再仅仅是代码生成器，而是一个具备“自我纠偏”能力的执行单元。

- 引入 Reviewer（审查者）角色 并实施 对抗评估与自主修复（Adversarial Evaluation & Self-Correction） 是一种极高效率的闭环进化机制。

- 验证：证据链搜寻自主取证Agent 自主搜集日志、截图等真实证据。拒绝囗头结论，只相信可追溯的系统反馈。

- 交付：系统复盘自主进化任务结束后， Agent 总结“为什么之前卡住并将优化策沉淀到 project-context.

- 纠偏： Course-Correction自我修复当运行轨迹偏离目标时，流水线自动挂起主任务，启动修订逻辑，实现自我纠偏。

- 调试：根因诊断精准治遇 Bug 启动系统化诊断。 Agent 必须先定位根因文档化，严禁盲目修改代码尝试。

- 它把一次完整的 AI 协作任务分成三层角色：三层之间形成一个闭环： Planner 提需求Generator 生成实现 Evalu ator 收评判不通过劐打回 Planner 做。Harness Design 还特别葜约先行：在Generator 廾始写代码之前， Planner 必须先给出一份足够详红的测试契约。明确瞄述[什么样的交付物算涕过]。这个细节很关，因为它把验收标准从事后评判变成了事前约定， Evaluator 拿首契约去就有据可依

- Evaluator （评估者）：独立检验产出，绝不能是写代码的那个。发现问题就截图打回给PIanner, 由 PIanner 重新发号施令。

### 4.5 Architectural Constraints架构约束的机械化执行：防止漂移

- 机械化强制执 

- 自定义 Linter 〔由 Codex 自己写）。裣 0 依赖方向、层级边界、模块化约束。关键设计： linter 报错时不只是说"违反了规则"，而是附带修复指弓刂，直接注入 Agent 上下文。约束被违反分规则是什么怎么修一，一一条消息闭合整个反馈回路。

- GoIden Principles： 编码进仓库的明确规则一，，一优先使用共享工具包而非手写 helper, 在边界处验证数据形状。后台定期运行的 Agent 扫 描偏 差、动开修正 PRO

- 核心原则：丨强制不变量（ invariants ），不管具体实现。你关心依赖方向、边界不被跨越、数据在接口处被验证。你不关心 Agent 用了哪个库或函数怎么拆分。守住边界，给 Agent 结构内的自主权。

- Martin FowIer 团队将 Harness 归纳为三个支柱：C0ntext EngineeringL （知识库的持续演化）ArchitecturaI Constraintsl （机械化约束执行）、Garbage ColIectionl （定期扫描不一致和违规的后台 Agent ）。三者缺一不可。

- 

### 4.6 Orchestrator-Workers编排：跨 Session 的协调 

- subagent-driven-development

- Anthropic 的双 Agent 架构。第一个 session 用lnitializer Agent— 不写功能，只搭环境：创建init.sh 、 Feature List 、 Progress File 、首次 gitcommit 。之后每个 session 都是 CodingAgent ，用标准化的启动序列快速定位：读Progress FiIe 读 Feature List 分选最高优先级的未完成功能分跑 init.sh 分跑基础氵则试确认应用正常。如果启动测试发现应用是坏的，先修冉做．．．．一防止在破碎的基础上叠加新功能。

- Subagent 的核心价值是隔离。不是并行（虽然也能并行），而是把大量输出留在子上下文里，主线程只拿摘要。扫代码库、跑测试、做审查这类产生海量输出的操作，塞进主线程会快速挤掉有效上下文。配置时要显式约束：限定工具集、限定模型（探索用Haiku 省成本，重要审查用 Opus ）、限定最大轮次、需要改文件时用 wo rktree 隔离文件系统。

- Ralph Loop （来自 LangChain ）。拦截 Agent的退出尝试，在干净的上下文窗口中重新注入原始prompt ，强制继续工作。文件系统使这成为可能一每次迭代从头开始（干净上下文），但从上次迭代的文件中读取状态。

- 元技能·自动路由skill-router 独立分析任务状态，确定当前最适合的Skill 组合，决定“下一步如何走“。

- stage-gate 是阶段转换的硬约束。它确保 Agent 在进入下一个自主环节前，已经完成了必要的收敛和质量达标。

- Planner （规划者）：读懂需求，制订测试契约，定义完成标准。它不写代码，只发指令。

- brainstorming

- writing-plans

- Generator （执行者）：照着契约写代码，不能自己加戏、不能过度设计，写完了就提测，仅此而已。Generator 层我拆成了两个，分别管好自己耶一亩三分地.把前后执行者分开的好处是：前端改动不会干扰后端逻辑，后端修复不会意外影响样式层，两个任务可以并行发布，互不干扰。

### 4.7  Reasoning Sandwich — 规划和验证用高推理，实现用低的 
4.8   Inversion：先问清楚，再开工 

# Loop Engineering

→ Automation：谁触发
→ Worktree：在哪里隔离执行
→ Skill：项目规则和检查怎么复用
→ Connector：能接哪些真实工具
→ Sub-agent：谁写，谁审
→ State：下次从哪里接着做

🚧 三条红线
→ 无证据不停止
→ 无隔离不并行
→ 无审批不发布

[page] Agent engineer 

[page] 多 Agent 协作一致性：并行执行、冲突控制与最终一致性的工程设计

- Agent 开发工程师的核心产物不是一个“聊天机器人”，而是一个受约束的决策执行系统。
一个典型系统至少包含模型、instructions/context、工具、运行循环、session/state、长期 memory（按需）、权限控制、评估与 tracing。Google ADK 明确区分当前 conversation 的 Session、临时 State 与跨 session 可检索的 Memory；OpenAI Agents SDK 则提供工具、handoff、guardrails、session、HITL 与 orchestration 等能力

- ：可运行服务、版本化 Eval 数据集、Tracing/性能报告、安全威胁模型与事故复盘。Agent Eval 尤其重要，因为自主、多轮系统的失败往往发生在轨迹中间