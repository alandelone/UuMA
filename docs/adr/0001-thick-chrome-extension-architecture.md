# ADR 0001: Thick Chrome Extension Architecture

**Status**: Original architecture accepted; implementation constraints revised for review, 2026-09-27.
**Scope**: Architecture decision, not implementation or platform acceptance.

## Context and decision

Retain a Manifest V3 thick extension using per-platform content scripts and shared core.js.
DOM interpretation and per-page actions stay in the extension. The service worker coordinates
navigation and tasks; Python services own authorization, durable batches, review and persistence.
See the [implementation plan](../plans/labbot_implementation_plan.md) for the current contract.

Thin (raw DOM to Python), medium (Python directs each page), and thick designs were considered.
Thick was selected to keep platform parsing close to the page and reduce per-action round trips.
It does not mean that a content script owns the only copy of extraction state.

## Required lifecycle

Before navigation, persist the current order, detail queue, return location and acknowledged batch
checkpoint. After navigation the new content script registers with the service worker and resumes
only after task, account and page validation. Browser or host restart requires reconciliation with
durable receipts. connectNative lifetime support does not replace recovery.

Content scripts only process authorized read operations in Phase 1. The service worker validates
the actual sender and task/tab/account binding. Page text cannot create commands or approve mutations.
Per-platform fixtures and permitted live samples must independently verify identity, parsing,
pagination and recovery. Adding a module also requires scope, permissions and acceptance work.

## Consequences

- Parsing is independently testable, but DOM changes require JavaScript maintenance.
- Durable checkpoints, backpressure and replay handling add complexity.
- Use structured batches with byte limits. Chrome's 1 MiB native-message limit applies to the
  host-to-Chrome direction; it is not a general reason that raw HTML cannot travel Chrome-to-host.
- Navigation destroys content-script memory; this is a normal lifecycle, not an exceptional error.
- A current tool access denial is not proof of platform anti-bot behavior. Do not use a custom
  extension to bypass that denial; use permitted samples or user-provided files.

## References

[Chrome Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
and [service worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).
