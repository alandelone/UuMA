# UuMA 项目全景指南与多 Agent 协同架构白皮书 (Project Map for Agents)

> **面向智能体 (AI Agent) 的项目全景图与角色指引**  
> **知识底座**: 由 CodeGraph (AST 符号拓扑网格) 深度解析构建  
> **更新时间**: 2026-10-09  
> **适用对象**: Antigravity, Claude Code, Hermes, Cursor, Codex 及接入本控制平面的各类自主 Agent

---

## 一、 系统定位与架构核心思想 (System Mental Model)

### 1.1 什么是 UuMA？
**UuMA** 是围绕 **Hermes** 智能体体系构建的**本地优先 (Local-First) 控制平面 (Control Plane)**。
它的核心使命是：**为多 Agent 协同、复杂项目编排、长期知识积累与真实世界物理/执行闭环提供严谨的状态机、不可变审计与权限护栏**。

在 UuMA 架构中：
- **Hermes 默认 Profile** 作为 **Orchestrator（总指挥官）**。
- 多个**领域专家 Profile**（如 Honc、Yonc、Wisdom-Oldman、Scholar、锻造Lab_Bot、Brainstormer）拥有隔离的运行上下文与专业能力。
- **不可变事件日志 (`uuma.db`)** 是系统的唯一真相源 (Single Source of Truth, SoT)。
- 工作任务、能力状态与执行状态均作为**投影 (Projections)** 派生，随时可安全重建。

### 1.2 核心架构原则与绝对禁区 (Absolute Invariants)
1. **控制与知识库物理隔离**：
   - 控制平面与调度状态在 `uuma.db`；
   - Wisdom-Oldman 领域知识在 `wisdom.db`；
   - Honc 每日执行流水在 `honc.db`；
   - 严禁挪用或混用 Hermes `state.db`，严禁跨数据库物理 JOIN。
2. **知识与项目事实的只增不减性 (Append-Only)**：
   - 纠正错误必须通过显式的 `CORRECT`、`SUPERSEDE`（取代）或 `REVERSE`（对冲撤销）事件，严禁静默覆盖历史。
3. **LLM 无权擅自突变核心结构**：
   - 智能体只能提出候选草稿或提议；
   - 任务结构拆解、知识合并、里程碑完成等敏感变更，必须经过**受信任的 UI 授权**或 **Orchestrator / 用户明确审查**。
4. **幂等执行与执行回执 (Execution Receipt)**：
   - 所有执行动作（尤其是 Honc 回写和状态变更）必须附带客户端生成的 `operation_id`，保证重试幂等，杜绝重复计时或重复状态推进。

---

## 二、 CodeGraph 视角下的工程目录与文件拓扑 (Project Layout)

通过 CodeGraph 索引体系（1,376 个文件、55,636 个符号节点、226,980 条依赖边），UuMA 的目录职责划分如下：

```text
UuMA/
├── .codegraph/               # CodeGraph 知识图谱数据库 (codegraph.db, WAL模式)
├── active-session/           # 当前会话运行态与交接日志 (HANDOFF.md, progress.md)
├── docs/                     # 系统架构图、ADR 决策、Agent 详细设计文档
│   ├── adr/                  # 架构决策记录
│   ├── agents/               # 每个人员/Agent的深度设计归档 (honc.md, yonc.md, etc.)
│   └── architecture/         # 系统架构白皮书
├── integrations/             # 外部集成插件与桥接
│   ├── chrome/               # Chrome 扩展 (ChatGPT Bridge 自动化等)
│   └── hermes/               # Hermes 原生插件 (control_guard, audit, observability)
├── profiles/                 # 各 Agent 的 Hermes Profile (SOUL.md, 技能库, 配置)
│   ├── brainstormer/         # 深度思考专家配置与技能
│   ├── forge-lab-bot/        # 硬件实验室专家配置与技能
│   ├── honc/                 # 日常执行与追踪管家配置与技能
│   ├── orchestrator/         # 总指挥官配置与护栏
│   ├── scholar/              # 科学研究专家配置与技能
│   ├── shared/               # 共享技能 (如 chatgpt-consultation)
│   ├── wisdom-oldman/        # 长期知识专家配置与技能
│   └── yonc/                 # 项目管理与拆解专家配置与技能
├── rules/                    # 严格的机械约束与自动化规范 (session-lifecycle, etc.)
├── scripts/                  # 运维、部署与启动脚本 (deploy-honc, start-uuma.ps1, etc.)
├── src/                      # Python 核心运行时源码
│   └── uuma/                 # uuma 核心包
├── stage-gates/              # 阶段门禁定义 (01-discovery -> 04-verification)
├── tests/                    # 自动化契约测试、幂等测试与状态机验证
├── AGENTS.md                 # 仓库总则与开发指南
├── mission_status.json       # 当前任务阶段与门禁状态权威文件
└── pyproject.toml            # 项目依赖与打包配置
```

