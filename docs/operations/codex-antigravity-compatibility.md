# Codex Antigravity compatibility audit

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
