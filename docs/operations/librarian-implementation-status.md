## Current deployment verification, 2026-11-04

Librarian runs on `alandelone-server-001`. The scoped worker and seven-tool read MCP
are active. Its default model is `gpt-oss-120b-medium` through the existing
Antigravity provider. Only Librarian's model/configuration and profile-local guard
and audit plugins were changed. The shared gateway was restarted at a verified idle
boundary; all six configured platform connections recovered.

The final fresh A2A Run `run_f0cae36792894e6c8a6f8c0879f58ab6` executed
`get_assignment`, `librarian_get_backup_status`, `librarian_list_sources`,
`report_progress`, and `submit_result`. All five actual tool completions were
verified without weakening the original acceptance assertion. A2A is COMPLETED;
control is REVIEW, accepted=false, pending USER review. The semantic catalog read
contains only the recorded Brainstormer and Yonc sources; this is not the live
backup collector inventory. Twenty-two matching raw audit records were found;
HTTP audit ingestion into the control database remains unverified.

The deployment exposed and repaired two genuine integration defects: configured
plugin names did not install profile-local plugin files, and the guard interpreted
an `error` field definition inside a Task's output schema as an execution failure.
Regression coverage preserves rejection of real errors and stale authority.
Seventy focused tests and Ruff passed. Earlier failed acceptance Runs are retained.
The Gemini 3.8 model/effort compatibility patch is retained separately; other models'
effort mappings were preserved.

The server midnight collector actually completed on November 4 at 00:02 UTC+8
with its original 36 sources. A new immutable capture release now preserves those
36 and adds six Librarian sources: native history, logs, memories, cron, config,
and SOUL. Its first real execution exited 0, incomplete=0, with 42 configured
sources. Librarian memories are explicitly EMPTY; its other five new sources
were COMPLETE/DELIVERED. Existing daily batches were reused with their real original
capture times. The timer remains midnight UTC+8. No database schema changed.

Current Windows: all six pending November 3 batches were delivered. The actual
November 4 midnight execution delivered eight batches but retained a PARTIAL
Antigravity core batch for one inaccessible presence lock. The broad package
LocalCache source exceeded inventory bounds; it was replaced by three explicit
Codex app directories. A separate owned repair task delivered app-local (87 files)
and app-openai (one file); app-roaming remained RUNNING at the latest observation.
The main daily task is Ready with its midnight trigger preserved. A later manual
core retry remains pending; the original delivered partial revision is retained.
Do not describe this as a zero-error Windows daily acceptance.

A real Codex-state sample was retrieved from server intake, decrypted with the
native DPAPI-protected recovery key, matched against the snapshot digest, and
passed SQLite integrity_check. Temporary plaintext was removed. This proves that
sample's recovery; it does not prove independent offline-key custody.

The read-only local project inventory found 530,537 regular files / 85,089,761,637
bytes and 145 issues, including links that were not followed. No project-file
capture was performed by that inventory. Full first-PC project coverage, evolving
project-to-catalog mappings, fresh Notion synchronization, and broader semantic
indexing remain unfinished. Server free capacity was about 129 GiB; an unbounded
daily full copy of the observed project tree cannot provide sustainable retained
history. A capacity-aware incremental capture plan is required before enabling it;
do not silently exclude development dependencies, linked targets, or private data.
The existing observed inventory now has a prepared 133-shard baseline plan, with
all 145 issues retained. It grants no server access and schedules no new capture.

The second Windows v9 handover ZIP is prepared for the user to run. It includes
the public recovery key, verified server SSH host key, preparation launcher and
digest. It contains no private SSH key or bearer token. Actual second-PC enrollment,
first capture/restore and midnight scheduling are still pending. The first-PC
interactive recovery-key export launcher is also prepared; the user has not yet
confirmed an independently recoverable export. Do not obtain its password in chat.

The NAS hardware issue remains deferred by explicit user instruction and the NAS
publisher remains disabled. Server intake success does not imply NAS publication.
The overall mission gate remains verification / pending_review.

Evidence (private operational receipts; paths relative to the server UuMA root):

- `operations/librarian-a2a-guard-fixed-verified-20261104.json`
- `operations/librarian-a2a-guard-fixed-audit-20261104.json`
- `operations/librarian-gateway-reload-a0470937d5944580a6c66e7364915cd3/receipt.json`
- `production/librarian/releases/hooks-3474fb2a39c89c2f88dcb2d4a2c44bc20380f3090e92e120a0137ee8ec837a43/receipt.json`
- `production/librarian/releases/server-self-capture-20261104-66dfacc1a69e4dfd9e8e4a6639ac9abe/receipt.json`
- That release's `status/run-6c9a2742f0fc46c58d407636d47e2daa.json`