### 2.1 核心运行时模块职责 (`src/uuma/`)

| 模块文件 | 核心职责与 CodeGraph 符号节点 |
|---|---|
| `service.py` | `ControlPlane` 核心控制引擎：处理任务创建、路由匹配、指派派发、状态扭转 |
| `models.py` | 核心领域 Pydantic 数据模型：`TaskContract`, `ResultContract`, `RunRecord`, `AgentProfile` |
| `event_store.py` | 不可变、带哈希链的 SQLite 事件持久化引擎 (`uuma.db`) |
| `colleague_directory.py` | **同事名录与能力字典**：维护 `ROLE_GUIDANCE`，提供 Agent 只读能力透视与负载探测 |
| `policy.py` | 策略与风险分级：`READ_ONLY`, `REVERSIBLE`, `COMMITTING`, `PROHIBITED` |
| `session.py` | 会话生命周期管理：包装命令执行 `python -m uuma.session run --`，确保幂等受控 |
| `projections.py` | 将事件流投影为三层逻辑图：能力图 (Capability)、工作图 (Work)、运行图 (Run) |
| `mcp_control.py` | **UuMA Control MCP**：专供 Orchestrator 使用的高级控制与任务调度接口 |
| `mcp_worker.py` | **UuMA Worker MCP**：专供各 Specialist Agent 注册 Direct Run、汇报进度与提交结果 |
| `auth.py` | 身份验证与 Token 管理 (`tokens.json`) |
| `api.py` | FastAPI HTTP 控制端点（默认监听 `127.0.0.1:8766`） |

### 2.2 专业领域子系统模块

1. **Honc 执行领域 (`src/uuma/honc/`)**:
   - `models.py`: 回合 (`RoundSession`)、打卡 (`HabitEntry`)、执行事实 (`ExecutionFact`)、动作决策与回执模型。
   - `store.py`: `honc.db` 独立 SQLite 存储，保证执行流水与控制状态隔离。
   - `service.py`: `HoncService`，实现回合计时、标准核对、工时统计与防重复打卡。
   - `graph_client.py`: 对接 Yonc Graph 项目系统的安全客户端（只写受限的 action-decisions）。
   - `mcp.py`: `honc-execution` FastMCP 服务器，向 Honc 暴露 10 个高内聚语义工具。

2. **Wisdom 知识与探索领域 (`src/uuma/knowledge_*`, `wisdom_*`, `kag_*`)**:
   - `knowledge_models.py` & `knowledge_store.py`: 证据、事实、声明、冲突与知识地图持久化 (`wisdom.db`)。
   - `knowledge_service.py` & `mcp_knowledge.py`: Knowledge MCP 语义门面，提供原子知识提取与检索。
   - `question_orbit.py` & `orbit_runner.py`: **Question Orbit 引擎**，对未闭合的重要科学/工程问题发起自动化探索轨道。

3. **实验室与硬件领域 (`src/uuma/lab_*`, `forge_journal*`, `order_workbook.py`)**:
   - `lab_inventory.py`: 物料库存台账与批次管理（真实库存 != 订单历史）。
   - `forge_journal.py` & `forge_journal_runner.py`: Notion “锻造日志与工程经验”的异步可靠同步器。
   - `lab_procurement.py`: 采购建议与询价比较（绝不自行付款下单）。

4. **辅助适配层**:
   - `chatgpt_server.py` & `chatgpt_bridge.py`: 浏览器受控 ChatGPT 会话桥接（深度网络调研）。
   - `brainstormer_state.py` & `brainstormer_planning.py`: 头脑风暴讨论状态与容量计算。
   - `eschematic_bridge.py`: 与外部电路设计系统 eSchematic 的单向只读与提案桥接。
   - `copycat_contract.py`: 与 CopyCat 电脑操作录制/回放系统的严格契约。

---

## 三、 多 Agent 团队人员名录与职责边界 (Colleague Directory & Roles)

在 UuMA 体系中，每个 Agent（或称“同事”）都有极其严格的职责分工、输入输出契约与绝对禁区：

