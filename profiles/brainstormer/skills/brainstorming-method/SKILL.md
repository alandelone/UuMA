---
name: brainstorming-method
description: Explore ambiguous or consequential problems, decompose into subquestions, ground with evidence, and converge on structured decisions via the Decision Map DAG.
---

# Brainstorming Method

Use for substantial ideation, planning, architecture choices, or decisions with meaningful uncertainty.
Scale the method to the user's question; a short answer does not need every step.

## The Decision Map Progression Loop

```text
Project / Topic
      v
Primary Question
      v
Decompose -> Subquestions (leaf nodes)
      v
Ground -> Evidence (facts) + Assumptions (hypotheses)
      v
Resolve -> Tackle ready leaf subquestions in sequence
      v
Converge -> Decision grounded on answered questions & evidence
```

### 1. Interpret & Place
- Clarify the user's real objective, active Project, and Topic.
- Check existing discussion state with `brainstormer_get_decision_map(project_id)`.

### 2. Decompose into Subquestions
- Break complex or multi-faceted problems into concrete subquestions.
- Connect subquestions to the parent question using `subquestion` relations (hierarchy).
- Identify dependencies: if Subquestion B requires Subquestion A's outcome first, establish `depends_on` (Subquestion B -> Subquestion A).

### 3. Ground with Evidence & Assumptions
- Distinguish verified facts from unverified working premises:
  * Record empirical data, measurements, quotes, or datasheet facts as `evidence`.
  * Record speculative scenarios or unverified user intentions as `assumption`.
- Link them to the relevant question using `grounds`.
- A user correction immediately supersedes an earlier premise. State the corrected premise briefly and recompute dependent conclusions.

### 4. Drive Progression (Active Question Focus)
- Use `brainstormer_get_decision_map` to check `progression.recommended_next_question_id`.
- Prioritize unblocked leaf subquestions (`ready_questions`) before attempting to decide composite parent questions.
- When shifting dialogue to a specific question, synchronize state via `brainstormer_set_active_question(project_id, question_id)`.

### 5. Explore Alternatives & Challenge
- Explore plausible alternatives for the active subquestion, challenge leading ideas, and analyze tradeoffs and failure modes.
- For numerical planning, use `quantitative-decision-model` and verify arithmetic with `brainstormer_calculate_capacity`.

### 6. Converge & Propose State
- When a subquestion or overall topic is settled, synthesize a `decision` that explicitly links to the resolved questions (`decides`) and supporting evidence (`grounds`).
- Follow `discussion-state` rules:
  * Safe commit assumptions, questions, evidence, checkpoints, and grounding links via `brainstormer_commit_safe_transaction`.
  * Submit decisions, project/topic structures, and supersessions for Orchestrator review.
- Strict DAG rule: never create circular links. If ideas change, supersede old objects rather than creating directed cycles.

### 7. Form Artifact
- Once the critical questions are answered and decisions are recorded, transition to PRDs, architecture docs, or SOPs (see `artifact-readiness`).

Show the user the reasoning that helps them decide. Do not claim a tool call, saved state, approval,
or completed artifact unless it actually happened.
