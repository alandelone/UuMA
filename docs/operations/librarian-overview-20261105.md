# Librarian backup overview and one-tap navigation

Date 2026-11-05, Asia/Kuala_Lumpur.

## Scope

The user requested simple Telegram navigation like the other specialists and the
ability to inspect the whole Library's backup status. Librarian remains on
`alandelone-server-001`, using the shared server Hermes gateway.

The new read-only operations MCP connects current backup intake and NAS publication
receipts to both natural-language agent queries and deterministic Telegram commands.
Encrypted backup contents stay in the existing recovery pipeline. Content retrieval
continues through the separately authorized semantic catalog.

## User commands

| Command | Result |
| --- | --- |
| `/library` | Overall received batches, history versions, NAS publication backlog and readable catalog scope |
| `/library_sources` | All registered or received sources, eight per page |
| `/library_issues` | Sources with incomplete capture, no received backup, or missing publication receipt |
| Source detail links | Stable source identity, latest batch date, capture/unavailable counts, publication receipt and content-query scope |
| Page links | Direct one-tap next page without arguments |

Source commands use a digest of the unambiguous device/source tuple. They fit the
32-character Telegram command limit. A source keeps the same command when list
ordering changes. The deployment inventory registers the current source links.
New source enrollments require refreshing the plugin inventory during deployment.

## Implementation

- `src/uuma/librarian_operations.py` reads existing ledgers with SQLite read-only
  connections. Intake totals and latest manifest revisions share a read transaction.
- Publication status requires a matching batch, revision and manifest digest.
- Missing policy sources are explicitly shown as `NO_RECEIVED_BACKUP`.
- Catalog metadata respects the Librarian reader lists. No backup payload or
  recovery key is opened by these queries.
- `integrations/hermes/uuma_librarian_commands` formats short deterministic responses.
  Failed or truncated tool receipts return an unavailable message.
- The MCP launcher binds `UUMA_AGENT_ID=librarian`. Profile toolsets and guard/plugin
  allowlists explicitly include the new operations MCP.
- Existing daily and weekly capture schedules continue to be displayed from the
  accepted deployment configuration. This query does not independently inspect timers.

The issues view reflects recorded coverage and publication. It does not classify
source age, validate all content hashes, or certify a complete restore. Each source
detail exposes its recorded date for inspection. Legacy granted source names with
no received batch remain visible rather than being silently marked successful.

## Verification

Local operations and reader suites passed 22 tests, with one Windows symlink
privilege skip. Ruff passed for the new operations, command and test files. A focused
regression requires each generated source command to fit Telegram's length limit.

Actual server MCP initialization, tool listing and invocation succeeded. The real
status showed 68 registered/received source identities, 207 batches, 209 revisions,
209 matching NAS publication receipts and zero pending revisions. At that snapshot
the readable catalog remained two sources and 59 record versions.

All 68 current source links were registered and exercised against the real operations
response. Pagination and error handling also have fixture coverage.

Actual authenticated model run `run_ffd4459d82224b31a053f10b3f14bdbb` completed and its
native tool ledger included `librarian_get_operations_status` and `submit_result`.
It returned the real receipt totals and separately described the limited catalog.

Source code was deployed in a content-addressed operations release with preview,
previous configuration/SOUL, connection receipt and preflight status. The shared
gateway was externally drained to zero active work before profile publication and
restart. Brainstormer, Forge, Honc, Librarian, Wisdom and Yonc are in the restart scope.
Credentials and domain databases were preserved. No mission gate was approved.

User-originated Telegram command acceptance was requested after deployment. Server
MCP tests and model/API tests are distinct from observing the owner's one-tap use.

### User-reported command dispatch defect

At 18:01 Malaysia the owner confirmed `/library` returned actual backup totals,
while `/library_sources` returned Unknown command. The first direct-handler checks
missed the gateway's underscore-to-hyphen normalization before registry lookup.
The plugin registered underscored keys. The single-word overview worked because
its name was unaffected by this normalization.

The correction registers canonical hyphenated keys while retaining the visible
underscored Telegram commands. It covers source lists, issues, source details and
page links. Focused regression tests now dispatch underscored input through the
same normalized lookup and require canonical registry keys. This is a Librarian
plugin correction. Shared Hermes engine behavior is unchanged.

Corrected immutable release is
`operations-5c650eedc4744d557ab9a078929675f77819daf27ea6988f15c0d8c5e8777b36`.
Gateway PID 194777 reported all six Telegram adapters and API connected. A server
probe imported the deployed engine's actual `GatewayInboundMixin` dispatch method,
registered the deployed plugin into an exact-key test registry and used current
read-only ledger results. All 73 tested underscored inputs were handled successfully,
covering three overview/list commands, two page commands and 68 source details.
The probe exercised the real dispatch method with a controlled registry and event,
without sending Telegram messages. New focused tests passed 3/3 and Ruff passed.
The owner's retry through Telegram remains a separate end-to-end observation.

Final immutable release is
`operations-727b5ac5c17e676c80fc87416dd120bc91ee698a6124f2ff4876625bf95a4ba6`
under the production Librarian releases directory. It supersedes the first operations
release by shortening source commands to Telegram's 32-character limit. All 68 source
detail handlers were rechecked against the final real MCP response. Gateway PID was
193237, all seven adapters were connected, and Telegram registered its 16-item menu.

## Recovery from this configuration change

Inspect current configuration and release receipts before rollback. At a new idle
maintenance boundary restore only the previous profile configuration, role text and
previous plugin link, then restart the shared gateway. Preserve all backup and native
session history. Private deployment and verification helpers/receipts are under
`.uuma-local/` and are excluded from source control.