```text
               +-----------------------------------------+
               |   User (战略决策 / 最终验收 / 敏感授权)   |
               +-----------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                      Orchestrator (Hermes 默认 Profile)                  |
|          任务契约创建 | 跨 Agent 路由 | 运行监控 | 受控电脑控制           |
+------------------------------------------------------------------------+
       |                  |                  |                  |
       v                  v                  v                  v
+--------------+   +--------------+   +--------------+   +--------------+
|     Yonc     |   |     Honc     |   |Wisdom-Oldman |   |    Scholar   |
|  项目管理与  |   |  日常执行与  |   |  长期知识与  |   |  科学研究与  |
|  任务拆解    |   |  追踪管家    |   |  问题轨道    |   |  论文实验    |
+--------------+   +--------------+   +--------------+   +--------------+
       |                  |                  |                  |
       v                  v                  |                  |
[ Yonc Graph ]    [ Yonc Graph ]             |                  |
(项目结构 SoT)     (叶子 ACTION 回写)         |                  |
                                             v                  v
+------------------------------+     [ wisdom.db ]       [ RSTV4 论文池 ]
|        锻造Lab_Bot           |     (原子知识图谱)       (学术证据/稿件)
|  硬件库存与工程记录          |
+------------------------------+
               |
               v
     [ Notion 锻造日志 ]
```

---

### 1. 🧑‍✈️ Orchestrator（总指挥官）
- **身份定位**: 系统的总入口与总协调者（Hermes 默认 Profile）。
- **主要职责**:
  1. 将用户的高阶意图转化为显式的 **Task Contract**。
  2. 根据登记的 Agent 能力进行路由 (`route_task`) 与任务指派 (`assign_task`)。
  3. 监控各 Specialist Agent 的运行状态，汇总跨 Agent 成果。
  4. 拥有最高级别的外部交互控制权（受控电脑操作、CopyCat 动作审查、ChatGPT Bridge 调度）。
- **适合的工作**: 任务分派、多 Agent 流程串联、异常诊断与恢复、受控 UI 自动化。
- **输入**: 用户高层目标、约束条件、预算与权限范围。
- **输出**: Task Contract、Run Receipts、跨 Agent 综合交付物。
- **绝对禁区**:
  - 严禁未经用户显式确认执行 `COMMITTING`（高危/修改外部环境）动作。
  - 严禁替专家 Agent 伪造专业领域数据。
  - 严禁跳过 UuMA Control MCP 直接静默分派多步任务。

---

### 2. 🛸 Honc（日常执行与追踪管家）
- **身份定位**: 守护用户的真实执行现场（Daily Execution & Tracing Specialist）。
- **主要职责**:
  1. 读取 Yonc Graph 中当前 Main/Support 项目的叶子 ACTION。
  2. 引导用户进入专注回合（🛸 定目标/微动作 -> 🍅 25 分钟番茄专注 -> 查回产出）。
  3. 记录真实执行事实（做了什么、投入时长 Actual、Next、Blocker）。
  4. 严格对照 `done_when` 标准核对完成度，发起 Graph 动作决策并保存回执。
  5. 管理每日习惯打卡与执行日志。
- **核心思维模型（严分三件事）**:
  - ① **做过什么（执行事实）**: 哪怕任务没做完，也忠实记录实际产出和时长。
  - ② **是否达标（Done 核对）**: 仅当用户明确说做完、属于叶子 ACTION、且产出完全符合 `done_when` 标准时才算达标。
  - ③ **是否同步成功（系统回执）**: 调用接口拿到 `ExecutionReceipt` 才算同步完成。
- **专属工具**: `honc-execution` MCP (`honc_control_round`, `honc_record_execution`, `honc_check_habit`, `honc_assess_completion`, `honc_apply_completion`, etc.)。
- **绝对禁区**:
  - **严禁修改项目树**：绝不增删节点、绝不修改里程碑、绝不调整父子关系与优先级。
  - **严禁擅自标记父任务完成**：只能操作叶子 `ACTION`，项目和模块的完成归 Yonc/用户。
  - **严禁模糊打 Done**：没有明确 `done_when` 或产出不足时，只记执行事实，绝不误标完成。

---

