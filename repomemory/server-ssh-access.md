# Server SSH access (non-secret)

Verified 2026-10-22 that `ssh ubuntu-server` opens an authenticated session to `alandelone-server-001` as `alandelone` on port 22. The alias is configured in `C:\Users\Alandelone\.ssh\config` and uses the dedicated private-key file `C:\Users\Alandelone\.ssh\id_ed25519_ubuntu`. Keep the private-key contents and any account password out of this repository and chat logs.

The user-provided addresses are `192.168.55.2` (the address used for the verified connection), `10.16.168.170` (same-LAN address), and `100.96.79.61` (Tailscale address). Only `192.168.55.2` was independently verified in this session. The observed host-key fingerprint for that address was `SHA256:B1RmMj444Gl2Ia/kdVqApV3pOpveK1udjZNpLyUK2GQ`, matching an existing `known_hosts` entry. Continue using normal host-key validation.
