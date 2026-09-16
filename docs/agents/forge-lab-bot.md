# 锻造Lab_Bot

Status: consolidated design record  
Agent type: customized persistent Hermes profile  
Primary role: hardware-lab operations and engineering memory  
Source: `chatgpt-conversation://6a8d3f19-c4c4-83ec-8342-bbd5d823e0a3`

## 1. Mission

锻造Lab_Bot is the hardware-domain worker in UuMA. It connects design intent to the physical lab: parts, stock, procurement, builds, as-built configuration, failures, repairs, and reusable engineering lessons.

Its closed loop is:

```text
eSchematic design and BOM
        v
Inventory availability
        v
Procurement need
        v
Receiving and stock
        v
Physical build
        v
As-built traceability
        v
Worklog and findings
        v
Candidate engineering lessons
        v
Validated feedback
        +-- eSchematic rule/recommendation
        +-- procurement warning/preference
        +-- build-process knowledge
        +-- troubleshooting knowledge
        v
Next design and build
```

## 1.1 Architectural Concept Hierarchy and Top-Level Systems

To avoid conceptual conflation across system projects, agent profiles, capability modules, and hardware build examples, the architecture defines four distinct levels:

### 1. Two Core Systems & Domain Authorities

- **`eSchematic` (Design Authority)**:
  - Component catalog (exact MPN, pinouts, electrical specs)
  - Schematic design & circuit graphs (Circuit IR)
  - Design BOM & normalization
  - Design revisions & immutable manifests
  - Electrical validation (ERC)
- **`forge-lab-bot` / `锻造Lab_Bot` (Physical Lab & Engineering Memory Authority)**:
  - Inventory ledger & location tracking
  - Purchase lots, order history, and receiving inspection
  - Physical builds and As-Built configuration tracking
  - Commissioning, testing, calibration, and repair records
  - Worklogs, failure analysis, and candidate engineering lessons

### 2. Supporting Roles

- **`Hermes`**: Top-level orchestrator responsible for routing, inter-agent coordination, and system audit logging.
- **`Notion`**: Source of Truth for raw human worklogs and Lab Journals (`Problem Faced`, `Trace Record`).
- **`Procurement`**: Sourcing search and market quotation observation capability, situated as a sub-capability/sub-agent under `forge-lab-bot` rather than an independent top-level system.

### 3. Hardware Project Instances (Data, Not Systems)

Entities such as `UGV`, `Motor Controller`, and `BUILD-MOTOR-001` are physical projects or specific build instances tracked within the lab database; they are not independent software systems or top-level agent roles.

### 4. Skillset Layout and Bridge Boundary

```text
eSchematic
└── eSchematic_skillset
    ├── component-catalog
    ├── schematic-design
    ├── design-bom
    ├── design-revision
    ├── electrical-validation
    └── design-manifest-export

锻造Lab_Bot
└── forge_lab_skillset
    ├── inventory
    ├── receiving
    ├── procurement-advice
    ├── build-traceability
    ├── as-built
    ├── commissioning
    ├── worklog
    ├── failure-analysis
    └── engineering-lessons

Integration
└── eschematic-bridge
    ├── read component/design data
    ├── import immutable design revision
    └── submit design-feedback proposal
```

Key Boundary Rule: `eSchematic_skillset` belongs strictly to eSchematic and is not embedded into `forge-lab-bot`. `forge-lab-bot` accesses design records solely through `eschematic-bridge` (read-only for canonical parts and immutable revisions; proposal-only for design feedback) and cannot directly mutate eSchematic authoritative state.

## 2. Responsibility boundary

锻造Lab_Bot owns:

- physical inventory state and locations;
- inventory movement ledger;
- purchase lots, receiving, and procurement decision records;
- build identity and as-built state;
- substitutions, repairs, calibration, and modification history;
- structured findings and engineering lessons derived from worklogs;
- operational feedback to design, procurement, build process, and maintenance.

It collaborates with but does not replace:

- `eSchematic`, which owns component definitions, schematics, and design BOM revisions;
- Notion, which currently owns raw human lab worklogs;
- procurement connectors or subagents, which search external marketplaces;
- Wisdom-Oldman, which provides external theory, datasheets, and evidence;
- Scholar, which owns scientific interpretation of experimental evidence;
- Hermes, which orchestrates the overall system.

## 3. Main capabilities

### Stockkeeper

Maintains inventory quantities, locations, condition, reservations, installation state, and purchase-lot provenance.

### Lab Journal / Worklog

Reads or appends practical hardware work records and conservatively structures observations, hypotheses, actions, results, and follow-up needs.

### eSchematic and build traceability

Consumes an immutable design revision and normalized BOM, creates a physical build record, and tracks the actual as-built configuration over time.

### Procurement

Converts BOM shortages or user needs into sourcing searches, compares offers and substitutes, records provenance, and returns recommendations or direct links. Purchase authorization remains with the user unless explicitly delegated within a defined policy.

Procurement may be implemented as a specialized subagent plus browser/MCP connectors. Marketplace adapters are capabilities, not the identity of Lab_Bot. Orchestrator-coordinated CopyCat and computer UI automation may be leveraged to expand search terms and navigate complex storefronts or overcome stealth web crawling hurdles, but are strictly restricted from executing payments, checking out, or entering financial credentials.

## 4. Federated source of truth

The accepted architecture is federated. One type of fact has one authority.

| Data | Authority |
|---|---|
| Exact component identity, manufacturer, MPN, pins, electrical specifications | eSchematic catalog |
| Schematic and design BOM revision | eSchematic |
| Inventory quantity, location, condition, and movement | Lab_Bot `lab.db` |
| Purchase lot, supplier offer snapshot, order, and receiving | Lab_Bot `lab.db` |
| Physical build and as-built configuration | Lab_Bot `lab.db` |
| Raw `Problem Faced` / `Trace Record` / worklog text | Notion |
| Structured finding and lesson | Lab_Bot derived state, linked to source worklog |
| External marketplace listing | External source plus timestamped Lab_Bot snapshot |

Other systems may cache display values, but those caches do not become a second authority.

## 5. Part identity

The component-catalog identity rules inherited from eSchematic are:

```text
Exact manufactured part
= manufacturer + exact manufacturer part number

Generic component without MPN
= stable internal component ID

Supplier SKU or listing name
= alias or offer reference
!= canonical component identity
```

Three different concepts must remain separate:

```text
Exact Component Identity
Engineering Equivalence
Inventory Stock Group
```

Two exact components can be engineering substitutes without becoming the same manufactured identity. Equivalence is contextual and may depend on circuit, package, rating, tolerance, firmware, mechanical fit, or approved design constraints.

For modules and informal parts such as `IBT-2`, aliases help resolve names and images, while purchase lots preserve seller and variant provenance.

## 6. Purchase lots and physical assets

Inventory does not require a unique serial number for every resistor. Identity depth depends on value.

Suggested levels:

```text
Component definition
    v
Purchase lot
    v
Physical asset, only when individually valuable or traceable
```

A purchase lot records:

- component reference;
- supplier and offer reference;
- order and received quantities;
- price and currency;
- purchase and receiving dates;
- lot-specific photos or markings;
- accepted, rejected, or defective counts;
- source links and captured listing data.

Individual assets are appropriate for machines, instruments, expensive modules, calibrated devices, or components whose unique history matters.

## 7. Inventory lifecycle

Inventory is event-driven. The system does not directly overwrite a single quantity field.

First-wave buckets:

```text
AVAILABLE
RESERVED
INSTALLED
DAMAGED
CONSUMED
```

`ORDERED` or `INCOMING` remains procurement state and is not counted as owned stock until receiving is completed.

Example events:

```text
RECEIVE         external  -> available
RESERVE         available -> reserved
RELEASE         reserved  -> available
INSTALL         reserved  -> installed
UNINSTALL       installed -> available
MARK_DAMAGED    any       -> damaged
REPAIR          damaged   -> available
CONSUME         available -> consumed
SCRAP           damaged   -> external
ADJUST          reconciliation event with reason and evidence
```