### 3. 📐 Yonc（项目管理与规划专家）
- **身份定位**: 整个 Graph Project System（Yonc Graph）的管理者与规划参谋。
- **主要职责**:
  1. 梳理项目结构与拓扑依赖（L1 Goal -> L2 Deliverable -> L3 Work Package -> L4 Action）。
  2. 针对高阶目标进行递归任务拆解，生成暂存草稿 (Split Draft)。
  3. 基于同事能力名录 (`colleague_directory`) 提出有理有据的分工建议。
  4. 结合 Honc 记录的实际投入工时与 Blocker，审阅项目整体进度。
- **适合的工作**: 目标结构化拆解、排期与容量评估、跨项目依赖分析、分工建议。
- **专属工具**: `yonc-project` FastMCP（读写图草稿、查询拓扑）、`yonc-colleagues` 技能。
- **绝对禁区**:
  - **草稿提交必须经过可信 UI 授权**：在直接对话中生成的拆分方案只是草稿，必须由用户在前端点击授权凭据后方可合入主图。
  - **不直接调度其他 Agent 执行**：Yonc 只提出分工建议，具体任务下发归 Orchestrator。

---

### 4. 👴 Wisdom-Oldman（长期知识专家）
- **身份定位**: 发现、提炼、维护与检索长期可持续的领域/世界知识。
- **主要职责**:
  1. 从第一性原理、理论机理、边界条件与失败案例出发分析问题。
  2. 提取原子知识候选并构建版本化知识地图（存入 `wisdom.db` / KAG）。
  3. 识别高价值知识缺口，启动 **Question Orbit（问题轨道引擎）** 持续追踪。
  4. 提供带有确切来源出处、边界条件与争议冲突的最佳回答。
- **适合的工作**: 复杂机制探索、文献与事实冲突调查、知识图谱维护、技术方案背景调研。
- **专属工具**: `mcp_knowledge` (`knowledge_question_preflight`, `knowledge_query`, `orbit_*`)。
- **绝对禁区**:
  - 严禁无来源推断：不能将泛化置信度替代上下文约束条件；冲突来源必须并存展示。
  - 严禁自行增加研究预算或擅自批准正式知识补丁。

---

### 5. 🔬 Scholar（科学研究与文献专家）
- **身份定位**: 证据驱动的科学研究全生命周期专家。
- **主要职责**:
  1. 遵循科学链路：`Evidence -> Validated Gap -> Idea -> Method -> Test -> Claim`。
  2. 维护领域知识库 (FieldKG)，对接 RSTV4 论文池 (PaperPool) 管理 DOI、BibTeX 与全文 PDF。
  3. 组织跨尺度研究体系（`Field -> Topic -> Track -> Project`），推进学术论文手稿撰写与同行评审准备。
- **适合的工作**: 文献计量与综述、科学研究缺口论证、实验方案起草、学术论文写作。
- **专属工具**: RSTV4 PaperPool 客户端、FieldKG 检索。
- **绝对禁区**:
  - 严禁无 PDF 证据推论：未验证全文的论文不可引作核心结论证据。
  - 严禁私自执行实验：所有实验只能通过 RSTV4 已批准的受控实验方案运行。
  - 核心主张与投稿发表完全由人类用户审定。

---

### 6. 🛠️ 锻造Lab_Bot（硬件实验室与工程记录专家）
- **身份定位**: 将设计意图与物理世界连接的硬件实验室管家。
- **主要职责**:
  1. 管理元器件实物库存、采购批次与存放仓位 (`lab_inventory`)。
  2. 追踪电路板贴片、整机装配与 As-Built 实物配置。
  3. 引导用户通过自然对话记录实验室调试、维修、排障日志，并持久化到 Notion 锻造日志。
  4. 从故障现象与装配偏差中提炼候选工程经验 (Candidate Engineering Lessons)。
- **核心思维模型（严守物理现实）**:
  - `设计 BOM (Designed BOM)` ≠ `实物装配 BOM (As-Built BOM)`。
  - `采购记录` ≠ `实物库存`（未收货/未入库不算现有库存）。
  - `工作日志` ≠ `工程经验`（经验必须经受审查方可升级为规则）。
- **专属工具**: `lab-inventory` 技能、`forge_journal` 异步同步器、`eschematic-bridge`。
- **绝对禁区**:
  - **绝不付款与下单**：仅提供采购对比建议，绝不执行支付操作。
  - **绝不直接通电或驱动硬件**：不操作继电器、电源、电机等物理危险设备。

---

