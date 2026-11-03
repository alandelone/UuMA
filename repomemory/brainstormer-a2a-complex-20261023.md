# Brainstormer A2A and complex worker: 2026-10-23

User requested a real sample of Orchestrator dispatching to a specialist and using
the server's port-8080 `complex` model for analysis. SSH/model calls and scoped
runtime repairs were within the requested sample; no external user messages were
sent by the sample.

See [the release and evidence report](../docs/operations/brainstormer-a2a-complex-20261023.md).

- Brainstormer's semantic worker tool is still `delegate_to_gemini`, with explicit
  backend `router_api`, base URL `http://127.0.0.1:8080/v1`, model `complex`.
  Its main conversation model is a separate configuration.
- Actual completed request used `gemini-4-argon`, not an inferred alias target.
  Worker `gw-20261023-caa22dea`; router `run_81a1a77ad2114a5eb6f0001acec05e98`.
- Corrected complete-package worker release:
  `c9c11f2e028038323b5076e6c3e23fef56a76b28e0d56e95dc6be65953c1f487`.
  The earlier three-file overlay was incomplete because `uuma.__init__` imports
  `models` and `service`. Preserve that failure record; do not reuse it.
- Profile config changes alone did not refresh existing MCP connections.
  Both shared server gateway restarts used all-five intake coverage, native
  zero-work drain and receipt-backed restoration. Final observed PID: 162514.
- Workstation Control MCP needed its declared `a2a-sdk==1.2.3` dependency and the
  existing SSH forward mapping from server origin 8768 to local 18768.
  `UUMA_A2A_LOOPBACK_FORWARDS` is set only on that MCP. New CLI MCP processes were
  verified; do not assume an already running workstation gateway reloaded it.
- True Hermes Orchestrator session `20261023_173251_fc40bb` used its MCP dispatch
  tool. Successful specialist Run `run_1db191572d7d44318dcd51de7300c4d7`, epoch 2,
  under Task `task_f3f347bb8fa9409b9fca747174811b97`; final independently verified
  control status `COMPLETED`. Failed old Run was explicitly superseded.
- The sample uses supplied synthetic prices: subtotal 3800, contingency 570,
  envelope 4370, unallocated budget 5630 MYR. These are not market quotations.
  Electricity/rent/labor/licensing remain unknown; no feasibility approval.
- Automatic Telegram Brainstormer -> Orchestrator request handoff and automatic
  Wisdom knowledge reuse were not implemented or proved by this sample.
  Brainstormer already has an `assumption` object kind and grounding relations;
  representation does not validate an assumption.
- Native execution can run while control progress still says PENDING until a
  worker report; use actual run events and final control status for evidence.
- Private receipts: `.uuma-local/brainstormer-a2a-complex-20261023/` and server
  `~/.local/share/uuma/operations/a2a-complex-400sqft-20261023/`. Config backups can
  contain credentials and must not be printed or committed.

Focused verification: 47 tests passed; scoped Ruff passed. Mission gate remains
verification/pending_review. User-facing final result must distinguish real A2A
dispatch and complex inference from the still missing automatic first hop.

## Protocol standard clarification

The user asked whether the protocol follows a real standard and should be written
as a standard. Documented the current integration in
`docs/architecture/uuma-a2a-contract-v1.md`, v1 draft for review, with official
fixed A2A1.0.0 and SDK references. Protocol1.0 differs from SDK package1.2.3.
Wire objects/routes use official SDK types; TaskContract/Run/epoch/approval,
uuma_run_id metadata and dispatch deduplication are UuMA application rules.
The actual A2A hop is dispatcher-to-specialist; analysis uses MCP plus router HTTP.
Existing listing pagination, formal extension negotiation, production HTTPS/TLS,
streaming and complete interoperability remain audit/conformance limits. No claim
of complete standard compatibility follows from the successful sample. This
clarification changed documentation only, with no new tests, inference or deployment.
