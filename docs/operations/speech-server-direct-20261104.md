# Server-owned speech transcription

Updated: 2026-11-04, Asia/Kuala_Lumpur. Operational repair; mission remains
`verification/pending_review`.

## Cause and final route

Forge received and cached the reported voice message at 12:44:36. Its command
provider failed at 12:44:37 with `desktop_unavailable`. The five server profiles
still called the workstation speech relay through reverse-forwarded port 8774;
that server listener was absent. The request never reached UnlimitedLLM.

The owning UnlimitedLLM API already ran on the server. Its original-language
`gemini-3.5-transcribe` route succeeded on the original audio without upstream
failures. No upstream provider or model replacement was needed.

| Consumer | Active transcription endpoint | Authentication |
| --- | --- | --- |
| Brainstormer, Forge, Honc, Wisdom, Yonc | `http://127.0.0.1:8080/v1/audio/transcriptions` on server | Separate named client token per profile |
| Workstation Orchestrator, Scholar | `http://192.168.55.2:8080/v1/audio/transcriptions` | Their own named client token |

Librarian had no explicit STT provider in the inspected configuration; this repair
does not claim to add or verify a Librarian voice entry.

## Applied changes

- UnlimitedLLM commit `b566024` is pushed and fast-forwarded on the server from
  verified clean baseline `d8a9f23`. Unrelated workstation `live_broker.py` and
  `test_live_broker.py` edits were preserved and excluded from the commit/deployment.
- `hermes_stt.py` supports `--router-url`, `--api-key-file`, and `--agent`.
  Secrets are read from private files, not command-line values. Requests carry
  authentication and `X-Hermes-Agent` for attribution.
- Adapter default is one submission, with no automatic replay after an uncertain
  timeout. The router's 300-second budget fits inside the adapter's 330-second
  timeout and the command provider's 360-second timeout.
- Five deployed server profiles changed only within `stt`. All other bytes outside
  that section were checked unchanged. The server uses immutable adapter release
  `~/.local/share/uuma/speech-releases/b398a62fc26ed4bc1798971d13a987c18ec90cb30d34541663a1191aaa312bad/`.
- Existing router client keys were preserved. Missing named clients Honc, Yonc and
  Orchestrator were added. Only Orchestrator/Scholar tokens were delivered to the
  workstation's private `AppData/Local/UuMA/router-clients` directory.
- The API was restarted once after checking its request journal for active work,
  to load the additional client keys. The existing authentication mode was preserved.
  Shared Hermes gateway PID `85355` remained unchanged: configuration reads are
  invalidated by file signatures, so no gateway restart was required.
- Workstation root and Scholar profiles changed only within `stt`. The owned
  startup manifest no longer starts the speech relay or forwards port 8774.
  Verified idle relay PID `32456` was stopped. Other connectors were not stopped
  or restarted. Historical process receipts and relay implementation remain intact.
- No database schema change, Telegram send, lab-log write or research job was
  performed. Recovered voice text was used only for transcription verification.

## Verification

- Windows UnlimitedLLM suite: 129 tests passed.
- Server UnlimitedLLM suite: 127 tests ran successfully, including 3 platform skips.
- Initial Windows suite exposed an existing leaked SQLite connection in the route
  timeout test. The test now uses the store's closing context manager; its original
  routing, timeout and cooldown assertions are unchanged. Initial failure log retained.
- Server API baseline: original Forge audio returned HTTP 200 in about 7.5 seconds,
  `gemini-3.5-transcribe`, zero prior route failures.
- Actual pinned server Hermes `transcribe_audio(..., "gateway")`: Forge succeeded
  in 9.19 seconds. Effective STT loading was checked for all five server profiles.
- Workstation adapter to server: authenticated Orchestrator HTTP 200, about 7.3
  seconds server latency. Actual workstation Hermes Scholar command STT succeeded
  in 10.7 seconds, returning 826 characters.
- API logs attribute the successful calls to the correct named clients/agents.
  Server API ports 8080/8081 remained healthy; retired port 8774 is not required.

These checks prove the real configured transcription commands and API path. They
do not claim a new Telegram message was sent or a hardware journal entry created.

## Evidence and rollback

Private workstation evidence: `.uuma-local/stt-server-20261104/`, including
`workstation-apply.json`, `workstation-retired.json`,
`workstation-hermes-verify.json`, test logs and exact before-config backups.
Server evidence: `~/.local/share/uuma/operations/stt-server-20261104/`, including
`preview.json`, `apply.json`, `api-probe.json`, `hermes-verify.json`, per-profile
before/after files and a private pre-change router key registry backup.

For a scoped rollback, compare the active profile hashes to `preview.json` or
`workstation-apply.json` before restoring the corresponding before-config files;
preserve any later unrelated changes. The prior profile route requires the retired
workstation relay and its reverse forwarding, so restoring it alone is not a
working rollback. Re-enable that legacy dependency only as an explicit operational
decision. Keep the added compatible client keys unless all new consumers have
been removed; do not restore an old registry over later enrollments. No production
database restoration is part of this rollback.