Local private receipts and launchers are under `.uuma-local/librarian-implementation-20261029/`.
The following dated sections are retained historical observations.

## Deployment continuation, 2026-11-03

The user authorized implementation after the independent audit and explicitly deferred
the NAS disk issue. Its existing publisher remains stopped; no disk repair or claim
of resolved NAS health is implied.

A dedicated Librarian-only worker was tested (four focused tests and Ruff), deployed
as a hashed script, and verified through real stdio MCP initialization and authenticated
control intake. It rejects other identities, stale assignments and mutating direct work.
Librarian registration was enabled through an append-only control event, with a
consistent SQLite backup and prior definition retained. Its next-start default was
prepared in a new scoped overlay. No domain schema was changed.

A server collector execution completed on November 3 with 36 configured sources and
incomplete=0, delivered to the server system-disk intake. This is registered-source
capture, not an all-data inventory, a NAS publication, or proof of live Notion sync.
Receipt: server operations librarian-server-daily-prepared-081ab49d6e85456981a493de26c53aa5/status/run-c6a3c879c9174338b8899abbc8c264a9.json.

The first Windows scheduled task was executed. It exposed an overly broad ACL on
the native-context device SSH private key. That ACL was corrected to the current
user and SYSTEM. A retry of the original November 3 Codex-state batch received a
verified server manifest receipt. Native and packaged AppData queues were found to
be distinct; neither history was deleted or merged. Remaining pending native batches
are being delivered through a session-capable runtime. The daily action was upgraded
to a verified version using negotiated sessions; its original midnight trigger,
registered source paths and native queue are preserved. Initial execution returned
2 and is retained as incomplete evidence, not silently converted to success.

The shared Hermes gateway was restarted only after authenticated health showed no
active agents/API runs and drainable=true. All five messaging connections and the API
reconnected. Its initial 45-second observation timed out; later health confirmed
success. Librarian startup registered five worker tools plus seven reader tools.
An existing A2A acceptance task is being continued without replacing its UuMA Run;
a later model attempt exposed a provider model/effort incompatibility. Final worker
result submission and acceptance are still being checked.

The user confirmed no independent recovery-key export exists and chose to run the
second-machine installer personally. A verified v8 ZIP, SHA256, setup steps, and
first-workstation interactive key-export launcher are under
.uuma-local/librarian-handover-20261103/. No password or private key was included
in that installation ZIP. Second-device enrollment, independent key custody, full
project-file coverage and end-to-end daily acceptance are not yet claimed.

# Librarian implementation status

Direct intake-to-external continuation: restricted server intake ledger comparison
found 55 manifest revisions versus 49 in the external v1 recovery tree, with no
conflicting or external-only revisions. Six were missing: Antigravity core, Codex
app roaming, two watchdog batches and two Yonc Graph batches. Receipt:
`.uuma-local/librarian-implementation-20261029/intake-vs-external-20261102.json`.
A low-priority, requested 1 MiB/s direct server-system-disk to USB tar export of
those six was launched as PID 56852 and observed processing Antigravity. Each tar is
kept as `.partial` until its exact frozen manifest and all included encrypted object
hashes and sizes are verified, then renamed `.tar`. Inspect the original process,
device-local `direct-intake-export-20261102.jsonl` and `.log`; do not start a second
copy on timeout. No NAS writes are performed. No completion receipt was observed at
launch; manifest PARTIAL coverage remains PARTIAL and other server queues were not
included. Preserve the USB and partial files. Launch receipt and scripts are under
`.uuma-local/librarian-implementation-20261029/`.

External v1 recovery history audit: 49 retained manifests form 48 batches, with
continuous revision numbers and matching predecessor digests; no chain errors were
found. The only PARTIAL revision is `workstation:codex-sessions:2026-10-30` revision
1 (one stable-file ValueError); its retained revision 2 records COMPLETE with zero
unavailable entries. This does not detect batches never published to the external
copy. Receipt: `.uuma-local/librarian-implementation-20261029/external-history-audit-20261102.json`.

