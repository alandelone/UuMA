# Private access links for Live, Hermes and Scholar

Deployed 2026-10-21. These three public domains now require the existing Observatory
credential, using the same `/?auth=<existing Observatory token>` link format as AGTS:

- `https://live.95963210.xyz/`
- `https://hermes.95963210.xyz/`
- `https://scholar.95963210.xyz/`
- `https://bttcb1.95963210.xyz/`
- `https://vcore.95963210.xyz/`
- `https://3dp.95963210.xyz/`

The first valid link sets a six-month (180-day), Secure, HttpOnly, SameSite=Strict session cookie
restricted to that individual host, then redirects to the same path with `auth` removed.
Other query parameters and deep links survive. Users can also enter the existing token
on the access page. Invalid tokens and anonymous HTTP requests are rejected with 401;
anonymous WebSocket upgrades are rejected. AGTS also issues a six-month (180-day)
HttpOnly browser cookie from its existing server. All four share the lifetime constant
in `src/uuma/browser_sessions.py`. Reopen each private access link once to replace any
previous eight-hour browser cookie; existing access links and tokens still work.

The cookie contains a host-bound HMAC and expiry, not the access token. The gateway reads
`%LOCALAPPDATA%\UuMA\observatory.token`; changing that credential invalidates its sessions.
Do not copy the credential into source, documentation, process arguments, or logs.
Request access logging is disabled, and responses specify no-store and no-referrer.

## Runtime and routes

`python -m uuma.public_access` listens only on `127.0.0.1:8791`. It proxies authenticated
HTTP bodies/responses without buffering, SSE and WebSocket text/binary traffic. It preserves
application credentials and cookies while withholding its own session cookie from upstream.
Explicit cross-origin mutations and WebSocket upgrades are rejected.

The `agent-local` Cloudflare tunnel's existing three hostnames now point to 8791. The
gateway sends Live to 5173, Hermes to 9119, and Scholar to 8875. Hermes retains its existing
Cloudflare HTTP Host Header override `localhost:9119` and native upstream host validation.
Phoenix, Yonc, AGTS, Wisdom Graph, RDP, and their route order/settings are unchanged.
The six-month lifetime update refreshed only the public access gateway and Observatory
HTTP listener. Live, the Hermes dashboard, Scholar, research workers and the Hermes
gateway retain their original processes. The tunnel routes did not change for this update.

The hidden `UuMA Public Access` Windows task starts 15 seconds after user login. Its scoped
supervisor uses a mutex, verifies the listener owner, and retries child exits after five
seconds. Task Scheduler retries supervisor failure three times, one minute apart. It does
not terminate processes occupying the port. An actual OS login/crash-recovery drill was
not performed during this deployment.

Install optional runtime dependencies with `pip install -e ".[public-access]"`, then run
`scripts/install-public-access-service.ps1` once. The installer refuses to overwrite an
existing task. Runtime and logs live under `.uuma-local/windows-service-logs/`.

## Validation and rollback

Fifteen isolated ingress tests and ten Observatory tests cover access denial, valid/invalid links,
redirect query preservation, signed host-bound sessions, expiry/tampering/rotation/missing
credential, body and SSE forwarding, native cookies, cross-origin mutations, Hermes' Host
override, real local WebSocket text/binary/subprotocol relay, all four 180-day cookie
lifetimes and signed-session validity beyond eight hours through the exact expiry boundary.
All 25 tests and Ruff pass. Live HTTPS checks confirm all four sites issue
`Max-Age=15552000`, still reject anonymous/bad-token requests, and load after login.
Lifetime-update evidence: `.uuma-local/access-six-months-20261021/`.

Separate read-only deployment checks verify all three public domains return 401 anonymously,
303 for valid login, and 200 for authenticated pages; Live JavaScript, Hermes status and
Scholar research overview also pass. Chrome renders all three and Live reaches READY.
No test message, microphone operation, scientific generation or research mutation was sent.
Evidence and before/after route/listener records: `.uuma-local/public-access-20261021/`.
Earlier fixture/preflight context failures are retained and explained in
`rules/public-access-validation.md`.

For rollback, the preserved route origins are Live `http://127.0.0.1:5173`, Hermes
`http://127.0.0.1:9119` with `httpHostHeader=localhost:9119`, and Scholar
`http://127.0.0.1:8875`. Restoring those origins removes this public authentication gate;
do not stop the gateway while the tunnel still points at 8791. Never change other routes,
reset workspaces, or restart agent/research processes to roll back this ingress.

The global mission remains `verification/pending_review`; this deployment does not approve
the research or mission gates.
