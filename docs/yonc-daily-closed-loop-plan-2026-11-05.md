# Yonc Daily: daily action and closed-loop view

Recorded: 2026-11-05, Asia/Kuala_Lumpur.
Status: implemented in `yonc-graph` and published to formal Yonc `/daily` with explicit user authorization on 2026-11-07. See `yonc-daily-release-preview-2026-11-07.md` for the scoped release, backup and verification receipt. This record does not approve or move the repository mission gate.

## Purpose and entry

Add a dedicated `/daily` route under the existing Yonc website. It is a detailed daily action workspace containing **only tasks arranged for today and previously arranged but unfinished tasks**. The user explicitly narrowed this scope with “only”; do not include an unscheduled-task pool on Daily. The closed loop is: choose a task, focus and act, capture context and obstacles, return and review, then mark it done.

The cards reference existing **Project Graph L4 Actions**, retaining their graph identity across days. Project membership, module ancestry and task classifications come from that graph. An L4 Action enters Daily automatically according to its **own planned date**, and remains in subsequent Daily views while unfinished. Mapping that planned date to the current field and handling date ranges remain implementation/design details.

## Task workspace

- Provide an icon button at the top right to switch grouping views. The user corrected an initial top-left description to top right. Clicking opens a small selection block/popover.
- First grouping: **By type**, using Yonc's existing Task type configuration and task tags; do not create a new taxonomy.
- Second grouping: **By project**, with modules nested inside each project. Exactly two grouping views, not a third By module view.
- Use visible divider lines between groups.
- Present tasks as cards/blocks in a list, drawing on the existing List view's visual rules. The L4 card is the main title. The latest confirmed tree treatment uses plain text, replacing the earlier underlined-subtitle interpretation.
- Clicking the card focuses it and makes it glow, like the existing Graph selection treatment. **Only one task may be focused at a time.** The user's latest clarification supersedes the earlier concurrent-focus answer. Switching to another card ends the previous focus interval and begins the new one. Clicking the focused card again pauses it and removes the glow. Another click resumes it, preserving separate focus intervals.
- The task completion checkbox sits at the far right end of the card. A tick directly completes the corresponding **canonical Project Graph L4 Action** and makes it gray. Support undo.
- Editable notes extend below the card as an indented tree: a vertical connector leaves the card's lower-left edge, turns into the next text row, and continues through deeper rows. Higher-level connectors are thicker; deeper ones become thinner. The latest spoken correction asks for non-curved connectors. Exact appearance should be validated in a small visual draft.
- Only the first indentation level directly under the card has to-do checkboxes before its text. Deeper levels contain connector lines and editable detail text. Connector lines replace ordinary bullet dots. Text has no underline. These rows capture issues, solution approaches, checks and additional detail.
- First-level checklist items are independent of overall task completion. Checking every item leaves the task's overall completion under the user's separate far-right checkbox control.
- Store the tree in the **Project Graph database under its L4 Action**. Notes and checklist content persist across days with the original task. The precise tree storage representation still needs design.

The user selected **stepped branches** and accepted the text size. Their final correction explicitly retains normal horizontal width and font size: compactness means **reducing vertical spacing between rows**, allowing more text on one page. The earlier 560px-width interpretation is superseded.

## Activity modes and return

Provide activity-mode controls on the right side; precise placement remains open. Confirmed initial modes are **Rest**, **Toilet**, and **LIJ (Lost in jungle)**. Interruption/interaction was mentioned as context but was not explicitly confirmed as a fourth initial mode.

Selecting a mode pauses the focused task and switches actual activity recording to that mode. When returning, the user clicks a task again to resume working on it; no automatic task resumption. Only the newly clicked task resumes. Whether paused cards retain a distinct selection treatment remains open.

## Focus and Copycat context

When the user focuses a task, associate the focus interval with available Copycat activity data: applications, windows and actions used while doing the task. This should support returning to the task with a record of the working context.

Original user wording, preserved as a quotation:

> Copycat也会也会用到copycat的资料啦，就是说到底现在我做着这个task的时候我是用什么东西啦。用什么window啊，就是trace我的motion，trace我的action啦。

After the original wording and automatic-association proposal were shown again, the user agreed and requested only a more compact visual treatment. The working design uses **automatic time-based association of available Copycat observations during task focus**. Actual capability/data-contract mapping, capture controls and correction semantics still need to be specified.

The final capture decision is explicit: **Daily uses Copycat's existing capture records and leaves capture start/stop under Copycat's own switch**. Daily never starts capture when focusing a task. The implementation reads events within an interval, rechecks timestamps, and reports unavailable/partial results when appropriate. Observation retrieval is bounded to 500 events. Observed computer activity and an explicitly selected task remain distinguishable; activity alone is not proof that a task is complete.

## Vertical timeline / tracer

Place the timeline **side by side: task list on the left, Activity on the right**, independently scrollable. This is the user's final layout decision. Time flows from top to bottom with a live **red current-time line**, like a music-sequencer playhead. Activity/focus changes produce colored time blocks. Only one task or activity mode records at a time. Optional planned times occupy a separate planned lane alongside actual activity.

If the user forgets to switch an activity or return to a task, allow **manual dragging of time-slot boundaries to correct recorded times**. A shared boundary updates both adjoining blocks: changing Toilet's end to 14:20 also changes the following task's start to 14:20. Moving whole blocks, inserting missing intervals and correction history still need design decisions. Correcting actual activity should be distinguished from rescheduling project plans.

The tracer captures three parallel dimensions:

