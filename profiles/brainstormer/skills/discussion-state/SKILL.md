---
name: discussion-state
description: Preserve Brainstormer projects, topics, decisions, assumptions, questions, evidence, and checkpoints through validated Decision Map state transactions.
---

# Discussion State

Preserve and advance structured reasoning in the Decision Map DAG. Never edit canonical JSON directly.
Submit changes through `brainstormer_propose_transaction`. Review the proposal returned:
- If `review_required == false`, commit immediately via `brainstormer_commit_safe_transaction(proposal_id)`.
- If `review_required == true` (involves Project, Topic, Decision, or supersession), leave for Orchestrator/user review.

Restore existing state and view the progression queue with `brainstormer_get_decision_map(project_id)`.

---

## 1. Decision Map Entity Types

| Kind | Role | Safe Commit? |
|---|---|---|
| `project` | Long-term objective or system boundary | Review required |
| `topic` | Specific problem or exploration area under a project | Review required |
| `question` | Primary or decomposed subquestion driving discussion | Safe commit |
| `assumption` | Explicit, unverified hypothesis or working scenario premise | Safe commit |
| `evidence` | Observed facts, test measurements, datasheet data, cited documents | Safe commit |
| `decision` | Formal resolution addressing questions with rationale | Review required |
| `checkpoint` | Continuity or maturity milestone snapshot | Safe commit |

---

## 2. Standard Relations (Edges)

All edges are directed and strictly acyclic (DAG). Two semantic categories:

### Hierarchy (归属关系)
- `contains`: Topic -> Question (top-level topic questions)
- `subquestion`: Parent Question -> Child Question (supports arbitrary depth and multi-parent trees)

### Grounding & Dependency (依据/依赖关系)
- `grounds`: `evidence` or `assumption` -> `question` (evidence/premise this question investigates)
- `grounds`: `evidence` or `assumption` -> `decision` (evidence/premise justifying the decision)
- `depends_on`: `question` -> prerequisite `question` (marks source question as blocked until prerequisite is resolved)
- `decides`: `question` -> `decision` (marks that this decision resolves the question)

> [!IMPORTANT]
> **Strict DAG Invariant**: Adding an edge that creates a cycle (e.g. A -> B and B -> A, or A -> B -> C -> A)
> is strictly rejected by the State Manager with `CycleDetectedError`. When revisiting earlier ideas,
> use `SUPERSEDE` or create a new question version rather than pointing arrows backward in time.

---

## 3. Concrete Transaction Examples

### Example A: Decomposing a Question into Subquestions with Evidence & Assumption (Safe Commit)

When exploring "土耕还是水耕？", decompose it into subquestions, record known measurement evidence and an assumption, and link them:

```json
{
  "project_id": "project-farm",
  "rationale": "将种植方式拆解为维护时间与水源两个子问题，并关联现有实测资料与时间假设",
  "operations": [
    {
      "action": "CREATE",
      "kind": "question",
      "target_id": "q-sub-labor",
      "values": {
        "title": "维护时间够不够？",
        "topic_id": "topic-planting"
      }
    },
    {
      "action": "LINK",
      "kind": "question",
      "target_id": "q-main-planting",
      "values": {
        "source_id": "q-main-planting",
        "target_id": "q-sub-labor",
        "relation": "subquestion"
      }
    },
    {
      "action": "CREATE",
      "kind": "assumption",
      "target_id": "a-daily-labor",
      "values": {
        "title": "每天可维护一小时",
        "statement": "用户确认工作日每天早晨有约1小时可用于常规巡检和维护",
        "topic_id": "topic-planting"
      }
    },
    {
      "action": "LINK",
      "kind": "assumption",
      "target_id": "a-daily-labor",
      "values": {
        "source_id": "a-daily-labor",
        "target_id": "q-sub-labor",
        "relation": "grounds"
      }
    },
    {
      "action": "CREATE",
      "kind": "question",
      "target_id": "q-sub-water",
      "values": {
        "title": "水源供应够不够？",
        "topic_id": "topic-planting"
      }
    },
    {
      "action": "LINK",
      "kind": "question",
      "target_id": "q-main-planting",
      "values": {
        "source_id": "q-main-planting",
        "target_id": "q-sub-water",
        "relation": "subquestion"
      }
    },
    {
      "action": "CREATE",
      "kind": "evidence",
      "target_id": "e-water-measure",
      "values": {
        "title": "水源测量资料",
        "statement": "现场蓄水池静水测量，稳定出水流量为 5L/min，日均最大补给 400L",
        "source_type": "physical_measurement",
        "topic_id": "topic-planting"
      }
    },
    {
      "action": "LINK",
      "kind": "evidence",
      "target_id": "e-water-measure",
      "values": {
        "source_id": "e-water-measure",
        "target_id": "q-sub-water",
        "relation": "grounds"
      }
    }
  ]
}
```
*Flow*: Propose -> returns `review_required: false` -> immediately execute `brainstormer_commit_safe_transaction(proposal_id)`.

---

### Example B: Converging on a Decision (Requires Orchestrator Review)

When subquestions are sufficiently answered and user confirms the decision:

```json
{
  "project_id": "project-farm",
  "rationale": "基于维护时间与水源测量数据，第一阶段采用土耕方式",
  "operations": [
    {
      "action": "CREATE",
      "kind": "decision",
      "target_id": "d-soil-stage1",
      "values": {
        "title": "第一阶段采用土耕",
        "statement": "鉴于日维护时间仅1小时且水源流量有限，第一阶段采用土耕+滴灌方案",
        "topic_id": "topic-planting"
      }
    },
    {
      "action": "LINK",
      "kind": "question",
      "target_id": "q-sub-labor",
      "values": {
        "source_id": "q-sub-labor",
        "target_id": "d-soil-stage1",
        "relation": "decides"
      }
    },
    {
      "action": "LINK",
      "kind": "question",
      "target_id": "q-sub-water",
      "values": {
        "source_id": "q-sub-water",
        "target_id": "d-soil-stage1",
        "relation": "decides"
      }
    },
    {
      "action": "LINK",
      "kind": "evidence",
      "target_id": "e-water-measure",
      "values": {
        "source_id": "e-water-measure",
        "target_id": "d-soil-stage1",
        "relation": "grounds"
      }
    }
  ]
}
```
*Flow*: Propose -> returns `review_required: true` -> state what was proposed; do not say it is committed until Orchestrator or user approves.

---

## 4. Discussion Progression & Active Question

- Call `brainstormer_get_decision_map(project_id)` to view:
  * `progression.ready_questions`: questions whose prerequisite dependencies are all resolved.
  * `progression.blocked_questions`: questions waiting on prerequisite question resolutions.
  * `progression.recommended_next_question_id`: topological recommendation focusing on leaf subquestions.
- When shifting focus to a new question during dialogue, call `brainstormer_set_active_question(project_id, question_id)`.
