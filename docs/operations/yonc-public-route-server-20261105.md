# Yonc public route and monitor ownership

Updated: 2026-11-05. Public entry: <https://yonc.95963210.xyz/>.

## Current route

The server Cloudflare connector now publishes `yonc.95963210.xyz` directly to
`http://127.0.0.1:8766` on the server. Its received configuration version 10 includes
this route. The Graph service remains `uuma-yonc-graph.service`, owned by the server.

The temporary Windows SSH forward created during the earlier HTTP 502 recovery was
stopped after confirming the new server route. Public Graph health still returned HTTP
200 after Windows port 8766 had no listener. Do not restore a workstation Graph service
or recreate a workstation database to repair this public entry.

## Dual-node service monitor

The dashboard at <https://dash.95963210.xyz/> runs as `cluster-dashboard.service`.
Its configuration is `/home/alandelone/services/dashboard/services.yaml` on the server.
Only the Yonc entry was updated:

| Setting | Current value |
| --- | --- |
| Display name | Graph App (Yonc) |
| Host node | Ubuntu Server |
| Local endpoint | `127.0.0.1:8766` |
| Local probe | HTTP GET `/api/v2/health` |
| Public endpoint | `https://yonc.95963210.xyz` |

The existing internal service ID `win-graph-app` was retained for incident continuity;
its prefix is historical and does not determine the current host. All other 24 service
definitions were preserved. The prober reloads this file on each cycle, so no dashboard
or Agent restart was needed. Existing incident records were retained.

Verified the live dashboard API and browser row: Yonc is on the Ubuntu node, with
`local_up=true`, `public_up=true`, green status and an empty current error. The Graph
remained at version 128 with 691 nodes and its existing database identity.

## Receipt and rollback

- Server backup: `/home/alandelone/services/dashboard/backups/yonc-server-monitor-20261105T044428394150Z`.
- Configuration SHA-256 before: `9c3c3bc04753e863ffaeb90ee2475546e656b540cb6039ce24bb8a4603f80e04`.
- Configuration SHA-256 after: `80741b930147c538283933d48c993f830af2a82b198456853d8360894ea488f5`.
- Private operation receipts: `.uuma-local/yonc-site-error-20261105/` in the UuMA workspace.

For a later rollback, first inspect the current configuration for subsequent edits.
Restore only the reviewed Yonc entry if needed; do not overwrite newer unrelated
configuration or restore an old monitoring database. Reverting the monitor entry does
not revert Cloudflare routing. A workstation forward is not part of the current public
route. This change does not certify unrelated services or advance the mission gate.