External rescue audit continuation: a read-only scan of the external v1 recovery
`objects` directories finished with 7,774 hash-named objects matching their SHA-256
names, and two `.pending-*` files reported as unexpected names and retained. A
separate audit found 49 digest-valid `manifest-*.json` files and 4,996 captured
object references, all present with matching sizes; 48 manifests say COMPLETE and
one says PARTIAL. These audits do not prove source completeness, authenticate the
manifest history chain, validate live databases, or include other archive layouts.
Evidence: device-local `external-rescue-object-audit-20261102.jsonl` and
`.uuma-local/librarian-implementation-20261029/external-manifest-audit-20261102.json`.

External NAS rescue update, 2026-11-02 22:02 MYT: original Robocopy PID 53468 is
absent and its log has a terminal summary: 16,783 files and 22,820,530,120 bytes
copied, zero reported failed files or directories, 1,998 directories copied and one
skipped. This was a live non-atomic copy over SMB to the exFAT external disk; `/XJ`
excluded links and Linux ACLs were not preserved. Three historical tarballs matched
the NAS by SHA-256, and 20 selected encrypted objects on the external disk matched
their content-addressed names. Receipt:
`.uuma-local/librarian-implementation-20261029/nas-rescue-sample-20261102.json`.
This sampling does not verify the entire tree, excluded links, or live databases.
Do not treat the NAS hardware as repaired or the Librarian deployment as complete.

On 2026-11-02 the external Seagate One Touch disk was connected to this Windows host
as `D:` (exFAT, approximately 1.36 TB free). A non-destructive NAS rescue copy from
`Z:` to the new directory `D:/NAS-rescue-20261102-ec7490d5daa5440094b762d9c4290740`
was launched as Robocopy PID 53468 with requested 1 MiB/s throttling, idle priority,
no retries, and link exclusion. Its process was observed live and copying files.
Receipt and Unicode log are in `.uuma-local/librarian-implementation-20261029/` as
`nas-external-rescue-launch-20261102.json` and
`nas-rescue-robocopy-487c4c4e4107475ca7b4451bc3fd0f5c.log`. Do not restart based
on an observation timeout: inspect PID and log, preserve partial results, then
review errors, skipped links, active database consistency and verify copied data.
The rescue is not complete or verified yet. exFAT does not preserve Linux ACLs.

The Yonc Graph collector finished: both server intake manifests report COMPLETE for
the non-atomic 1,489-file inventory, including SQLite online snapshot sidecars. One
encrypted object from each shard was fetched from server intake, decrypted, and
matched to its unchanged source. Receipt:
`.uuma-local/librarian-implementation-20261029/yonc-graph-server-restore-20261102.json`.
This does not verify every file or establish a NAS recovery copy.

On 2026-11-02 a one-shot, low-priority workstation `yonc-graph` collection was
launched to the server's system-disk intake, not NAS. Its fresh inventory observed
1,489 files in two shards. The first launch failed before capture because Windows
process-handle types were incorrect; the original process was confirmed gone and
the failure retained. A corrected immutable runtime was verified and launched once;
its process and `started`/`inventory` progress were observed. The current run is
not yet evidence of delivery or recovery: inspect the same process and
`%LOCALAPPDATA%/UuMA/Librarian/devices/workstation-f2c381ecd4dd493b842cc3b2670aac35/yonc-graph-inventory-20261102.jsonl`
before taking further action. Launch identity and source-grant receipts are under
`.uuma-local/librarian-implementation-20261029/yonc-graph-*20261102.json`.
No project-wide or NAS backup completeness is implied.

At the following inspection, the same collector process remained live and its local
queue contained 272 encrypted objects (11,019,467 bytes). The batch transaction and
server receipt were not yet complete; these object counts do not prove delivery.
The NAS publisher timer remained disabled and inactive; the RAID check's mismatch
counter continued to rise, reaching 336,384. No external USB disk was visible.

> Update, 2026-10-30: The earlier increment report below is historical. Its claims
> that there is no production key, restricted SSH intake, or installed service are
> superseded by the deployment record in the next section.

## Production progress and remaining work, 2026-10-30

On 2026-10-31 a bounded project inventory planner was implemented and tested:
it assigns distinct shard IDs, retains inventory issues and explicitly labels its
scan non-atomic and not captured. It does not yet perform shard authorization,
capture or scheduled transfers. The separately authorized
`project-chatgpt-watchdog` source was captured and delivered to server intake as
PARTIAL, with seven captured files and one locked `watchdog.lock`. Manifest SHA-256
is `9bc2d64f8da618687760db93aa0d52dcc61590d6ec83fcade088d2ae146be3c7`.
One Python source was independently retrieved from server intake, decrypted with
the workstation recovery key, and its plaintext SHA-256 matched the current source
(`b3cb5c09fdd2c99ce58094175fe0befaa75d1c684dfbc578ad6c6ac298ba48fb`). This is
one server-intake restoration, not a NAS restore or full project coverage. The
NAS publisher remains paused and other project directories are not covered by
this sample. The pre-change intake grant policy is privately retained at server
operations `librarian-policy-before-project-af069661e5184fa8bf9302b9888b7d9c`.