Current quantities are derived from the ledger. Every material adjustment preserves actor, time, quantity, reason, and related build or purchase lot.

## 8. Location model

The system must eventually answer both `How many?` and `Where?`.

Locations form a stable hierarchy, for example:

```text
Lab
  +-- Cabinet A
      +-- Drawer 03
          +-- Box 07
```

V1 may use a simple location reference, but the schema should support parent-child locations, moves, unknown locations, and reconciliation.

## 9. Receiving

Procurement does not change stock by itself.

```text
Order
  v
Arrival
  v
Receive and inspect
  +-- accepted
  +-- defective
  +-- missing
  +-- wrong item
  v
Inventory event
```

Receiving connects the real item to its purchase lot and canonical component reference. Photos or user speech may assist extraction, but uncertainty must remain explicit until confirmed.

## 10. Design revision, build, and as-built

These are separate objects:

```text
Design Revision
= how the system should be built

Build
= a particular physical instance

As-Built Revision
= what that physical instance actually is at a point in time
```

### Design revision

Owned by eSchematic and immutable after a physical build references it.

### Build

Owned by Lab_Bot and references exactly one originating design revision.

### As-built revision

Records actual components, substitutions, wiring changes, firmware/configuration, mechanical changes, calibration, repairs, and modifications.

```text
DESIGN REV-A
   +-- BUILD-001
   |     +-- ASBUILT-1
   |     +-- ASBUILT-2
   |     +-- ASBUILT-3 current
   +-- BUILD-002
```

The designed BOM is not the as-built BOM. Inventory reservation can use the designed BOM, while final installation events and build traceability use confirmed as-built data.

## 11. Worklog model

The existing Notion `Problem Faced` and `Trace Record` are the raw Lab Journal. The user can continue writing naturally; Lab_Bot structures the content in the background.

Minimum semantic fields:

```text
Date
Project / machine / build
Action
Issue
Observation
Suspected cause
Confirmed cause
Solution or action taken
Result
Parts involved
Next action
Source reference
```

Fields may be unknown. The essential epistemic distinction is:

```text
Observation != Hypothesis != Confirmed cause
```

The raw source is never overwritten by the derived interpretation.

## 12. Engineering-learning pipeline

Worklog-derived learning has four levels:

```text
1. Worklog
   raw account of what happened

2. Finding
   structured observations, actions, and confirmed facts

3. Engineering Lesson
   reusable interpretation with scope and evidence

4. Operational Rule
   validated constraint or recommendation used by another system
```

The promotion path is conservative:

```text
Worklog
  v
Extraction
  v
Candidate lesson
  v
Evidence accumulation
  v
Human or engineering validation
  v
Accepted lesson
  v
Optional rule, warning, recommendation, or preference
```

Worklogs must never automatically become mandatory engineering rules.

## 13. Lesson model

Lesson status:

```text
CANDIDATE
SUPPORTED
ACCEPTED
DEPRECATED
REJECTED
```

A lesson preserves:

- statement;
- scope and applicable contexts;
- evidence references;
- confidence;
- status;
- exceptions;
- affected systems;
- superseding or rejection reason.

One ambiguous event can produce a diagnostic candidate, but not a universal root-cause rule. Evidence can accumulate across builds, worklogs, datasheets, and calculations. Lessons must be correctable and may be deprecated, rejected, or superseded.

## 14. Feedback targets and severity

Feedback targets may include:

```text
LAB_ONLY
ESchematic
PROCUREMENT
BUILD_PROCESS
STOCKKEEPER
TOOL_MAINTENANCE
```

Feedback strength:

```text
BLOCK
WARN
RECOMMEND
PREFERENCE
KNOWLEDGE
```

Examples:

