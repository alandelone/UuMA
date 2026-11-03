# Brainstormer A2A sample and complex analysis worker

Date: 2026-10-23. Scope: a bounded synthetic calculation, real A2A transport,
real specialist execution, and the Brainstormer analysis worker configuration.

Protocol definitions and the boundary between official A2A and UuMA application
rules are recorded in [UuMA A2A integration contract v1](../architecture/uuma-a2a-contract-v1.md)
(draft for review). The completed sample is not a full protocol conformance claim.

## Architecture and evidence boundaries

The existing control flow is:

```text
Orchestrator control tools
  -> TaskContract / capability route / assignment / PENDING Run
  -> trusted Brainstormer A2A endpoint
  -> Hermes assigned run
  -> get_assignment(task_id, run_id, execution_epoch)
  -> delegate_to_gemini(supplied material)
  -> worker receipt / specialist review / submit_result
  -> control-plane result / independent verification
```

An assignment does not create an execution attempt. Register the Run explicitly
before calling `dispatch_run`. Use the registered execution epoch, which the
control plane advances; do not assume it stays at the caller's initial value.

This sample does not establish an automatic Telegram Brainstormer -> Orchestrator
handoff, automatic Wisdom knowledge retrieval, or a completed market cost study.
Those require separate request, provenance, retrieval and return-path contracts.
The first hop must not be represented as implemented solely because dispatch works.

## Worker backend

`GeminiWorker` retains its existing semantic MCP tool name and adds the explicit
`router_api` backend. Brainstormer now selects `complex` at the server-local
`http://127.0.0.1:8080/v1` endpoint. The main Brainstormer model is configured
separately. Other profiles keep their existing worker settings.

`complex` is a router profile, not a permanent underlying model name. At inspection,
its ordered routes were `gemini-4-argon`, `gemini-3.1-pro`, then
`nvidia/nemotron-3-ultra-550b-a55b`. A real completion's observed model must be read
from its receipt rather than inferred from this order.

The worker submits one durable `/v1/runs` request with a generated idempotency key
and `max_attempts=1`, then polls that same run. It has no tools or filesystem
access. Working-directory and authorized-profile checks still apply. Caller input
must contain all needed material; a directory path does not transfer its contents.
Receipts retain requested and observed model, router run ID, usage and outcome.
Timeouts preserve reconciliation identifiers and do not resubmit model work.
The router can choose among its configured routes; the worker itself does not
silently fall back to the account-pool or CLI backend.

## Synthetic fixture

All amounts are supplied assumptions in MYR, not retrieved evidence or quotations.
Area is 400 sqft and available budget is 10,000.

| Item | Formula | Amount |
| --- | --- | ---: |
| Trays | 40 x 20 | 800 |
| Racks | 4 x 300 | 1,200 |
| Ventilation | 2 x 250 | 500 |
| Starter stock | supplied | 600 |
| Initial substrate | supplied | 400 |
| Miscellaneous | supplied | 300 |
| Known subtotal | sum of supplied items | 3,800 |
| Contingency | 3,800 x 15% | 570 |
| Known envelope | 3,800 + 570 | 4,370 |
| Unallocated budget | 10,000 - 4,370 | 5,630 |

Electricity, rent, labor, licensing and their applicability remain unknown. Unknowns
are not zero, and positive unallocated budget does not establish feasibility.

## Release and validation

Private evidence is under `.uuma-local/brainstormer-a2a-complex-20261023/` and the
server's `~/.local/share/uuma/operations/a2a-complex-400sqft-20261023/`. Credentials
are not part of the public report. The server-local config backup is private.

The initial worker source release was
`0a9690e5a63b4f42908ffd8ea57dd693d1a7421a22be7e6ddeae9d17009c75d7`.
Its receipt records the repository commit plus the exact three deployed file
digests, including the uncommitted worker changes. A Git commit alone is not the
deployment identity.

The first real dispatch (`run_9bb3cd61b6504843874d70f2e3dd6329`) returned a correct
synthetic calculation and submitted a result, but its already connected MCP server
still used `account_pool` / `gemini-3.8-flash-medium`. This is evidence that editing
profile configuration alone did not refresh existing MCP connections. It does not
pass the complex-model verification requirement.

The shared gateway was then drained with all five specialist intake gates covered.
Actual active work was zero before restart; the receipt records PID 144499 ->
154353. All five Telegram platforms and the native API reconnected, all gates that
this release paused were restored, and the release's drain marker was removed.
The maintenance receipt preserves the original intake states and rollback steps.

The subsequent live attempt exposed an incomplete deployment package: the copied
`uuma/__init__.py` imports `models` and `service`, which were missing from the
three-file overlay. Brainstormer therefore reported a missing analysis tool and
correctly marked `run_e88a6d4bd2464241a29513f53427aa08` BLOCKED. No complex model
request had been submitted by that attempt.

