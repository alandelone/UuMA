# Forge workspace on NAS

## Active ownership

Windows uses `Z:/Hardware-Lab-Workspace`; Linux uses `/mnt/nas/Hardware-Lab-Workspace`.
These are the same directory on `\\192.168.55.2\NAS`, including `.git`.
`deploy/forge-workspace.json` records the host paths used by deployment and Observatory.
Only one host may perform Git writes or modify the workspace at a time.

The original `C:/Users/Alandelone/CodeSpace_Local/Hardware-Lab-Workspace` is retained as a
rollback copy. Do not continue development in that copy. After new NAS writes, switching
back requires reconciling them first; do not copy the old tree over the active workspace.
Forge's terminal, command plugin and project registry now use Z. The Forge Agent itself
still runs on the workstation pending its separate domain and eSchematic cutover.

## Git and availability

The initial copy verified 684 files, preserved the complete repository and passed
`git fsck --full`. NAS HEAD is `17bc7e9901b9f4822af1e23ef3bdb4a443e41115`, based on
`fc383b9bea317d4db66c5135be822f8649fa113b`. No push was performed.
The one follow-up source change resolves the legacy bridge's paths from its workspace
and requires a token from the environment; that legacy receiver was never started.
Git uses `core.autocrlf=true` and `core.filemode=false` to preserve the existing checkout.

On Windows, Z must be available in the account/session running Forge. If NAS is
unavailable, wait for the share to return. Do not silently create a new local workspace.
The server accesses its local NAS filesystem without a second Git clone or SMB login.
Workspace commits are saved manually; changing source does not deploy Agent services.
Private copy, configuration backup and verification receipts are in
`.uuma-local/forge-nas-cutover-20261022/`.

Windows Git trusts only this exact NAS repository through an explicit safe.directory
entry, because SMB reports the server owner SID. No wildcard trust was added.
A repeat full Git check over SMB exceeded30seconds; the same check passed locally
on the server against the identical NAS directory, whose working tree is clean.