- a verified voltage incompatibility may become an eSchematic or procurement `BLOCK`;
- a possible decoupling improvement may be a design `RECOMMEND`;
- repeated seller-quality evidence may become a procurement `WARN` or `PREFERENCE`;
- symptom-to-possible-cause information remains troubleshooting `KNOWLEDGE`.

Safety-critical rules require stronger evidence, such as worklogs plus calculations, datasheets, or explicit engineering approval.

## 15. Design feedback

Lab_Bot does not directly edit authoritative schematics.

```text
Observed build evidence
   v
Design Feedback Proposal
   v
eSchematic review
   v
New immutable design revision if accepted
```

A proposal records the target design, observed change, linked builds, outcome evidence, confidence, and recommended evaluation.

## 16. Procurement feedback

Procurement learning is categorized as:

- compatibility knowledge;
- supplier or lot quality evidence;
- product preference;
- search terminology and alias knowledge;
- raw-material or tool alternatives;
- price and availability observations.

A single failed component does not prove the seller is bad. Failure attribution may remain unknown. Supplier-quality conclusions require comparable evidence, repeated failures, or another defensible basis.

## 17. Procurement operating model

The first goal is BOM sourcing, not fully autonomous purchasing.

```text
BOM need
   v
Canonical part and acceptable substitutions
   v
Search-term expansion
   v
Multi-platform offers
   v
Specification, price, seller, and risk comparison
   v
Shortlist with direct source links
   v
User purchase decision
```

Useful sources may include LCSC, 1688, Taobao, PDD, manufacturer sites, distributors, and local shops.

Marketplace constraints and UI automation boundaries:

- login, session expiry, CAPTCHA, and dynamic UI may require human intervention;
- use real signed-in browser sessions and low-frequency searches where appropriate;
- pause for human login or CAPTCHA rather than attempting to bypass protections;
- Orchestrator-coordinated CopyCat and computer UI control may be used to expand search terms into marketplace search inputs, interact with category filters, and overcome stealth web crawling hurdles on dynamic storefronts;
- **Strict payment restriction**: CopyCat and UI automation are strictly restricted from making payments, checking out, or executing any financial transactions; purchase authorization and payment execution remain 100% with the human engineer;
- store source URL and capture time because listings change;
- separate advertised specifications from verified manufacturer specifications;
- treat marketplace data as external observation, not timeless truth.

PDD may be supported later or opportunistically, but it should not be the primary V1 source because of stability and access constraints.

## 18. Suggested operational database

`lab.db` is the authority for the physical lab state. First-wave objects may include:

```text
component_refs
part_aliases
equivalence_rules
purchase_lots
supplier_offers
orders
receiving_records

locations
inventory_events
inventory_balances derived

builds
as_built_revisions
as_built_events
firmware_and_config_refs

worklog_refs
findings
lessons
feedback_proposals
operational_rules
```

The component catalog itself remains in eSchematic.

## 19. Collaboration contracts

### With eSchematic

Consumes component IDs, design revisions, and normalized BOMs. Returns availability, as-built substitutions, and reviewed design feedback proposals.

### With Wisdom-Oldman

Consumes datasheets, theory, safety guidance, and external evidence. Returns observed physical evidence that may enrich reusable knowledge after review.

### With Scholar

Supplies experiment hardware configuration, calibration, deviations, failures, and as-built provenance. Scholar owns scientific interpretation.

### With Brainstormer

Supplies feasibility, cost, component, risk, and physical-evidence input to design discussions. Brainstormer owns project reasoning and decisions.

### With Hermes Orchestrator

Exposes lab status, inventory shortages, approval requests, procurement options, build progress, and safety-critical blockers.

## 20. Locked decisions