The corrected immutable worker release is
`c9c11f2e028038323b5076e6c3e23fef56a76b28e0d56e95dc6be65953c1f487`.
It snapshots the complete existing production package (134 baseline files) and
overrides only `gemini_worker.py` and `mcp_gemini.py`. Its manifest records every
baseline file digest and both override digests. A check using the exact configured
worker Python and environment successfully imported the MCP, listed
`delegate_to_gemini`, and observed `router_api`, `complex` and the correct endpoint.
After a second idle drain, gateway PID 154353 -> 162514; all five Telegram
connections and original intake states were restored. The old blocked attempt was
explicitly superseded by `run_1db191572d7d44318dcd51de7300c4d7` at execution epoch 2
under the same Task `task_f3f347bb8fa9409b9fca747174811b97`.

The actual workstation Orchestrator subsequently reached its `dispatch_run` tool
and exposed a missing `a2a` import in its Control MCP environment. Installing the
already declared `a2a-sdk==1.2.3` dependency into the existing project virtualenv
repaired the runtime prerequisite; no Control MCP source change was required.
Workstation setup that uses A2A dispatch needs the project's `distributed` extra.
Import checks must use that MCP's exact Python, rather than an ambient `python`
selected by PATH. A first attempt to restrict the CLI to a dynamic MCP toolset
resolved no tools and is retained as failed evidence, not a successful dispatch.

The next live Orchestrator attempt exposed a refused connection: the registry
correctly describes the server-local `127.0.0.1:8768` endpoint, while the existing
workstation SSH forward listens on `18768`. The A2A client now accepts the explicit
administrator setting `UUMA_A2A_LOOPBACK_FORWARDS`, mapping only that exact origin
to `http://127.0.0.1:18768` while retaining `/agents/<agent>` paths, the original
credential and protocol headers. This setting does not change registry bindings
or grant dispatch authority. Only HTTP loopback origins with explicit ports are
accepted; credentials, paths, query strings and remote destinations are rejected.
It is configured on the workstation Control MCP and recorded in a private scoped
config receipt. Newly started MCP processes load it; existing processes must be
refreshed before claiming the repair is effective there.

Focused local verification: 47 worker, transport and distributed-control tests passed, covering existing backends,
durable submission and polling, receipt identity, scope boundaries, credential
redaction, incomplete responses and timeout reconciliation. Scoped Ruff passed.

## Final live result

The real workstation Hermes Orchestrator session
`20261023_173251_fc40bb` called its Control MCP `get_run` and `dispatch_run` after
the dependency and SSH-origin mapping repairs. It received a real A2A acceptance:

| Evidence | Identifier / observation |
| --- | --- |
| Task | `task_f3f347bb8fa9409b9fca747174811b97` |
| Successful UuMA Run | `run_1db191572d7d44318dcd51de7300c4d7`, epoch 2 |
| A2A task | `b761dac3-1e1c-4b6a-9e28-86c5320688de` |
| Native specialist Run | `run_fbd182ea635e4e9ab96e5323282c9199` |
| Worker receipt | `gw-20261023-caa22dea` |
| Durable router Run | `run_81a1a77ad2114a5eb6f0001acec05e98` |
| Requested model | `complex` |
| Observed model | `gemini-4-argon` |
| Router provider | `gemini_web` |
| Router attempts | 1 |
| Worker duration | 36.244 seconds |
| Router-reported usage | 510 prompt + 456 completion = 966 tokens |
| Independent verification | `verification_161fcc510732409aa668b16e031b32ae` |
| Verified UuMA Run status | `COMPLETED` |

Native events show `get_assignment`, actual `delegate_to_gemini`, successful
`submit_result` with `RUN_RESULT_SUBMITTED`, then native completion. The specialist
submitted the expected four numeric totals, explicit assumptions and unknowns,
the worker receipt path, the router Run and the observed model.

Independent verification compared the submitted values with integer/Decimal
fixture arithmetic, inspected the unknown-cost treatment, and matched the worker
receipt to the completed durable router record and its response model. All three
checks passed; the server control event chain remained valid. Verification accepts
this synthetic transport/model-routing test. It does not approve a business plan,
real prices, a knowledge patch, or a mission gate.

The run's progress heartbeat remained `PENDING` until result submission even while
the native run was executing. Native run events and final control `status` are
separate evidence. Automatic progress synchronization is a follow-up improvement;
this sample does not claim it was repaired.

The final read-back by the same Orchestrator session succeeded: its real
`mcp__uuma_control__get_run` response contained `COMPLETED`, the submitted result,
the matching result digest, all four expected totals and `complex` ->
`gemini-4-argon`. Its final answer reported the synthetic assumptions and unknowns.
The evidence is retained as
`orchestrator-collect.stdout.jsonl` in the private evidence directory. It is a
separate check from transport acceptance and specialist completion.

Final server inspection showed all five specialist intake gates accepting, all
five Telegram platforms and the native API connected, gateway active work zero,
no release drain marker, and the corrected worker source digests matching the
local tested source. Existing workstation gateway processes were not asserted to
have reloaded the repaired client; the actual Orchestrator CLI MCP process did.
