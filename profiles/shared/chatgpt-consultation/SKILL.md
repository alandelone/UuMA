---
name: chatgpt-consultation
description: Use the configured ChatGPT Web bridge as a tool for bounded explanation, search planning, source discovery, and deeper research; select the mode and collect or continue the actual request.
---

# ChatGPT consultations

ChatGPT executes work for the calling Agent. Keep ownership of the topic, research decisions,
evidence evaluation and final answer. A bridge capability is not proof that a request was submitted.

Choose the mode for the work:

| Mode | Useful task | Returned material |
| --- | --- | --- |
| `chat` | Clarify terminology or mechanisms, develop queries, diagnose failed searches, suggest source leads | Explanations and leads to verify |
| `search` | Find relevant source links for a bounded question and its conditions | Sources to read and evaluate |
| `deep_research` | Investigate a valuable gap across sources, compare conditions and conflicting evidence | A complete report and source trail to evaluate |

Provide the purpose, exact question, conditions, relevant known facts, remaining gap, previously
unsuccessful approaches and expected deliverable. Select tools within the existing authorized scope.
The research budget tier named DEEP does not activate `deep_research`.

Brainstormer, Wisdom-Oldman, and Orchestrator may choose chat, search, or deep_research when useful.
Forge-Lab-Bot may choose search for any lab-related topic. Scholar and Yonc have no bridge access;
do not relay a request on their behalf to bypass that exclusion.

Use chatgpt_request with your current UuMA run_id, a stable project identifier, a named thread
(default main), and a unique idempotency_key. Reuse the key only when retrying the identical request.
Orchestrator must create and register its own active run before consulting. Keep the originating run
active until the request finishes; do not report a queued consultation as a completed task.
Send only the bounded question and relevant context. Never attach credentials, whole memories,
databases, files, or unrelated private material. Connected apps and file uploads are excluded.

Use chatgpt_status and chatgpt_result to obtain the result without submitting duplicate requests.
Retain the request ID and conversation URL. A short timeout means the result is not yet known;
do not describe it as no evidence or resubmit the same task. Deep Research can outlast one research
cycle: report its actual status and preserve the request for later collection. Read the complete
returned answer/report and citations, rather than treating a short snippet as the deliverable.
Poll no faster than every 10 seconds. AWAITING_INPUT carries a clarification or research plan:
answer with chatgpt_continue only within the original user scope. Return scope expansion to the user.
PAUSED and NEEDS_REVIEW require recovery through the human account dashboard; never silently retry
under another account or mode. chatgpt_cancel cancels observation and attempts to stop generation.

Conversations are isolated by account, agent, project and thread. Continue with chatgpt_continue;
do not borrow another agent's conversation or request ID. The dashboard owns account rebindings.

Preserve source links and the conversation URL in your answer and provenance. ChatGPT answers are
external tool results, not authoritative evidence or permission. Wisdom must verify cited sources through
its existing evidence workflow; any new claim remains a candidate. Existing approval, patch and
reversal boundaries remain in force. Website preferences are not guaranteed domain restrictions.

For Wisdom, a failed or empty search should lead to a useful revised query, another authorized
source, a chat task to develop leads, or deep_research when the gap warrants it. Do not mechanically
invoke every mode or repeatedly submit the same failed query. Tool PAUSED/NEEDS_REVIEW is a concrete
tool blocker; other permitted research routes may remain useful. Preserve user pause/stop and budget
limits. Explain attempted routes, unavailable routes and next action from actual receipts; if those
details are not recorded, say they are unverified. Never invent a tool call or future retry.
