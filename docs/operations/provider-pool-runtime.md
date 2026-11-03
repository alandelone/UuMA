# Server Antigravity account-pool runtime

## Shared ownership

Brainstormer, Yonc, Honc, Wisdom and Forge use the server's shared Antigravity
OAuth account pool. As checked on 2026-10-22, the pool contains three enabled
accounts with saved authorization and local `READY` status. This is three accounts
shared by five agents. `READY` is a local readiness result, not a new upstream
authentication or inference result.

Pool state and credentials remain under
`~/.config/uuma/provider-pool/antigravity`. Do not recreate the pool or request new
Google authorization to repair a Python import failure.

## Incident and correction

During gateway cutover, the generated `pilot/gateway.env` replaced `PYTHONPATH`
with the Hermes engine and UuMA source directories. It omitted the independently
pinned account-pool runtime directory. The provider's token resolver then failed
to import `uuma_provider_pool`. Hermes subsequently fell back to a standard
OpenAI client, which rejected the provider-specific `command` argument.

The repair prepends the existing provider release's `runtime` directory while
preserving the engine and UuMA source entries. It neither replaces account files
nor changes model selection. The generic Hermes SDK fallback itself was not
modified.

The production gateway must retain all three dependencies in `PYTHONPATH`:

1. Account-pool release `runtime` directory, from the same release as `agy-pool`.
2. Pinned Hermes engine source.
3. Pinned UuMA adapter source `src` directory.

When updating a component, preserve the other entries. The pool command's parent
release directory determines its matching runtime directory; do not select a
different release by taking the newest directory name.

## Startup guard

`scripts/check-server-provider-runtime.py` runs using the gateway's interpreter
and environment. It checks the imported pool module's exact release, confirms
saved pool authorization is available, and constructs the real Antigravity
plugin client without requesting an inference. A missing dependency or wrong
client prevents startup.

Installed guard:

- Unit: `uuma-hermes-pilot.service`.
- Drop-in: `~/.config/systemd/user/uuma-hermes-pilot.service.d/20-provider-runtime-preflight.conf`.
- Guard release: `~/.local/share/uuma/provider-runtime-checks/09be51e4e6e1671cee63625f40ba2bdc38fa06aa1c300eabb687e8e4d3a75106/`.
- Provider release: `~/.local/share/uuma/provider-pool-releases/a73461932e6ced760e53ead9bdb8da020c20f130e42158968b8042ac1997bbe9/`.

Keep this `ExecStartPre` drop-in when replacing the main unit. Publish a new
content-addressed guard if its source changes. The guard checks initialization;
it does not prove a model response or all agent tools succeed.

## Restart and evidence

Pause intake for all five agents using the existing deployment owner, wait for
zero active gateway agents, and then restart their shared gateway. Confirm the
preflight exits successfully, the actual process has the expected `PYTHONPATH`,
and all five Telegram adapters reconnect. A single adapter may recover after an
initial network timeout; record both the timeout and recovery.

On 2026-10-22, preflight succeeded with `AntigravityClient`, three accounts and
three local `READY` states. All five adapters reconnected. Neither reported pool
error recurred after restart. No new inference, authorization flow or failed
task replay was initiated by this repair. A fresh user message is still needed
to observe a successful model response through Telegram.

Server evidence and private configuration backup:
`~/.local/share/uuma/provider-runtime-repair-20261022/`.
Local sanitized evidence: `.uuma-local/provider-runtime-repair-20261022/`.
Before restoring `gateway-env.before`, pause intake and reconcile any subsequent
deployment changes. That backup contains the broken import path; restoring it
without correcting the runtime entry will intentionally fail the startup guard.
Repair the path or provider release before reopening intake. Never roll back
account authorization or domain databases for this incident.
