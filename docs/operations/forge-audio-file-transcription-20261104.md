# Forge audio-file transcription repair

Updated: 2026-11-04, Asia/Kuala_Lumpur. User authorized checking Forge Telegram
history and resolving the reported failure. Mission remains
`verification/pending_review`.

## What actually failed

Read-only inspection of Forge's native session `20261022_214713_09785ffa`, messages
787-793, confirms the reported exchange. Telegram cached
`audio_d3a4bab1bfe9.ogg` at 14:21:50 as an audio-file attachment. The gateway's
existing media classifier deliberately excluded `MessageType.AUDIO` and
`MessageType.DOCUMENT` from automatic STT. No speech API request was made.

The model therefore received an attachment-path note and attempted transcription
through `gemini_worker`. That is a bounded analysis worker, not the configured
speech API. It failed its deployment binding before inference. The model's claim
that this proved the speech backend was down was incorrect. The original failed
messages, tool results and review receipts remain intact.

The preceding server-direct repair proved voice STT and API calls, but omitted
the audio-file intake branch. This follow-up closes that specific evidence gap.

## Applied repair

- Added a profile-scoped `stt.transcribe_audio_files: true` opt-in to the existing
  gateway classification. Enabled it for Forge only. Audio file and audio-typed
  document attachments now enter the existing server-direct STT path before model
  input. Other files and other profiles retain their previous behavior.
- Current-message and pending-message intake share the eligibility decision;
  an already prepared pending transcript is not resubmitted or relabelled as an
  untranscribed file.
- Prepared immutable Hermes source
  `~/.local/share/uuma/engine-sources/hermes/audio-files-9b9a760a45aff50b05fd` from
  the prior `a74e08df...` snapshot. Only `gateway/run.py` and
  `gateway/run_inbound.py` differ; all 3,133 other source files compare exactly.
  The reproducible patch and two invariant tests are under
  `integrations/hermes/patches/` in the workstation UuMA repository.
- Local Hermes development sources received only the corresponding targeted
  changes. Its pre-existing inbound/agent/cron/transcription changes were preserved
  and were not included in the server runtime snapshot.
- Verified the existing provider-pool release manifest and all five runtime file
  digests, then checked the wrapper's exact interpreter, release script and pool
  root. Forge's stale expected wrapper digest `237706c4...` was corrected to the
  verified `758be57c...` digest. The rejection check remains unchanged. Plan mode,
  caller identity, allowed roots, model and account pool were preserved.
- Added a final systemd overlay pointing at the new source while preserving the
  effective provider/shared PYTHONPATH entries and pinned Python environment.
  At verified idle readiness (zero active agents/API runs/delegations/completions),
  reloaded the shared gateway once: PID `85355` -> `103521`. Scope covers
  Brainstormer, Forge, Honc, Wisdom, Yonc and Librarian. Only Forge's profile was
  changed. There was no speech API restart or database migration.

## Verification

- Two new behavioral tests fail on the original classifier and pass on the
  repaired one. Eight relevant Hermes tests pass, including original mixed-file
  and STT-echo behavior. Profile A -> B -> A uses real temporary config homes.
- The same two invariant checks pass with the pinned server runtime and candidate.
- The actual reported `.ogg` entered
  `GatewayRunner._prepare_inbound_message_text` as `MessageType.AUDIO`, called the
  configured authenticated server speech API, and returned 828 characters in
  8.52 seconds. No model inference or Telegram delivery was used for this test.
- Fifteen existing pool-worker/binding tests pass. A bounded real Forge worker
  readiness request completed in 10.45 seconds and returned `WORKER_READY`.
  Its plan-only result is not an independent filesystem audit.
- Post-reload verification checks the process's actual working directory and
  PYTHONPATH, effective Forge STT opt-in/binding, and all six platform connections.
  A probe during gateway startup initially received connection refused; final
  readiness must be read after connections finish, not inferred from service start.

Tests initially lacked the host's required logging and async-test packages. These
were supplied in a private test-only dependency directory; production environments
were not modified. Missing-dependency/collection outputs and strict red/green
results are retained separately.

## Evidence and rollback

Private server receipts:
`~/.local/share/uuma/operations/forge-audio-attachment-20261104/` contains the exact
before/after Forge config, complete source manifests, overlay, preview, idle-health
receipt, apply receipt, candidate verification, worker verification and final
health observation. Workstation copies and test logs are in
`.uuma-local/forge-audio-attachment-20261104/`.

The recovered transcript is `audio_d3a4bab1bfe9.transcript.txt` in those private
evidence directories. The tests did not send Telegram messages, modify native
conversation history, replay business tasks, or create a hardware lab entry.

Rollback requires an idle boundary for all six shared-gateway profiles. Compare
current config/source hashes before restoring the saved Forge config and removing
only `zz-audio-file-stt.conf`, then reload systemd and restart the shared gateway.
Keep all other overlays and runtime data. That restores the prior source and the
known old audio-file/worker limitations; it is not a successful repair. Preserve
later changes instead of overwriting them. No database restore is required.

Whenever a future pool release changes `GEMINI_WORKER_EXECUTABLE`, verify the
reviewed wrapper/runtime and update `GEMINI_WORKER_WRAPPER_SHA256` atomically.
Do not disable the mismatch rejection to accommodate a release.
