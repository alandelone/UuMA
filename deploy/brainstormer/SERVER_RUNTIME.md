## Server runtime boundary

Brainstormer runs on `alandelone-server-001`. Orchestrator, Scholar, browsers,
interactive logins and desktop tools remain on the workstation.

Use the Brainstormer semantic tools for project and topic state. Structural
proposals still require Orchestrator/user review. An explicit human `/topics new`
command keeps its existing behavior through the authenticated command plugin.

The Gemini worker uses the server account pool with its existing task, directory
and receipt limits. Voice transcription calls the server UnlimitedLLM API directly
at loopback port 8080 with the profile's own client identity. It does not use the
retired workstation speech relay on port 8774. ChatGPT consultation uses the workstation
connector. If that connector is unavailable, explain the waiting condition; do not
claim completion or replay an uncertain external action.

Windows paths in remembered conversations describe workstation resources. They
are not local server paths. Do not read other agents' files, credential stores or
databases. Direct file access is limited to the configured profile/workspace/domain
roots; use the owning service for data outside those roots.

Code and profile updates are published manually from an explicit release preview.
Do not update the engine, install a different provider or change task admission
while carrying out a user task.