The workstation `CodeSpace_Local` root currently has 27 top-level directories,
including project repositories and non-project directories. The registered source
configuration does not yet cover that entire root; its contents, exclusions,
mutable files and any links need explicit inventory and scalable capture. Existing
agent-history backups do not establish project-file coverage. The second machine's
actual project roots and enrollment likewise remain unknown until it is prepared.

On 2026-10-31 the server's independently scoped `librarian` token was added to
the existing identity registry using an atomic replacement and a private pre-change
snapshot. A live request to the independent Librarian MCP returned its one visible
classified record, and using the same token as Honc was rejected with HTTP 403.
This establishes the service identity, not a running Hermes agent or A2A binding.
The workstation source now defines a disabled, read-only Librarian agent and
enforces disabled-agent policy for explicit assignments as well as routing; this
control-plane source change has not been deployed to the shared running service.
The actual Librarian stdio proxy listed seven tools and read its classified
record using this identity. A server profile has been staged, not activated, in
`operations/librarian-profile-stage-c3f6a054d26341a68f075904b9ff9462`; its only
MCP servers are the scoped worker and Librarian reader. The existing production
control API still rejects the Librarian worker token with HTTP 403. A minimal
control overlay is staged at
`operations/librarian-control-overlay-dc17e4a0ee564203b0e2e4fd7601e6f5`;
it was tested with the production interpreter and source chain against an isolated
temporary database. The fixture registered eight agents, kept Librarian disabled,
rejected assignment and verified the event chain. Live control, A2A, Hermes gateway
and guard plugin have not been restarted or updated; their active runs must be
rechecked and a non-disruptive release coordinated before enabling the agent.

Later NAS safety observation: the Antigravity batch's 39,703 encrypted objects
and its PARTIAL revision 1 manifest reached server intake; its one unavailable
entry was a locked `.lock` file. Codex app local and OpenAI subtrees were COMPLETE
at intake and their two NAS manifests were hash-verified. The Codex app roaming
subtree reached intake as PARTIAL: 25,034 entries, including 95 unavailable
(82 `PermissionError`, 13 `TimeoutError`). Its NAS publication is unverified.

During publication of the large Antigravity batch, host I/O pressure reached
approximately 80% and the NAS received only about 3,055 objects after hours.
The dedicated publisher timer was stopped and the publisher was sent SIGTERM;
no server intake or retained NAS objects were removed. I/O pressure subsequently
fell to around 3%. The RAID showed both members present and both SMART overall
health checks said PASSED; these checks do not prove there is no disk problem.
The old publisher must remain paused until a better approach is tested against
the user's non-disruption requirement. Do not treat its systemd failed result after
the deliberate stop as a completed publication.

A tested local candidate groups and rate-limits v1 object publication with an
I/O pressure guard. Windows tests passed; Linux tests passed, including grouped
sync and recovery after injected failure. An isolated 128-object actual NAS test
nevertheless raised I/O pressure above 60% after its first 64-file group; it
deferred itself and did not publish a success manifest. It is not deployed.
Avoid retesting real NAS writes while pressure is high; explore a format with far
fewer filesystem objects, safe restoration, versioned manifests and bounded I/O.

An experimental `librarian_packed_recovery` implementation now stores separately
in a packed-v2 layout and ledger without modifying v1, with authenticated object
hashes, deterministic restart receipts, versioned manifests, retrieval indexes,
and exclusive capsule restoration. Windows tests passed, including decrypting an
actual fixture and retaining partial and later versions; Linux isolated tests
passed. It has not been deployed as a production publisher. A 16-object real
NAS fixture first deferred before a pack due to I/O pressure, then on a later
attempt wrote one verified fixture pack and its group receipt but deferred before
the manifest. A resume reused that pack and wrote its map but deferred before the
manifest. During each short NAS write test, measured I/O pressure rose above 40%.
No success receipt or production publication was recorded. The test data remains
under `backups/librarian/v1/verification/packed-fixture-399a644094294689b919806922befce2`;
do not erase it or blindly repeat NAS writes. NAS responsiveness requires further
diagnosis before using this candidate; current user-impact guard remains in effect.

