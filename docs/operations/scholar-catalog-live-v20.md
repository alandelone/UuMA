# Scholar Catalog live initial workflow

The user explicitly requested immediate rollout on 2026-10-28, reusing completed checks
and keeping full-paper interpretation and semantic review off the initial release path.
This supersedes the earlier requirement to wait for the original FULL sample before
activating the initial workflow. The wider research workflow remains in progress.

## Running components

- Catalog Web uses fixed release `catalog-f23432549cac` and the existing RSTV4 owner.
- The active pointer is `.uuma-local/scholar-catalog-runtime/active-release.json`.
- Scholar's live profile includes the separate `scholar-catalog` MCP connection. A real
  stdio handshake returned eight curated tools, and a semantic status read succeeded.
- Scholar's own native MCP schema cache was inspected on 2026-10-28 and contains all
  eight Catalog tools. Its gateway and agent startup logs also mention their discovery
  at 19:56:57 Malaysia time. This verifies native discovery, without claiming a new
  Telegram conversation or a reading request through Telegram was exercised.
- `UuMA Scholar Catalog Reading` is installed and running with one canonical worker.
  Automatic work runs 00:00–08:00 Asia/Kuala_Lumpur; manual requests have priority.
- The installed Scholar research guide describes the new semantic tools and workflow.

The existing owner was already schema 20 when this cutover began. Its consistent backup
is retained with the cutover receipts. The selective INITIAL transfer retained every old
row, row identity, column and schema object. Its real sample displays fourteen candidate
Themes. Unmapped labels remain usable, with independent Field/Topic review.

## Verification policy

Structural, source, quote and workflow checks are deterministic. Candidate output is
available while semantic review is pending. Full interpretation and independent semantic
review must remain grounded in the original PDF and PaperSkeleton; pending work does not
grant scientific acceptance. A manual independent spot check now uses the gateway's
`thinking` profile. Its first response reported `gemini-3.1-pro` and assessed three
initial Themes against their exact original text and PaperSkeleton L1-L4 records.
All three sampled observations were returned as locally supported; whole-paper
centrality remains unverified. This check did not change canonical candidate states.

Reuse the completed 1758-test release result and eleven frontend checks. Future edits
receive relevant checks, with a complete suite at a release boundary. Do not repeat the
unchanged suite to observe background model progress.

## Evidence and continuation

Private receipts are under
`.uuma-local/scholar-catalog-implementation-20261023/live-initial-cutover-v132/`:
`activation-receipt.json`, `live-tools-worker-readback-v133.json` and
`rollout-followthrough-v134.json`. They include the source manifest, original profile and
integration-script backups, consistent owner backup, task XML, and actual HTTP/MCP reads.

The original manually requested FULL sample continues in its retained workspace using its
original frozen scientific engine. Finish and import that evidence separately. Do not
replace the canonical database or replay its successful extraction. The original PDF is
on the existing `Z:` NAS mapping; the post-reboot reconnection preserved its exact hash.

## First night-window observation — 2026-10-29

Actual automatic intents were created after midnight Malaysia time, and automatic
QuickRead jobs were queued and processed. The 01:11 Malaysia readback included five
automatic jobs and the existing completed manual sample. One automatic job was held
with `Reason must bind to a supported PaperSkeleton dimension`; the other four were
queued. These are execution observations, not five completed readings. The dimension
binding failure remains an open item and is separate from the original sample's
malformed-digest recovery. No unsupported reason was silently approved or dropped.

The original manual sample now uses an isolated, focused-tested transport successor
for one exact failed digest, as recorded in
`catalog-observed-digest-transport-recovery.md`. The canonical release remains v20.
