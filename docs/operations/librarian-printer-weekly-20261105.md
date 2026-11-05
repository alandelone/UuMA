# Librarian weekly Klipper printer.cfg backup

Deployed on 2026-11-05, Asia/Kuala_Lumpur. The user requested weekly preservation
of the two printers' `printer.cfg` files. Sunday 00:00 Malaysia time was selected
as the weekly schedule and disclosed during implementation.

## Sources and schedule

| Printer | Read endpoint | Recovery source |
| --- | --- | --- |
| BTTCB1 | `https://bttcb1.95963210.xyz/server/files/config/printer.cfg` | `printer-bttcb1-config` |
| VCore | `https://vcore.95963210.xyz/server/files/config/printer.cfg` | `printer-vcore-config` |

The endpoints returned HTTP 200 and Klipper configuration text during deployment.
Both Moonraker instances reported `ready`. The collector performs bounded HTTPS
GET requests, rejects redirects, HTML login pages, oversized responses and content
without a supported Klipper section. It saves the original downloaded bytes.

The server user timer `uuma-librarian-printer-weekly.timer` is enabled and active.
Its calendar is `Sun *-*-* 00:00:00 Asia/Kuala_Lumpur`, with `Persistent=true` to run
after a missed scheduled activation when the server becomes available. The next
activation observed after installation is **2026-11-08 00:00 UTC+8**.

## Storage and history

The collector runs on `alandelone-server-001` through
`uuma-librarian-printer-weekly.service`. It keeps dated private snapshots under
`~/.local/share/uuma/production/librarian/printer-weekly/snapshots/<source>/<date>/`.
Each snapshot contains `printer.cfg` and `source.json`, which records the endpoint,
actual fetch time, byte count and plaintext SHA-256. A repeated run on the same date
reuses the original validated snapshot. Later dates retain separate versions.

Existing Librarian encryption and manifest intake routines deliver these snapshots
to the server recovery intake using the existing public recovery key. The existing
NAS publisher then writes them to
`/mnt/nas/backups/librarian/v1/recovery/server/<source>/<date>/`.

The weekly job has its own queue, snapshot store, status directory and execution
lock. It reports source failures independently and exits nonzero when collection
or intake delivery remains incomplete. Systemd journal and private JSON receipts
record the result. Daily agent collection continues on its existing schedule.

The requested capture scope is the two `printer.cfg` files and their provenance.
Included configuration files referenced from those files require their own source
coverage if later added to the user's scope. Semantic MCP publication remains a
separate item in the overall Librarian work plan.

## Initial execution evidence

The initial capture ran on 2026-11-05, ahead of the first weekly trigger.

| Source | Config bytes | Config SHA-256 | Capture and NAS result |
| --- | ---: | --- | --- |
| BTTCB1 | 16,894 | `111b472944c3e9827da23f39aa49774c92898e094799675031faf8e9265c2397` | COMPLETE, DELIVERED, NAS hashes verified |
| VCore | 27,196 | `fc95b3f105290f65567d0be010a4b098e65ddb75d9e84e271d76eb24f53c740b` | COMPLETE, DELIVERED, NAS hashes verified |

Both initial batches contain two objects, the original configuration and its
provenance JSON. Readback checked every corresponding NAS object size and SHA-256,
as well as the two immutable manifests and publication ledger entries.

Both real NAS snapshots were then downloaded as ciphertext and decrypted in local
temporary directories using the existing Windows user's DPAPI-protected recovery
key. The recovered `printer.cfg` files matched their provenance byte counts and
plaintext SHA-256 values shown above. The native verification task exited 0 and
temporary plaintext was removed. Its receipt is
`.uuma-local/librarian-implementation-20261029/native-printer-restore-20261105.json`.
This verification uses the existing user key. Independent offline key custody
continues under the broader Librarian acceptance plan.

The server's deployed release test suite passed **3/3**, including actual fixture
encryption, intake, two-date history and decryption. The related Windows suite
passed **22 tests**, with one POSIX-only intake test skipped. Affected-file Ruff
checks passed.

## Published runtime and rollback

Source module is `src/uuma/librarian_printer_weekly.py`. Regression tests are in
`tests/test_librarian_printer_weekly.py`.

The immutable production release is
`~/.local/share/uuma/production/librarian/releases/printer-weekly-199d564f2707f28fbd77c9b1d3b8c051565c8b10bed3615d2f866f7e8d763255/`.
It retains `preview.json`, `receipt.json`, the pinned source/configuration manifest,
the service/timer definitions and `qa-result.log`. The launcher validates pinned
source, configuration and interpreter hashes before collection.

The first capture receipt is
`~/.local/share/uuma/production/librarian/printer-weekly/status/run-2426e592bbd24b3fa8521c6b22fbb7c6.json`.
Private workstation verification helpers and results are under
`.uuma-local/librarian-implementation-20261029/`, including
`deploy-printer-weekly-20261105.log` and `verify-printer-nas-20261105.log`.

To retire this schedule, disable and stop only
`uuma-librarian-printer-weekly.timer`. Preserve the dated source snapshots, queue,
intake records and NAS history. The deployment adds this pair of units and does
not require a shared Hermes gateway restart or database schema migration.