Second Windows bundle v8 and the session-capable server enrollment release were
prepared and tested in isolated fixtures. Bundle SHA-256 is
`2fe89c84012b0d6f931fb4a87a0168431e5af0da9241a08dd8513054fdcb3454`.
The old enrollment helper pins an incompatible legacy receiver; follow the v8
runbook. No real second-device key or daily schedule was installed.

Subsequent continuation: Windows package inventory identifies
`OpenAI.Codex_2p2nqsd0c76g0` as the Codex desktop package; its `LocalCache` is not
evidence of complete ChatGPT cloud history. A paged scan of its whole LocalCache
failed because a directory changed during enumeration. A later scoped scan found
92 files in `Local/Codex`, one in `Local/OpenAI`, and 25,040 in `Roaming/Codex`,
with no reported inventory issues at that observation. This does not cover the
other virtualized application directories under LocalCache.

The server policy now grants the existing workstation device only three additional
explicit sources: `codex-app-local`, `codex-app-openai`, and `codex-app-roaming`.
The preceding policy is privately retained in server operations as
`librarian-policy-before-codex-scopes-aa189eab9e1d4e29b3490411be6d2492`. A
verified isolated workstation runtime `codex-scopes-3fe72dbc87534c6692440645d6ec8402`
started low-priority one-shot capture using its own queue and
`codex-scopes-progress.jsonl`; a running process is not proof of completed intake,
NAS publication, restoration, or daily scheduling. Scope capture tests and the
workstation/discovery suite passed 13 cases (one Windows symlink privilege skip),
and the affected code passed Ruff. The original large Antigravity transfer remained
active after the policy change, with 28,416 encrypted objects reported delivered
at the latest check; its final manifest and NAS publication remain unverified.

Later continuation: the Librarian semantic index batch was published to NAS and
its manifest SHA-256 verified as `16e360f0ac8645c78154c261f6fcb1e4e5ba24311d41eef82f69426b1e02b0fd`.
This index still contains only one explicitly classified Brainstormer structural
summary; it does not establish complete semantic or A2A coverage.

The workstation-only SSH forced-command receiver now uses release
`intake-session-39725dfe81aa466a9ac6a142902665f7`. It accepts legacy frames and
negotiated sessions of at most 256 objects; manifests are limited to 64 MiB and
100,000 entries. The previous authorized-keys bytes were saved privately under
server operations and only the workstation release path was switched. A live
device-key handshake passed. Linux transport/intake/publisher tests passed 39
cases, including a greater-than-16-MiB manifest published to a fake archive and
ungranted-source and oversize rejection. A one-shot, idle-priority workstation
transfer is delivering the existing Antigravity batch in the background; monitor
the device-private `transport-progress.jsonl`. The batch had 39,703 encrypted
objects and one unavailable source at capture, so even successful delivery does
not imply complete coverage; NAS publication and recovery require verification.
The new session protocol has not been installed on the second device's enrollment
release or enabled in the daily collectors.

The `chatgpt-localcache` scan exceeded the current 100,000-entry inventory bound
and has not been captured. Its registered root contains both Codex-specific and
other virtualized application directories. Partitioning or resumable discovery must
preserve an explicit record of all covered and uncovered source paths; a partial
inventory must never be reported as complete. The user's separately verified
offline recovery-key export remains a prerequisite for unattended daily capture.

Continuation at 09:44 MYT: the original workstation run ended with Codex sessions
PARTIAL (one actively written JSONL), Antigravity core and the application local
cache FAILED with `PermissionError`, and Scholar catalog COMPLETE at intake. At
that observation all 45 intake revisions, including fixture revisions, were
published to NAS. The new JSONL prefix collector verifies a fixed complete-line
prefix without blocking appenders; its Windows and Linux tests passed. A real
retry produced a COMPLETE revision locally and was still delivering. That first
production prefix version records its size and hash but lacks a separately stored
cutoff timestamp; the next fixed source release adds that timestamp. Failed source
retries are queued behind the Codex delivery. A process being queued or running
does not prove its results. The publisher's counts do not establish complete source
coverage or end-to-end restore verification.

At the subsequent check, Codex sessions revision 2 was COMPLETE and delivered to
server intake; it was subsequently published to NAS and the 134,927,118-byte
active JSONL prefix was actually restored and matched its recorded SHA-256 and
size. This v4 capture does not record a separate source-cutoff timestamp.
Antigravity core and local-cache retry had begun as the next background process.
The updated workstation task XML
remains an unregistered draft and uses fixed release
`workstation-bb3f0480bdf14b98821ea603ec997d3d`.

