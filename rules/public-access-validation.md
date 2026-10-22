# Published browser application access validation

Use isolated fake credentials and upstreams for unit tests. Real deployment validation is
read-only and separately recorded; never send chat, inference, scientific generation or save
requests to production as a test.

Preserve native navigation: Live Agent on port 5173 returns HTTP 302 from `/` to `/live/`.
Require that exact redirect and then HTTP 200 for `/live/`, rather than requiring root 200.
Scholar's actual read endpoint is `/api/catalog/research-overview` in `rstv4/catalog_web.py`;
`/api/research/overview` is not an endpoint. Keep the original preflight diagnostics.

Starlette TestClient relative WebSocket URLs default to `ws://testserver`. To validate a
Secure, host-bound production-format cookie, use the explicit fixture `wss://` hostname.
Keep anonymous, cross-origin, binary/text round-trip and negotiated-subprotocol assertions.

Verify the loopback ingress before changing tunnel routes. Preserve the Hermes HTTP Host
override `localhost:9119`; proxy transport must keep the native host checks working. Capture
all routes before/after and require every unrelated route and application listener to remain.
After publication verify anonymous denial, invalid-token denial, credential-stripping redirect,
session navigation, real assets and read APIs. Never log credential-bearing request URLs.
