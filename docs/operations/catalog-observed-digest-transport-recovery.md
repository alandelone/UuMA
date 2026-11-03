# Exact observed malformed digest recovery — 2026-10-29

The original manual sample stopped after the provider returned a malformed
`skeleton_view_digest` answer. The remote run was completed, but its 941-character
answer contained a truncated initial object followed by another object. It was
not accepted as a returned scientific result or repaired by changing source text.
The actual response remains retained under the private implementation directory.

The isolated scientific successor extends the existing bounded transport recovery
to this exact answer fingerprint, task, provider, run, original operation and
parser failure. Other unknown malformed replies remain held. The existing source,
consent, active-intent, lease, fence, first-unanswered-step and provenance guards
remain required. Semantic retry limits and the three-per-job transport bound are
unchanged. The original failed call remains historical; its replacement has its
own stable operation and actual model provenance.

Forty-four related tests passed. A test-import formatting issue was corrected;
the seven new cases were rechecked and lint passed. An exact real-database-copy
rehearsal verified stale-fence rejection, idempotent authorization, preservation of
all source/model rows, and the exact replacement dispatch, stopping before inference.
The unchanged components reuse their baseline 1746-test evidence; no claim is made
that a full suite was rerun for this isolated successor.

The actual held job was backed up and moved from fence169 to170 through the
append-only recovery API. Its new observer uses frozen source
`catalog-bd0bfa30578b`; the worker reached replacement dispatch at fence171.
All990 original model-event rows were retained. The canonical live v20 runtime
was not changed. Completion of the replacement and the full sample must still be
observed; starting an observer is not proof of a finished result.

Evidence: private `json-control-failure-v178/`, `digest-transport-checks-v180.json`,
`digest-transport-final-checks-v181.json`, `digest-transport-rehearsal-v181/`,
`catalog-fixed-runtime-successor-v21.json`, `digest-transport-resume-v182/`,
and `digest-recovery-night-readback-v183.json`.

The previous continuation guardian correctly stopped on the actual held failure.
The active observer pointer is now `current-original-observer.json`; the old
guardian receipt is historical, and must not be treated as a live controller.
Finished archival must retain this additional execution engine and recovery chain.