- The canonical display name is `锻造Lab_Bot`.
- Lab_Bot is a hardware-domain agent; procurement connectors are tools or subservices.
- The architecture uses federated sources of truth.
- eSchematic owns the component catalog and design BOM.
- Lab_Bot owns inventory, purchase lots, builds, as-built state, and derived lab lessons.
- Notion remains authority for raw worklogs in the current design.
- Exact component identity, engineering equivalence, and inventory grouping remain distinct.
- Inventory is ledger/event-driven.
- Ordered items are not stock until received.
- Design revision, build, and as-built revision are separate and versioned.
- Observation, hypothesis, and confirmed cause remain separate.
- Worklogs produce candidate lessons, never immediate mandatory rules.
- Engineering lessons retain evidence, scope, confidence, status, and correction history.
- Design changes go through proposals and review.
- Procurement V1 stops at reliable sourcing and comparison; Computer UI control and CopyCat may be leveraged via the Orchestrator for search term expansion and overcoming stealth web crawling hurdles, but are strictly restricted from making payments.

## 21. Open design work

- Define the Notion bidirectional sync / webhook connector for real-time human journal sync.
- Define substitute approval rules and equivalence scopes.
- Define multi-vendor procurement offer normalization and trust rating algorithms.
- Define safety-critical action and automated rule-approval policies with orchestrator escalation.
- Define photo/vision-assisted part identification and SMD marking resolution.

## 22. Implemented Skills and MCP Tool Mapping

The following table records the canonical mapping between the nine `forge_lab_skillset` domains, the integration bridge, and their implemented MCP tools in `uuma-worker`:

| Skill Domain | Hermes Skill (`profiles/forge-lab-bot/skills/`) | `lab.db` Backing Tables | Authoritative MCP Tools (`src/uuma/mcp_worker.py`) |
|---|---|---|---|
| **Inventory** | `lab-inventory` | `locations`, `inventory_events`, `component_refs` | `inventory_status`, `inventory_create_location`, `inventory_get_balances`, `inventory_transition`, `inventory_adjust`, `inventory_preview_or_import_legacy_rows` |
| **Receiving** | `lab-receiving` | `purchase_lots`, `purchase_history_lines`, `legacy_import_rows` | `inventory_receive`, `inventory_preview_or_import_order_workbook`, `inventory_list_purchase_history`, `inventory_resolve_purchase_history_line` |
| **Procurement Advice** | `lab-procurement-advice` | `sourcing_requirements`, `supplier_offers`, `sourcing_evaluations`, `sourcing_term_rules`, `purchase_lots` | `lab_analyze_bom`, `procurement_create_requirement`, `procurement_list_requirements`, `procurement_create_requirements_from_shortages`, `procurement_expand_terms`, `procurement_save_term_rule`, `procurement_parse_offer_snippet`, `procurement_record_offers`, `procurement_list_offers`, `procurement_evaluate_sourcing`, `procurement_confirm_order`, `procurement_check_crawler_status`, `procurement_auto_search_and_evaluate`, `inventory_get_balances` |
| **Build Traceability** | `lab-build-traceability` | `builds` | `lab_create_build`, `lab_list_builds`, `lab_update_build_status` |
| **As-Built** | `lab-as-built` | `builds`, `inventory_events` | `lab_get_current_as_built`, `inventory_transition` |
| **Commissioning** | `lab-commissioning` | `commissioning_records` | `lab_record_commissioning`, `lab_list_commissioning` |
| **Worklog** | `lab-worklog` | `worklog_records` | `lab_record_worklog`, `lab_list_worklogs` |
| **Failure Analysis** | `lab-failure-analysis` | `failure_records` | `lab_record_failure`, `lab_list_failures`, `inventory_transition` |
| **Engineering Lessons** | `lab-engineering-lessons` | `engineering_lessons` | `lab_propose_lesson`, `lab_list_lessons`, `lab_update_lesson_status` |
| **eSchematic Bridge** | `eschematic-bridge` | `design_feedback_proposals` + external eSchematic | `eschematic_get_component`, `eschematic_list_components`, `eschematic_find_components`, `eschematic_commit_candidate`, `eschematic_normalize_bom`, `eschematic_export_design_manifest`, `eschematic_validate_circuit`, `eschematic_check_electrical_rules`, `eschematic_submit_design_feedback`, `eschematic_list_design_feedback` |

## 23. Architecture Status and Roadmap Baseline (2026-09 Consolidation)

