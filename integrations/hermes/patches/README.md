# Scoped Hermes runtime patches

`audio-file-stt.patch` extends the existing voice-transcription path to audio-file
attachments when the current profile explicitly configures:

```yaml
stt:
  transcribe_audio_files: true
```

Default behavior is unchanged. Non-audio attachments remain files. Both immediate
intake and pending-message selection use the same eligibility function; an event
with prepared STT does not submit the audio a second time. Config resolves from
the active profile scope, rather than process-global environment state.

Apply with `patch --batch --fuzz=0 -p1 -i PATH` to a new reviewed Hermes source
snapshot. Never patch an already deployed snapshot in place. The companion
`tests/test_audio_file_stt.py` belongs under the target Hermes `tests/gateway/`
tree and exercises profile A -> B -> A with real config loading, MIME separation,
and pending-message single-path behavior. Run it with existing mixed-attachment
and STT-echo tests. It requires the target Hermes runtime dependencies.

Deployment evidence and rollback:
`docs/operations/forge-audio-file-transcription-20261104.md`.