- A workstation-specific SSH key and restricted server intake are installed. The
  existing authorized keys were preserved. Server receipt and publication databases
  are private and do not grant semantic access to recovery archives.
- The production recovery private key is protected by the current Windows user's
  DPAPI and private filesystem permissions. An independently held offline export
  has **not** yet been made. Loss of this Windows profile may therefore make all
  archives using this key unrecoverable. `scripts/export-librarian-recovery-key.py`
  prepares a separately password-protected export to an independent local drive.
- Actual workstation Codex state and server Brainstormer and Yonc SQLite backups
  have been published to NAS and restored, with SHA-256 and SQLite quick checks.
  Additional server agent databases and file sources were captured into private
  server intake. A low-priority server publisher timer retries NAS publication.
- A multi-source workstation capture started on 2026-10-30; its private per-source
  receipts report completion and failures. A started run is not evidence that every
  source has finished, reached NAS, or covers cloud-only conversations.
- The publisher timer only publishes already captured batches. Daily collection
  schedules for the workstation and server have not been installed. Independent
  recovery-key custody must be established before activating unattended capture.
- Prepared workstation task XML passed Task Scheduler's unregistered XML parsing.
  It runs for the interactive user, so a missed midnight needs a later login. The
  draft includes the Scholar catalog, but not its large artifact tree. The first
  concurrent Scholar capture failed on the collector's SQLite queue lock; a separate
  low-priority retry waits for the current collector to exit. Neither a waiting
  process nor an accepted task definition is evidence of a successful capture.
- A server daily-capture configuration for 36 existing source batches is prepared
  in `operations/librarian-server-daily-prepared-081ab49d6e85456981a493de26c53aa5`.
  Its source paths and live owner checks passed; it has not been scheduled. This
  list is not a claim of complete system coverage.
- A second-computer preparation bundle is available at
  `.uuma-local/librarian-implementation-20261029/second-windows-bundle-v7-ba18a7f0f0da4d2cb84fe6c970c9e7e8`.
  An isolated Windows fixture created its own SSH key, installed its dependencies,
  and queued a fake source while offline. Actual device enrollment and scheduling
  have not been performed; the bundle's local integrity manifest is not a signature.
- The server enrollment helper is staged as fixed release
  `/home/alandelone/.local/share/uuma/production/librarian/releases/enrollment-330be9cd08b242d5a883a75aa51b5fa9`.
  POSIX tests and a Windows-generated public-key request against an isolated server
  policy passed. The initial cross-OS test exposed a Unicode SSH key comment and
  the subsequent version handles it. Enrollment still requires the real second
  computer's request and a separately checked SHA-256. Coordinate a single writer
  for server policy and authorized_keys; advisory locking cannot protect against
  unrelated programs that ignore the lock. Preserve the pre-change snapshots and
  reconcile an incomplete intent if publication is interrupted.
- Server-side Librarian agent registration, production A2A and full semantic MCP access,
  safe source classification, broader source coverage, retention capacity management,
  and full acceptance remain unfinished. Encrypted recovery archives do not
  themselves provide MCP search.
- The source now supports an authenticated, opt-in Librarian route through the
  existing semantic MCP transport, with an independently checked source/record
  grant at read time. An owner-side catalog publisher accepts only explicitly
  classified record versions, verifies object digests, preserves older versions
  and catalogs, and supports narrowing reader access. Linux isolated tests exercise
  actual catalog publication followed by an authenticated MCP read, denial and
  identity-spoof rejection. A separate production read-only service now runs on
  server loopback `127.0.0.1:8788`; its sole published real record is a derived
  structural index for the specified Brainstormer topic. The index contains counts,
  source revision and status, not original discussion text; coverage is PARTIAL.
  Actual authenticated Brainstormer reads and unauthorized/spoofed reads have been
  verified. Other agents are not yet configured to call the route, and the 16 MiB
  JSON catalog limit remains. Classification must identify secrets even inside
  otherwise ordinary records; merely labeling a file safe is not proof it contains
  no credentials. Its current archive was captured into private recovery intake;
  NAS publication must be checked separately.
- Daily encrypted snapshots are not globally deduplicated and NAS capacity is finite;
  indefinite retention has not been demonstrated. Notion's midnight cache snapshot
  does not establish that its 03:00 sync completed successfully.

