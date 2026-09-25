# ChatGPT Web Bridge

The bridge gives selected UuMA identities a bounded consultation tool backed by the user's signed-in
ChatGPT Web account. ChatGPT is an external adviser; it is not an Agent, approval authority, or
source of accepted knowledge.

## Access

| Identity | Modes |
| --- | --- |
| Orchestrator | chat, search, deep research when verified on the account |
| Brainstormer | chat, search, deep research when verified on the account |
| Wisdom-Oldman | chat, search, deep research when verified on the account |
| Forge-Lab-Bot | search for lab-related questions |
| Scholar, Yonc | none |

The MCP client derives identity from each Hermes profile. The service repeats the permission check
and requires a current UuMA Run owned by that identity. A request cannot select another agent's
account or conversation. These are policy ceilings: an account can only use capabilities found by
its most recent verification and any capability explicitly confirmed by the user. The current
`main` account is ready for chat, search, and deep research.

## Runtime

The loopback service owns a durable queue in `uuma.db` and a human dashboard on port 8787. An
account can use either its isolated Playwright browser or the UuMA Chrome extension in an existing
Chrome profile. Isolated browser profiles live under
`%LOCALAPPDATA%\UuMA\chatgpt-bridge\profiles`; the extension uses the already signed-in Chrome
session without reading or copying its cookies. UuMA never asks for or stores the account password.
Login, MFA, challenges, identity mismatches, capability loss, and uncertain submissions pause the
queue for human review.

Every account is serialized. Conversation identity is `(account, agent, project, thread)`. Requests
carry idempotency keys and retain an append-only state history. A crash before submission returns the
request to the queue. A crash while submitting marks it `NEEDS_REVIEW`, so recovery never blindly
duplicates a prompt.

Search and research results must retain source links. Wisdom-Oldman must independently ingest and
verify relevant sources before forming a candidate claim. Existing candidate, review, patch, and
reversal boundaries remain unchanged.

Connected apps, uploads, image generation, private ChatGPT endpoints, copied browser credentials,
automatic account failover, and use by Scholar or Yonc are excluded.

## Deployment

```powershell
.\scripts\install-chatgpt-bridge.ps1 -StartNow
```

Open **ChatGPT Bridge** from the Windows Start menu. Add the `main` account alias, expected email,
and exact workspace label. Each account can select a normal Chrome profile for human or
extension-controlled use; this opens that profile without reading or copying its cookies. Install
the unpacked extension shown by the dashboard, select the profile, and press the account's
**Connect** button. The button opens ChatGPT in that signed-in profile, pairs the extension, and
verifies the visible account and workspace. Leave the selector on **Dedicated UuMA browser** to use
the isolated Playwright transport instead. UuMA does not type, read, or store passwords, email
codes, OTPs, or MFA. Deep Research can be recorded with **Confirm Deep Research access** after the
user verifies that the selected account has it. Extension-based Deep Research uses ChatGPT's
`/Deepresearch` composer command so it does not depend on the changing internal markup of the `+`
tools menu.

The installer backs up `uuma.db`, every affected Hermes configuration, and any pre-existing managed
skill before applying additive tables and profile changes. It installs a limited-user on-demand
task with no logon trigger, repeating watchdog, or automatic failure restart. Installation leaves
it stopped unless `-StartNow` is supplied. The first bridge tool call starts the task and waits up
to 30 seconds for it to become ready. For an account routed through an existing Chrome profile, the
same call opens a short-lived authenticated dashboard URL in that profile so the extension wakes
and reconnects before the queued consultation runs. The Start menu shortcut starts the service and
opens the dashboard for manual administration.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-chatgpt-bridge.ps1 -Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-chatgpt-bridge.ps1 -Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-chatgpt-bridge.ps1 -Stop
# Convert an existing deployment without redeploying Hermes or installing dependencies:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\manage-chatgpt-bridge.ps1 -Action migrate
```

Migration backs up the old task definitions, removes the watchdog and logon trigger, removes
automatic failure retries, updates the shortcut, and leaves the service stopped with a trigger-free
manual task ready for lazy start. Stop terminates only the configured bridge processes. With no
trigger or retry policy, it remains stopped until an agent calls a bridge tool, the operator selects
Start, or the dashboard shortcut is opened. Closing the dashboard does not stop the service: use
Stop when finished.

On-demand operation suits occasional consultation. An authorized agent tool call starts the bridge
when needed, and the service stays running through the consultation. Stop is a process termination,
not a graceful queue drain: wait for active work to complete first. History and browser profiles
remain intact; an interrupted submission may need human review on the next start. Other UuMA
services and their schedules are independent.

To disable the service and restore the affected profile files while preserving consultation history
and browser profiles:

```powershell
.\scripts\uninstall-chatgpt-bridge.ps1
```
