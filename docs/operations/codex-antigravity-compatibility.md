# Codex Antigravity compatibility audit

## Independent provider authentication (2026-11-11)

The original custom provider used `requires_openai_auth=true` and the user's
ChatGPT access token for loopback authentication. Antigravity inference itself
did not consume OpenAI quota, but this unnecessarily retained the OpenAI login
requirement at the client/provider boundary.

`manage.py independent-auth` now migrates the installed bounded provider block to
[Codex command-backed provider authentication](https://learn.chatgpt.com/docs/config-file/config-advanced)
with `local_auth.py` and a protected, ignored local bearer credential. The helper
does not use an OpenAI token. Windows ACLs allow only the current user and SYSTEM.
OpenAI login state and unrelated configuration are preserved. The gateway
continues accepting old ChatGPT-authenticated sessions while the desktop reloads.
For GPT requests, it substitutes the normal local OpenAI token and preserves the
official backend's quota response; the independent credential never goes there.

Fourteen focused tests passed, including rejecting missing/incorrect/non-loopback
authentication, accepting Antigravity without an OpenAI auth file, and a mocked
official response proving token separation and unchanged HTTP 429 quota error.
The first quota fixture used an already-consumed response body and failed its
exact body assertion; the fixture now uses an unread byte stream, and the same
status/body assertions pass without weakening them. Two pre-existing lint
findings in the unrelated official streaming exception handler remain separate.

A native isolated Codex home contained no OpenAI auth file before or after the
check, no OpenAI API-key environment variable, and a local credential helper.
`account/read` returned `account=null, requiresOpenaiAuth=false`; an ephemeral
native `hi` completed successfully with a real Antigravity greeting. The combined
check took 17.12 seconds. These establish the independent model/auth path, rather
than a guarantee about every desktop UI state. The actual user configuration
was then migrated after verifying the candidate, preserving its selected model,
all unrelated values and the exact OpenAI login file bytes.

The desktop must be fully restarted once to load the new provider authentication.
Select Antigravity in a chat already using the gateway (or a provider-aware fork).
Exhausted-plan Enter/button behavior is not visually verified; do not claim that
the app's cached quota UI has been tested or patched. The app-server can now run
the provider without OpenAI credentials. No OpenAI quota is extended or bypassed.
Some hosted/account features still require their usual login and entitlement.

Private evidence: `independent-auth-focused-checks-20261111.json`,
`independent-auth-verification-20261111.json`,
`independent-auth-candidate-installation.json` and
`independent-auth-installation.json`. The latter references the actual user-config
backup. The independent token is not included in these receipts or in Git.

## Desktop reference context without a call ID (2026-11-11)

An actual new desktop chat, `Respond to greeting`, failed before inference with
HTTP 400 `"'call_id'"`. Its history included named `function_call_output` items
for `codex_apps_open_page` and `codex_apps_selected_page_part_1_of_1`. These carry
client-provided reference context, not results of model-requested calls, and have
an item ID but no `call_id`. The adapter incorrectly required a call ID for them.

Named outputs without a call ID now remain in order as explicitly untrusted user
reference context, preserving their name, namespace and textual output. No
assistant call or result pairing is fabricated. Normal paired outputs retain
their call IDs; missing IDs on actual calls, unidentified outputs and invalid IDs
still reject with explicit errors. Eleven focused protocol checks cover both
this input shape and the earlier additional-tools repair.

The current-path minimal request completed in 9.84 seconds. A separate ephemeral
native Codex `hi`, at the saved High effort with core tools, completed in 24.59
seconds with no tool execution (55,292 upstream input tokens). Neither reproduces
the complete desktop tool configuration. Existing long task failures and the GPT
usage-limit errors in the troubleshooting chat are separate evidence, not proof
that a greeting is still pending. Slow response time remains a limitation.

Private receipts use the `current-path-diagnostic-20261111`,
`native-greeting-20261111`, `context-output-local-replay-20261111` and
`context-output-release-20261111` prefixes in the bridge state directory.
The original eight-item desktop history reproduces the failure against a source
snapshot whose hash matches the pre-fix running process, and passes translation
after the fix. Gateway PID 80492 loaded source hash
`714d7a273c10f24e3b23123dfe87e536dac0d58ccb03579726fd54781d72fa93`.
The subsequent real-provider probe with both unpaired context items returned
HTTP 200 and a greeting in 8.31 seconds; its receipt is
`live-context-output-20261111-result.json`. That probe used Low effort, no tools
and synthetic null-page values. The user's full desktop retry remains separate.

## Additional tool definitions (2026-11-06)

Codex can place `additional_tools` items in the replayed input, as documented in
[OpenAI's tool-search guide](https://developers.openai.com/api/docs/guides/tools-tool-search).
The old bridge rejected these items before inference with HTTP 400
`Unsupported Antigravity input item: additional_tools`.

The adapter now merges their function/custom definitions into the tools offered
to the current provider call, preserves namespace and input grammar, and places
an introduction marker at the same point in the translated conversation. This
adapts the declaration to the provider's static Chat Completions tool array;
it does not implement hosted tool search. Replayed identical definitions are
deduplicated; conflicting aliases/schemas and unsupported tool types still fail.
Only a developer-role declaration (or the legacy omitted role) is accepted.

Six focused, isolated checks in `tests/test_codex_antigravity_input_tools.py`
cover declarations, history and forced-tool mapping, duplicate/conflict handling,
invalid input and HTTP/SSE route acceptance. These checks do not call a model.
The isolated gateway release and separate live-provider result are recorded in
`additional-tools-release-20261106.json` and
`live-additional-tools-20261106-result.json` in the private state directory.
The live check passed in 26.91 seconds across two Gemini requests: an injected
namespaced function was requested, the local fixture reader returned its actual
nonce, and a subsequent request preserving the declaration/history returned that
exact nonce. This confirms the repaired input path and result replay, not all
desktop network or UI behavior. The isolated gateway was restarted at an idle
boundary; the shared Hermes service was not restarted.

The existing process had been launched with the same Python installation's
`python.exe`, whereas management allowed only `pythonw.exe`. Management now accepts
both executable names while retaining listening-service, process and source checks.

The source already contained two lint findings in the separate OpenAI forwarding
exception handler (`S110` and `BLE001`); this change preserves that unrelated
behavior and introduces no new lint findings.

Observed on 2026-11-03 using the installed Codex 0.166 runtime and the existing
Hermes `antigravity-oauth` provider. This is a custom Responses bridge, with
client-side Codex tools. Full equivalence to the OpenAI provider is not established.

## Failures and corrections

1. An old conversation retained `model_provider=openai`. Changing its model name
   sent an Antigravity name to the OpenAI backend and was rejected before reaching
   this bridge. A provider-aware fork preserves history on the new connection.
2. Codex offered optional hosted `web_search` even though the catalog did not
   advertise search. The adapter previously rejected the whole request. It now
   omits that unavailable offer, tells the model explicitly, and rejects forced
   hosted search rather than inventing a result.
3. Custom tools require their input grammar and correct namespace mapping.
   The bridge now preserves the grammar, supports explicit custom-tool selection,
   and resolves exact canonical names only against advertised tools.
4. Windows virtual-environment launchers can have a different PID from the
   listening Python process. Management validates the actual owned gateway process
   before stopping it. Recovery also has a standalone PowerShell entry point.
5. SSH disconnect previously did not explicitly close the remote model client.
   JSON-line requests now keep a control connection open; EOF closes that client.
6. A combined native audit exposed `JSONDecodeError` at the adapter boundary.
   Freeform custom input was being treated as a mandatory JSON wrapper, and
   function arguments were pre-parsed before Codex could return a normal tool
   validation error. Native freeform input is now preserved, recognized wrappers
   are unwrapped, and function arguments reach Codex unchanged. Grammar validation,
   permissions and execution remain with the client. An isolated SSE contract
   confirms both paths complete without a transport abort.

## Capability and evidence

| Capability | Current evidence and limit |
| --- | --- |
| Desktop model picker and text reply | User's `Respond to greeting` retry completed. Gemini Flash only. |
| Original GPT route | Existing model names forward to the fixed official backend. User previously confirmed GPT sends successfully; it was not re-probed with paid inference during this audit. |
| Shell and tool-result replay | Native ephemeral Codex read the disposable input file, received its real content, and continued through subsequent tool outputs. |
| `apply_patch` | The corrected combined native check patched the disposable output file, read it back through a shell tool, and independently matched its exact content from the outer reader. An earlier standalone outer read hit a sandbox ACL denial; that failure is preserved. |
| MCP | A real local read-only MCP fixture returned a file nonce, and native Codex returned that exact nonce. Only the fixture had ephemeral per-tool approval. Real connected services were not exercised. |
| Custom grammar, namespaces and forced choice | Adapter contract checks pass. Invalid or unadvertised tool types/names fail explicitly. The native patch round trip supplies separate integration evidence. |
| Cancellation | An isolated fake-provider SSH probe observed EOF close the client and exit without inference. Actual desktop Stop-button behavior and upstream account lease release remain unverified. |
| Usage and timings | Upstream token counts are emitted in Responses usage; gateway records actual model, timings and tool count. A new desktop performance panel has not been implemented or visually verified. |
| Conversation history | Provider-aware fork was created without rewriting historical receipts. Tool-result continuation works; very long dialogue and automatic compaction are unverified. |
| Images and audio | Not supported by this text bridge. Image input is rejected explicitly. |
| Hosted web search | Unavailable. An independently offered client retrieval tool can be used through the standard tool protocol; no built-in search equivalence is claimed. |
| Server compaction / `previous_response_id` | Unsupported and rejected. Do not assume long-session parity or automatic recovery. |
| Other model entries and effort levels | Names were observed in the server catalog. Claude, GPT-OSS and each effort setting have not passed this Gemini integration audit. |
| Skills, plugins and permissions | Catalog includes their instructions; normal client permissions remain enforced. This does not verify every skill, plugin or external action. |
| Multi-agent | Disabled in the custom catalog. |

## Performance and candidate isolation

A small greeting reported roughly 55,000 upstream input tokens. A subsequent
native MCP request offered 143 client tools, with roughly 302,000 serialized
payload characters and 54,600 input tokens. Each request starts an isolated
SSH worker and provider call. These are observations, not a latency guarantee;
provider/account contention and model reasoning also affect response time.

A private `code_mode_only` catalog reduces the offered top-level tool count.
Its first run failed with an unknown tool name. The second bounded check completed
shell, patch, MCP and independent exact output assertions after the name-mapping
correction. It took ten model requests, repeatedly reading an unchanged file before
finally applying the patch: 437,273 cumulative input tokens and 2,494 output tokens.
Correctness passed, but the extra round trips do not justify enabling this
performance candidate. The installed catalog remains unchanged. The standard
catalog's first combined recheck exposed the parameter-format failure documented
above. The corrected installed-catalog check passed: shell input read, patch,
read-only MCP, shell output read, both exact nonces in the final reply, and an
independent exact output assertion. It exited zero and reported 220,871 cumulative
input tokens and 576 output tokens. This verifies the bounded tool round trip,
not every model, service or desktop interaction.

## Local evidence and recovery

Private receipts are in `.uuma-local/codex-antigravity-ui-20261102/`:

- `first-successful-ui-reply-20261103.json`: actual desktop completion.
- `native-tool-audit.stdout.jsonl`: native shell/patch execution and readback.
- `native-mcp-audit-result.json`: exact MCP nonce round trip.
- `contract-audit-result.json`: adapter contracts and fake-provider EOF lifecycle.
- `native-codemode-audit-result.json` and the `native-codemode-audit-v2*` files:
  isolated optimization attempts, with no installed-catalog change.
- `native-standard-final*`: preserved parameter-format failure in the combined
  standard-catalog audit; `native-standard-v2*` is the corrected bounded recheck.
- `tool-name-fix-release.json`: isolated worker release and previous-settings backup.
- `freeform-fix-release.json`: current worker and gateway hashes and settings backup.
- `final-release-verification.json`: running gateway/source and worker/settings
  hash agreement and confirmation that the reduced-tool catalog is not installed.
- `events.jsonl`, `routing.jsonl`: sanitized per-request diagnostics; no prompts,
  tool arguments, tool results or authentication tokens.

The Antigravity project fork retains an obsolete saved C: workspace path. Select
the existing `Z:\Hardware-Lab-Workspace` through the desktop project UI before
project work. Do not recreate the removed workstation workspace or bypass folder
access by changing session databases.

The Desktop shortcut **Restore Codex OpenAI** invokes
`integrations/codex_antigravity/restore-openai.ps1` independently of Codex, Python
and the gateway. It restores routing while retaining chats, credentials and
unrelated settings. Restart the app afterwards. Its preview passed; an actual
routing restore has not been executed because the integration remains in use.

This work does not restart shared Hermes, alter specialist agents or production
databases, deploy a Scholar release, or approve the repository verification gate.