Detailed private operational receipts are under
`.uuma-local/librarian-implementation-20261029` and the server Librarian production
deployment-receipts directory. Keep credentials and recovery-only data out of MCP.

The user has authorized full implementation and production deployment: this Windows
workstation first, server collectors and Librarian next, with a tested installer for
the other Windows computer. No further authorization is needed for that scope.

## Locked decisions

- Daily capture at 00:00 UTC+8; offline capture reports its actual time.
- Source/project-scoped reads; project association never grants permission by itself.
- Credentials are encrypted recovery-only material, excluded from MCP retrieval.
- Preserve originals, source history, attachments, domain data and project files.
  Exclude only verified rebuildable dependencies and caches, with explicit coverage.
- Five existing specialists run on the server; Scholar/Orchestrator remain on the
  workstation. NAS aliases are the same live storage, not additional backup copies.
- Preserve all existing source authority, task state and historical backups.

## Implemented components

- Read-only MCP and catalog reader now include a seventh read-only tool for
  authenticated bounded binary chunks; the reader still uses the limited JSON catalog.
- SQLite online snapshot with bounded deadline, quick_check, digest and no overwrite.
- Streaming recovery capsules: AES-256-GCM with RSA-OAEP-SHA256 wrapped object keys.
  Capsules authenticate the header and content; failed authentication never publishes
  recovered plaintext. RSA recovery keys require at least 3072 bits.
- Local SQLite recovery queue: one immutable explicit-file capture per device/source/date,
  source stability checks, partial coverage, exact batch reuse and pending delivery state.
- Trusted-destination recovery delivery: ciphertext size/hash readback, immutable manifests,
  idempotent retries and transactional delivery state. Delivery preserves PARTIAL status.
- Packaging extra `librarian` declares the tested cryptography dependency.
- Windows current-user DPAPI protection and key initialization/offline export primitives.
  Actual production storage, private ACL validation, secure password entry and an
  independently held recovery copy are not yet connected or verified.
- Bounded source discovery and resumable pages with directory-change detection. Obvious
  credential filenames are recovery-only; all other files remain UNCLASSIFIED. Only
  explicitly verified relative directories can be excluded. Pages must be aggregated
  and validated before publication; file content classification is not implemented.
- A server-local encrypted-object intake primitive checks framing, digest, size,
  format and exclusive publication. It is not a network listener and does not bind
  an authenticated device identity. Its destination must be private local storage.
- A partial daily recovery batch can retry unavailable entries under the same batch
  identity, preserving successful captures and immutable prior published manifests.
  Retry entries carry actual retry time and a chained manifest digest.

## Verification for this increment

Windows: 34 cases passed, one existing symlink case skipped for OS privilege;
affected-source Ruff checks passed. This includes the existing reader/MCP suite,
new encryption/queue tests and SQLite deadline regression. Logs are under
`.uuma-local/librarian-implementation-20261029`.

An independent Linux/server fixture using the exact three implementation sources
passed batch reuse, repeated NAS delivery and actual encrypted-file restoration
from NAS. It contains fake data only. Its receipt is under server operations
`librarian-encrypted-verification-c5b514a199a64ee0a4b71751a20512f0/receipt.json`.
The fake NAS fixture is under `backups/librarian/v1/verification/` with the same name.
No key from this fixture is a production or user recovery key. Windows used
cryptography 50.0.1; the independent Linux smoke used existing cryptography 41.0.7,
not a newly installed production environment.

The recovery queue accepts trusted explicit stable files and explicitly declared live
SQLite paths; declared databases use online snapshots and regular-file copying rejects
the SQLite signature. Recovery delivery is a low-level local
publisher primitive; it is not an authenticated remote intake service. Source paths in
its private queue/manifests are recovery metadata, not an ordinary MCP catalog.

## Not activated or complete

No production key has been generated or exported by these components. No encryption
claim applies to the older one-database NAS pilot. That pilot remains historical evidence.

Automatic source discovery/adapters, sensitive-record classification, DPAPI protection
and offline private-key export, restricted SSH intake, ordinary archive publication and
scalable read index, scheduler integration, production profile/A2A/MCP binding and the
second-PC installer remain unfinished. No service or scheduled task was installed in
this implementation increment. Do not call these pending components deployment-ready.

Continue with isolated platform tests and actual owner/source discovery, then complete
the accepted deployment plan and run end-to-end source/recovery acceptance. Do not
replace the entire shared gateway or trigger scientific work to test backup behavior.
# Project inventory capture continuation (2026-11-02)