1. **Activity — what I am doing.** Task focus transitions are recorded when the user clicks to focus. Include everyday non-task activities such as toilet breaks and other personal activities.
2. **Location — where I am.** Examples include traveling, in a car or arriving somewhere. Recording is optional. Select from options that the user can add or adjust in Configuration settings.
3. **Body condition — how my body is doing.** Recording is optional. Select from options that the user can add or adjust in Configuration settings.

Reuse the Configuration settings concept. The user's recollection of an existing settings page has not yet been mapped to exact existing location/body-condition configuration fields. Whether location also accepts an immediate free-text entry remains to be clarified from the spoken wording.

The timeline should allow these dimensions to coexist at the same time. A location or body-condition entry should not implicitly replace the activity record. This coexistence is a proposed interpretation of the user's three-dimension tracer, to validate during design.

## Example journey

Open `/daily` → see today's and carried-over tasks → choose grouping → focus a task → task highlights and tracer records the start → work using relevant apps/windows → add notes or nested troubleshooting bullets when blocked → record breaks, travel/location or body condition as needed → return to review → tick done → task becomes gray and the timeline retains the day's trace.

## Existing-system reading, 2026-11-05

Read the Yonc design index, core architecture, Graph Project System specification and current List view source in the sibling `yonc_agent` repository. These are local-source observations, not a fresh production audit.

- The Graph hierarchy is L1 Goal → L2 Deliverable/Module → L3 Work Package → L4 Action. The specification allows atomic refinements inside an Action without creating additional graph nodes, which fits Daily's nested notes/checklist intent.
- Current List view resolves task types from existing tags and Yonc configuration; its fallback options include Coding, Research, Reading, DeepWriting, Thinking, Search, HandyWork, Planning, Structuring, Admin and Repetitive. Daily should reuse current configured values rather than freeze this fallback list.
- Existing Project Timeline scheduling is reserved for L1–L3 modules/jobs. L4 Actions are execution units in Canvas/Focus/execution views. List view separately detects temporal context through node dates/tags/text. Therefore “has timeline context,” “scheduled for today,” and “actual Daily activity time” must be distinguished before choosing an eligibility rule. Do not assume the user requested changing Project Timeline's L1–L3 rule.
- CodeGraph was used first; one call reported a busy queue. The sibling index flagged ListView/App/types as changed on disk, so current ListView and relevant current source locations were inspected directly. No UI code edited.

## Implemented interaction defaults and remaining acceptance

Development uses the actual `C:/Users/Alandelone/CodeSpace_Local/yonc-graph` repository; the earlier `yonc_agent` reading was design background only. A separate candidate starts from the production source snapshot and applies Daily changes, excluding unrelated local List work.

- Date precedence: explicit L4 `daily_planned_date`, then `planned_start`, then imported `timeliner_settle_date`. Explicit null clears the override. Malaysia UTC+8 determines the day. Optional start/end times must be ordered within that day.
- The outline is stored in `GraphNode.tags.daily_outline` and uses existing reversible Graph updates. Enter creates a sibling; Tab/Shift-Tab changes nesting; explicit Save or Ctrl/Cmd+Enter persists it. Browser-local unsaved drafts survive reload and are retained on conflict.
- Completing a task updates canonical L4 status, stops active focus, and supports undo. First-level checklists remain independent. Completion-day history uses canonical status events.
- Runtime changes use revision checks. Three additive tables store runtime, intervals and append-only changes. Shared-boundary corrections update both adjacent intervals and retain correction history; they do not alter planned dates.
- Location and body condition are optional independent context dimensions. Their option lists are editable under Configuration / Daily. Selecting either does not replace task activity.
- Pausing removes the focus glow. Rest, Toilet and LIJ require manually clicking a task to return.
- Source and synthetic-data browser checks cover focus/pause/resume, completion/undo, outline persistence, grouping, planned times, context and the parallel layout. Final candidate acceptance also checks boundary dragging and settings persistence.

Rollout completed after explicit candidate approval: consistent backup, additive schema, Graph-only service restart and verification of the same database owner. Copycat's capture switch remains independent. The mission gate remains pending review.

## Historical design checklist (superseded where resolved above)

- Map the confirmed L4-own-planned-date inclusion rule to exact date fields, ranges and rescheduling behavior.
- Exact project/module ancestry and handling unclassified/multi-parent tasks while retaining canonical IDs.
- Switching browser/device and crossing midnight. Single-task focus, repeated-click pause/resume, mode pause/manual return, and coupled adjoining boundaries are confirmed.
- Tree editing: compact-preview feedback, expand/collapse, add/indent/reorder/delete and precise storage representation. Stepped branches, first-level-only checkboxes, independent checklist completion, plain text and persistence under L4 are confirmed.
- Planned versus actual rendering, color mapping, timeline position/zoom/navigation, and drag correction semantics.
- Map automatic time-based Copycat association, including unavailable capture, corrections, and capture scope.
- Location/body-condition timing, free-text entry, single/multiple selection, persistence and simultaneous entries. Optional input and configurable option lists are confirmed.
- Completed-task visibility and history retention. Canonical Graph L4 completion and undo are confirmed.

Latest confirmed clarification: only one focused task, entering a mode pauses task focus and returning requires clicking a task, and shared time-block boundaries move together. The earlier multiple-focus answer is superseded.

Subsequent confirmed decisions are L4-own-planned-date admission with unfinished carry-over, canonical Graph completion with undo, independent sub-checklists, cross-day tree persistence in the Graph database, click-again pause, plain stepped-branch appearance, optional configurable location/body-condition lists and automatic association of available Copycat observations during focus. The more compact preview and remaining detailed interaction rules remain under discussion.

These historical questions are not additional user requirements. The implementation defaults above resolve the current development scope; the next step is candidate acceptance and a separate publication decision.