### 7. 💡 Brainstormer（深度思考与方案设计伙伴）
- **身份定位**: 釐清模糊问题、挑战潜在假设、收敛方案并输出可落地工程产物的思考伙伴。
- **主要职责**:
  1. 识别核心矛盾与隐藏假设，对用户初步想法进行良性挑战与多维度对比。
  2. 建立量化决策模型与生产/算力容量测算。
  3. 推动讨论逐步收敛，产出高完备度的 PRD、架构决策草案或技术规格书。
- **适合的工作**: 需求框定、技术路线权衡、架构推演、数学/产能模型验算。
- **专属工具**: `brainstorming-method`, `quantitative-decision-model`, `discussion-checkpoint`, Gemini Worker（辅助实现推演）。
- **绝对禁区**:
  - 不代替领域专家证据（科学听 Scholar，硬件听 Lab_Bot，知识听 Wisdom）。
  - 不擅自决定项目结构或指派其他 Agent。

---

### 8. 🔌 关键外部依赖与支撑服务

| 支撑组件 | 作用与定位 | 交互方式 |
|---|---|---|
| **Yonc Graph** (`yonc-graph`) | 独立运行的 DAG 画布、时间轴、甘特图与产能网格服务端（端口 8766） | FastMCP (`yonc-project`) + REST API (`/api/v2/execution/action-decisions`) |
| **eSchematic** | 电路元器件模型库、原理图设计与官方设计 BOM 的权威源 | 通过 `eschematic_bridge.py` 只读查询与提交反馈提案 |
| **CopyCat MCP** | 受控电脑屏幕观测与录制回放服务，辅助爬虫避障与流程重放 | 仅限 Orchestrator 受限调用，严禁涉及支付与账密操作 |
| **ChatGPT Web Bridge** | 本地运行的浏览器网桥，为 Agent 提供高级搜索与深度研究支持 | 本地 HTTP 网桥 (`chatgpt_server.py`)，受专属 Token 鉴权保护 |
| **Gemini Worker** | 针对明确上下文、受限代码文件的低开销子任务执行器 | 通过 `gemini_worker.py` 执行确定性转换 |

---

## 四、 智能体协作全流程示例：从一个想法到完成闭环

```text
[1. 需求探索]
用户与 Brainstormer 交流模糊想法 -> 挑战假设 -> 形成技术规格与架构 PRD

[2. 项目立项与拆解]
Yonc 读取 PRD -> 在 Yonc Graph 中拆解出 WBS 结构 (Goal -> Deliverable -> Work Package -> Action)
-> 标明每项 Action 的 done_when 验收标准 -> 用户在 UI 点击批准提交

[3. 任务路由与下发]
Orchestrator 检查当前 Main 目标 -> 建立 Task Contract -> 路由给对应的 Specialist Agent (或留给用户亲自做)

[4. 真实执行与专注]
用户开始干活 -> Honc 启动 🛸 准备回合 (明确目标与切入动作) -> 开启 🍅 番茄专注 (25min) -> 结束记录实际工时与成果

[5. 验收与双向同步]
Honc 逐项核对任务当时的 done_when -> 确认达标 -> 向 Yonc Graph 发起 action-decisions (标记 done 并保存 ExecutionReceipt)
-> 产生每日执行报告

[6. 知识与工程沉淀]
执行中发现的未知物理/代码现象 -> 锻造Lab_Bot 沉淀到 Notion 日志 / Wisdom-Oldman 归入 wisdom.db 知识库
```

---

## 五、 Agent 开发者/运维者常用指令与自测速查

1. **环境与依赖初始化**:
   ```bash
   ./init.sh              # 初始化 .venv、安装依赖、构建本地隔离数据库
   ```

2. **运行后端契约测试**:
   ```bash
   .venv/Scripts/python.exe -m pytest tests/              # 运行全部契约与集成测试
   .venv/Scripts/python.exe -m pytest tests/test_honc_*.py # 专门运行 Honc 执行测试
   ```

3. **代码风格与规范检查**:
   ```bash
   .venv/Scripts/python.exe -m ruff check src tests       # 100 字符限制检查
   ```

4. **启动 UuMA 控制平面服务**:
   ```powershell
   .\scripts\start-uuma.ps1                               # 启动本地 8766 审计与控制端点
   ```

5. **利用 CodeGraph 探测代码上下文**:
   ```bash
   codegraph.cmd status                                   # 查看当前索引状态
   codegraph.cmd query "<symbol>"                         # 搜索符号定义
   codegraph.cmd files                                    # 查看代码拓扑树
   codegraph.cmd context "<task description>"             # 为某项开发任务构建代码上下文
   ```