The bounded, low-priority workstation inventory finished 27 top-level directories:
16 were discovered without reported issues and 11 were partial. It observed 47,834
files, with nine page bounds and 127 link/reparse-point exclusions reported. Two
direct files in CodeSpace_Local were recorded separately and not captured. Discovery
is non-atomic, does not itself back up any file, and is not proof of whole-project
coverage. The 2026-10-31 watchdog project capture reached the server partially
(seven of eight files; one lock was unavailable); a captured file was decrypted and
verified against its source from server intake, not from NAS.

The new `librarian_inventory_capture` implementation connects explicitly granted
inventory shards to the encrypted queue and optional session delivery, with path and
grant checks, SQLite online snapshots, explicit unavailable sidecars, and incomplete
coverage reporting. It is a local candidate, not yet configured or activated in a
production schedule. The focused Windows inventory tests passed (9 cases). No claim
is made that the remaining projects, historic files, or either PC have complete NAS
backups. NAS publishing remains paused after excessive I/O pressure. Offline recovery
key custody, second PC enrollment, production Librarian A2A and daily scheduling
remain incomplete; follow the detailed later entries and verify live state.

On 2026-11-02, one explicitly authorized live project shard was captured using the
new inventory path and delivered with the workstation's restricted SSH identity.
The server accepted its immutable manifest `516f9624c7a9e46f601bf907b523a054ec9c9a7261fc2b5b0477cc6c337ace7d`;
seven of eight files were captured, with `watchdog.lock` unavailable due to
PermissionError. One captured Python file was fetched from server intake, decrypted,
and matched to the source SHA-256 `b3cb5c09fdd2c99ce58094175fe0befaa75d1c684dfbc578ad6c6ac298ba48fb`.
This did not verify NAS recovery. A subsequent idempotent replay reused the server
manifest; the caller's bandwidth limit is now passed to both capture and delivery.
The scope grant was added with an atomic policy update and pre-change backup, recorded
in `.uuma-local/librarian-implementation-20261029/inventory-watchdog-live-20261102.json`.
This is one partial project shard, not production-wide source coverage.

### NAS health incident (2026-11-02)

Read-only inspection found `/mnt/nas` on `/dev/md0` RAID1 (`sdb`, `sdc`) with both
members marked present but an ongoing `check` advancing slowly (about 200 KB/s).
`mismatch_cnt` rose from 131,712 to 198,272 during observation. The kernel repeatedly
logged `/dev/sdc` READ errors with `UNC` and media-error status on November 2. The
device's SMART overall status reported PASSED despite historical reallocation count
11 and the current kernel errors. These observations do not identify which files or
mirror copies are correct. Do not run repair, remove a member, rebuild, format, or
assume the NAS is a verified recovery destination. The Librarian NAS publisher timer
remains inactive. Read-only evidence is retained at
`.uuma-local/librarian-implementation-20261029/nas-readonly-evidence-20261102.json`.

The user has an external disk; at initial check neither the Windows host nor the
server exposed an identifiable connected USB disk. Wait for connection and establish
its identity, capacity, existing content and writeability without formatting. Prepare
a low-impact, resumable, non-destructive independent copy with explicit errors and
verification; live databases require consistency-aware capture. Do not treat a copy
to the server system disk as independent of the server. Coordinate access to the
shared NAS workspace and preserve existing sources and the live RAID check.

The Windows `Z:` mapping was observed as `\\\\192.168.55.2\\NAS`; the external disk
was not yet visible. A fake-data Robocopy fixture verified that this Windows version
accepts `/E /Z /R:0 /W:0 /COPY:DAT /DCOPY:DAT /XJ /IORATE:1M /IOMAXSIZE:64K
/THRESHOLD:0 /NP`, preserves unrelated destination files on repeated copy, and
produces matching fixture content hashes. Robocopy may adjust requested throttling,
`/XJ` excludes links, and copying active files does not establish database consistency.
This fixture is preparation only: no NAS rescue copy was run and no external volume
has yet been identified or written. Test receipt is reproducible with
`.uuma-local/librarian-implementation-20261029/test-nas-rescue-robocopy-20261102.py`.

At 09:52 MYT the publisher timer was observed **enabled but inactive**, meaning a
future reboot could reactivate it. It was disabled with `systemctl --user disable`
and read back as **disabled and inactive**, preserving the timer unit and data.
Its prior state was enabled; re-enable only after the NAS incident is resolved and
the publisher's impact and recovery path are verified. The RAID check was not stopped.

