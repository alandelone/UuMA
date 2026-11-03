# Antigravity in the Codex desktop model picker

This pilot adds a loopback Responses gateway and a merged Codex model catalog.
Existing OpenAI model names proxy to the official ChatGPT Codex backend. Names
starting with `antigravity/` use the installed Hermes `antigravity-oauth` client
through an isolated SSH worker. The gateway never sends ChatGPT tokens to that
worker. Antigravity credentials remain in the server's existing account pool.

The Windows state directory is `.uuma-local/codex-antigravity-ui-20261102`.
It contains configuration backups, a process receipt, catalog and sanitized
timing/usage records. It must remain outside Git. The shared Hermes gateway,
agent definitions, databases and credentials are not changed by this pilot.

The worker reads the current provider runtime paths from the existing server
gateway environment. It imports the installed plugin in its own process and
uses a temporary inference workspace. Its request formatter preserves the full
Codex conversation instead of applying Hermes's historical tool-output
truncation policy. Native Antigravity host tool execution remains neutralized
by the existing plugin; Codex receives requested tool calls for client execution.

After configuration, restart the desktop app and open a fresh Codex chat. Choose
an `Antigravity · ...` entry in the model selector. The initial catalog includes
only model names observed from the server's `agy models` command. Gemini offers
low, medium and high effort. Other models expose their upstream default effort.
Installation preserves the user's default model. Subsequent desktop selections
may update that preference; the audit does not overwrite it.

This initial bridge supports text, function/custom tools, streamed replies,
replayed conversation turns, and upstream token usage. Images, audio,
server-side search and server-side compaction are not advertised. First-token
latency and elapsed seconds are recorded locally; no thought stream or usage
numbers are fabricated. The user's desktop greeting and isolated native Codex
shell, patch and read-only MCP round trips have now been observed. See
[the compatibility audit](../../docs/operations/codex-antigravity-compatibility.md)
for evidence scopes and remaining limits. Other advertised models have not yet
passed the same end-to-end audit.

The local gateway requires the current ChatGPT access token already managed by
Codex and binds only to `127.0.0.1`. No prompt, tool arguments, outputs or tokens
are written to its event log. The unauthenticated health endpoint exposes only
service state, selected model identifiers, counts, timing and token totals.

The desktop may still include its optional hosted `web_search` definition with
every request. This bridge excludes that unavailable offer and explicitly tells
the model that hosted search is unavailable. A forced hosted-search request and
all other unknown tool types still fail explicitly. No search results are invented.

To undo the pilot, run `manage.py restore` with the repository virtual environment.
It restores the previous provider/catalog settings while preserving unrelated
changes made after installation. Restart the desktop app afterwards. Stopping
the isolated gateway does not stop Hermes or any specialist agent.

Windows Start menu shortcuts under **UuMA** provide gateway startup and routing
restore without a terminal. A current-user Startup shortcut starts the loopback
gateway on login. Restore removes that Startup shortcut. Neither shortcut closes
or restarts the desktop app.

`restore-openai.ps1` provides recovery independently of Python, Codex and the
gateway. The Start menu recovery shortcut and a desktop recovery shortcut invoke
this script and show success or failure. Recovery preserves unrelated settings,
chats and credentials; the user restarts the app afterwards. A model name visible
in the picker is not proof that the composer can submit or inference succeeds.

Existing chats keep their saved provider. Switching only their model name does
not migrate them from OpenAI to this gateway. Use a new chat or a provider-aware
fork to preserve history on the new connection. Do not edit session databases or
rewrite historical rollout receipts to change providers.

The JSON-line worker protocol keeps SSH stdin open during inference. A disconnect
closes the worker's provider client; it does not stop the shared Hermes service.
Gateway health and sanitized events include actual resolved model, provider-ready
time, first text time, elapsed time, client tool count and upstream token usage.
These diagnostics do not add a custom performance panel to the desktop UI.

The experimental reduced-tool catalog is a private candidate only. It is not
enabled by installation. Unknown calls fail explicitly; an exact canonical
namespace spelling may resolve only to an unambiguous advertised tool.
