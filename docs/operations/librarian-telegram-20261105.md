# Librarian Hermes Telegram deployment

Date 2026-11-05, Asia/Kuala_Lumpur.

## User request and architecture

The user authorized implementing Librarian using the other specialists' existing
Hermes pattern and supplied the new Telegram bot credential. The current server
already had a Librarian Hermes profile, native session database, role document,
scoped identity, control guard and audit plugins. Earlier conversational statements
that the agent layer was absent were incorrect. Telegram was the missing channel.

The bot is https://t.me/uulibrarian_bot. Open it, press Start and send a normal
question. The existing owner allowlist applies. Credentials remain node-local.

Librarian runs in the existing multiplexed server Hermes gateway. It uses its own
profile and sessions and accesses the existing governed worker and read MCP.
Collectors, encryption, NAS publication and restoration remain distinct services.

## Applied configuration

- Added the profile-local Telegram credential and copied the existing Forge owner
  allowlist, containing one authorized user.
- Enabled the Telegram platform and explicitly restricted its toolsets to
  `uuma-worker` and `uuma-librarian-read`, matching CLI and API scope.
- Reused Forge's live model/provider configuration, `gemini-3.8-flash` through
  `antigravity-oauth`. Set Librarian's maximum turn count to 40.
- Retained existing scoped identity, MCP commands, plugins, role and databases.
- Updated maintained `tools.yaml` and the runtime contract. Corrected the obsolete
  NAS pause instruction to reflect the user's replaced disks and resumed publisher.

## Release and restart evidence

Private server release directory

```text
/home/alandelone/.local/share/uuma/operations/librarian-telegram-20261105T083616Z
```

The directory holds a sanitized preview, previous profile configuration and
credential file with private permissions, connection receipt and model verification.

Configuration SHA-256 before
`52482b12cb7d6ed31caa6426514f7dd24d340486061aa8341362bdbfe84ceeda`.

Configuration SHA-256 after
`b1279bbc64eaf5e763693e260e20cfb5cf5d562cc595575793e7c7303247724c`.

Used the engine's external drain marker, waited for draining state with zero
active agents, checked unchanged source hashes, applied the two profile files and
restarted the existing gateway. Cleared the maintenance marker in a finally block.
The shared restart affected Brainstormer, Forge, Honc, Librarian, Wisdom and Yonc.
Gateway PID changed from 103521 to 181595. Final state was running with all six
Telegram adapters and the API adapter connected.

The bot identity matched `uulibrarian_bot`. No webhook was registered. The adapter
reported healthy polling and successful command-menu registration.

## Actual model verification

Submitted a Chinese read-only query through the authenticated Librarian profile API.
Run `run_21a34b9315724835a863e5c0e4495f13` completed successfully with runtime provider
`antigravity-oauth` and model `gemini-3.8-flash`. Its answer identified Librarian and
cited snapshot `librarian-index-20261103033751`, one Brainstormer record and 58 Yonc
records, with partial coverage and recorded source timestamps.

This establishes a real model response through the profile API. Telegram polling
and a successful model response are separate checks. A user-originated Telegram
request was subsequently observed at 17:11:54 Malaysia. The owner sent
`你是谁？请查一下备份目录` after Start. Native Telegram session
`20261105_171154_d611e92d` retained the request, actual
`librarian_list_sources` result, successful `submit_result` receipt and the final
Chinese answer. At 17:12:55 the gateway logged a 682-character response ready and
the Telegram adapter sending that response. Processing took about 60 seconds.
These are server-side reception, execution and send-path observations. The user's
client display has not been independently inspected.

## Remaining coverage and rollback

This deployment adds the direct communication channel. Broader backup acceptance
and readable catalog coverage retain their existing partial statuses. Independent
offline key custody remains unfinished. The second Windows installation stays deferred.

Rollback requires a fresh guarded drain and inspection of current hashes. Restore
only this release's previous profile configuration and environment file, then restart
the shared gateway at an idle boundary. Preserve all native session and domain data.
No mission gate was approved and no Git commit or push was performed.
