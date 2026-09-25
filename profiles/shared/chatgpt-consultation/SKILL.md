---
name: chatgpt-consultation
description: Consult the user's configured ChatGPT Web account for bounded second opinions, search, and research through the UuMA bridge.
---

# ChatGPT consultations

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
Poll no faster than every 10 seconds. AWAITING_INPUT carries a clarification or research plan:
answer with chatgpt_continue only within the original user scope. Return scope expansion to the user.
PAUSED and NEEDS_REVIEW require recovery through the human account dashboard; never silently retry
under another account or mode. chatgpt_cancel cancels observation and attempts to stop generation.

Conversations are isolated by account, agent, project and thread. Continue with chatgpt_continue;
do not borrow another agent's conversation or request ID. The dashboard owns account rebindings.

Preserve source links and the conversation URL in your answer and provenance. ChatGPT answers are
external advice, not authoritative evidence or permission. Wisdom must verify cited sources through
its existing evidence workflow; any new claim remains a candidate. Existing approval, patch and
reversal boundaries remain in force. Website preferences are not guaranteed domain restrictions.