This section formally records the status review and user decisions from the canonical design consolidation:

### 1. 骨骼与大脑（Brain & Skeleton: 90% Completed, 10% Pending）

- **已完成（90%）**：
  - 不可变事件驱动库存流水账本（`inventory_events`，5 大状态桶与防负库存断言）。
  - 多级物理仓位层级树（`locations`）。
  - 物理制造追溯与 As-Built 真实构型投影（`builds`, `current_as_built`）。
  - 硬件调试、通电、温升与标定记录（`commissioning_records`）。
  - 认识论隔离工作日志（`Observation != Hypothesis != Confirmed Cause`）。
  - 硬件故障等级与根因归因（`failure_records`）。
  - 工程经验晋升漏斗（`engineering_lessons`，`CANDIDATE` -> `ACCEPTED` 审核流）。
  - 对 eSchematic 的单向设计变更提案桥（`design_feedback_proposals`）。
  - 身份鉴权的 MCP Worker 工具集与 62 项全覆盖自动化测试套件。
- **待完善的大脑逻辑（10%）**：
  - 调试日志到候选经验的自动分析与草稿提炼触发器（Auto-Extraction Trigger）。
  - 元器件“等效替换（Equivalence & Substitution）”规则表与兼容性算法。
  - 安全临界规则（`BLOCK` 级别经验）的自动化设计校验拦截 Hook。
  - 批次库存采购价加权与 As-Built 物理机器真实制造成本滚动汇总（Cost Roll-up）。

### 2. 手与眼（Hands & Eyes: 战略决策与优先级排期）

| 外部感知与执行能力 | 战略定位 | 当前进度 | 实施决议 |
|---|---|:---:|---|
| **“眼”：元器件视觉辨识（Vision Part Resolver）** | 拍照看形状/丝印识别元器件 | 0% | **暂缓（Deferred）**：暂不进行多模态/OCR 丝印识别开发，依赖文本 MPN 与别名维护。 |
| **“耳目”：Notion 实时双向同步（Live Notion Connector）** | 实时拉取与回写 Notion 实验日志 | 0% | **暂缓（Deferred）**：暂不进行 Notion API 与实时 Webhook 对接，当前以本地结构化 Worklog 为准。 |
| **“手”：采购比价与寻源引擎（Procurement Engine）** | 缺料搜索、多平台比价、店铺打包优化 | 90% | **方案 C 核心就绪（Phase 1 + Chrome Crawler Delivered）**：数据模型、寻源需求、关键词规则、报价快照、多策略比价（最低到手价/单店打包/自制替代）、下单批次闭环以及基于本地真实 Chrome 持久会话的淘宝/1688 自动抓取与人机滑块兜底引擎已全部落地。 |

## 24. Procurement Engine Design Blueprint (手 - 采购引擎规划)

作为当前阶段唯一重点推进的“执行手”能力，采购引擎将按以下阶段落地为 `forge-lab-bot` 的专属子能力：

```text
BOM Shortage / User Need
         v
1. Search Term Expansion (MPN, Aliases, Package, Raw Materials)
   - CopyCat UI automation: assists entering terms and navigating search interfaces
         v
2. Multi-Platform Browser Connectors (Taobao, 1688, LCSC, PDD)
   - Persistent session / Cookie profile
   - Human-in-the-loop for 2FA / CAPTCHA
   - Low-frequency, stealth request throttling
   - CopyCat / UI control: assists overcoming stealth crawling, dynamic DOMs, and filters
         v
3. Offer Parsing & Normalization (Price, Shipping, MOQ, Seller Rating)
         v
4. Sourcing Optimization
   - Shop-in-store pricing advantage
   - Single-shop packaging (save shipping) vs distributed lowest price
   - First-principles alternative (raw materials + standard tooling)
         v
5. Direct Link Comparison Matrix (Clickable URLs for Human Checkout)
   - Hard boundary: STRICTLY RESTRICTED FROM MAKING PAYMENT (human-only final payment)
```


