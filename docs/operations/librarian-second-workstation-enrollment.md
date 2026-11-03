# Librarian second Windows workstation enrollment

Status: the preparation bundle and server enrollment helper have been tested with
isolated data. No real second-workstation key has been enrolled yet. A complete
deployment also requires independent recovery-key custody, a working collector
schedule, source coverage checks, and a real restore test.

## Prepare on the second Windows machine

Copy and extract the full `librarian-second-windows-preparation-v8-20261030.zip`
bundle. Establish the server SSH host key through an independent trusted channel
and configure the `ubuntu-server` alias. Install Windows OpenSSH and Python 3.12
or 3.13. The preparation uses the internet to install pinned Python packages.

In the extracted bundle directory, run:

```powershell
py -3.12 prepare.py --server ubuntu-server --device workstation-2
```

The output identifies the newly generated device folder, a public
`enrollment-request.json`, its SHA-256, and any missing source IDs. The request
contains the new public SSH key and requested source IDs, not the private key.
Keep the private key on this Windows machine. Verify the request SHA-256 using an
independent trusted channel before transferring the request to the server; a
digest transmitted alongside an untrusted request does not authenticate it.

## Enroll on the server after checking the request

Coordinate a single writer for the Librarian server policy and `authorized_keys`.
Do not edit these files concurrently: the helper detects some changes but its
advisory lock cannot prevent writes by programs that ignore it. Put the checked
request in an owner-controlled server location and supply its exact server path and
the independently compared SHA-256 as arguments:

```bash
/usr/bin/python3.12 -I -B \
  /home/alandelone/.local/share/uuma/production/librarian/releases/enrollment-session-0660363da4f144cf8869b1e4ffc436d0/launch.py \
  --request /absolute/server/path/enrollment-request.json \
  --request-sha256 CHECKED_SHA256
```

The helper checks the request digest, fixed receiver release, device identity and
the requested source IDs against the existing workstation grant. It adds one
forced-command, `restrict`-scoped SSH key, retaining prior key bytes. It saves
private pre-change snapshots and an intent receipt before publication, followed
by a completion receipt after readback. If interrupted or a concurrent change is
detected, do not rerun blindly: inspect the intent and retained snapshots. The
policy might contain an inert device grant without a corresponding SSH key.
The v8 bundle requests negotiated session transfer; this enrollment release pins
the compatible `intake-session-39725dfe81aa466a9ac6a142902665f7` receiver. The
previous enrollment release pins a legacy receiver and must not be used with v8.
The new enrollment runtime passed its integrity check and an isolated fixture
enrollment; no actual second-device registration has taken place.

## Verify and finish

After enrollment, `run.cmd` in the created device folder can perform an on-demand
capture. Inspect its private status receipts and verify the server intake and NAS
publication; a successful installation or SSH connection alone proves neither.
The program reports only registered, locally present sources. Review missing
sources, project roots, and cloud-only conversations separately. Do not register
an unattended schedule until the accepted independent offline recovery-key
custody is established. No schedule is installed by this preparation bundle.
