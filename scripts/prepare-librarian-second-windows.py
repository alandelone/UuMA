"""Prepare a second Windows collector; server enrollment and scheduling are separate.

Run from the copied bundle with Python 3.12 or 3.13. This never copies the first
workstation's SSH or recovery private keys, and it does not contact the server.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, help="Existing trusted SSH host name or alias")
    parser.add_argument("--device", default="workstation-2")
    args = parser.parse_args()
    if os.name != "nt" or sys.version_info[:2] not in {(3, 12), (3, 13)}:
        raise SystemExit("Windows with Python 3.12 or 3.13 is required")
    if not re.fullmatch(r"workstation-[a-z0-9][a-z0-9-]{0,39}", args.device):
        raise SystemExit("Invalid device identity")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,253}", args.server):
        raise SystemExit("Invalid SSH host or alias")
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / "bundle-manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        file = (bundle / name).resolve(strict=True)
        if not file.is_relative_to(bundle) or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise SystemExit("Bundle integrity verification failed")
    device = Path(os.environ["LOCALAPPDATA"]) / "UuMA" / "Librarian" / "devices" / args.device
    device.mkdir(parents=True, exist_ok=False)
    sid = next(csv.reader(io.StringIO(subprocess.check_output(
        ["whoami", "/user", "/fo", "csv", "/nh"], text=True
    ))))[1]

    def private(path: Path, directory: bool = False) -> None:
        access = "(OI)(CI)F" if directory else "F"
        subprocess.run(["icacls", str(path), "/inheritance:r", "/remove:g",
                        "*S-1-5-32-544", "*S-1-3-4", "/grant:r",
                        f"*{sid}:{access}", f"*S-1-5-18:{access}"],
                       check=True, stdout=subprocess.DEVNULL)

    private(device, True)
    key = device / "id_ed25519"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    private(key)
    subprocess.run(["ssh-keygen", "-y", "-f", str(key)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, "-m", "venv", str(device / "venv")], check=True)
    python = device / "venv" / "Scripts" / "python.exe"
    subprocess.run([str(python), "-m", "pip", "install", "cryptography==50.0.1",
                    "cffi==2.1.1", "pycparser==3.0", "tzdata==2026.5"], check=True)
    shutil.copytree(bundle / "src", device / "src")
    shutil.copyfile(bundle / "recovery-public.pem", device / "recovery-public.pem")
    (device / "queue").mkdir()
    (device / "status").mkdir()
    home = Path.home()
    sources = [
        ("codex-state", "sqlite", home / ".codex/state_5.sqlite"),
        ("codex-attachments", "tree", home / ".codex/attachments"),
        ("codex-archived", "tree", home / ".codex/archived_sessions"),
        ("codex-sessions", "tree", home / ".codex/sessions"),
        ("antigravity-backups", "tree", home / "AppData/Roaming/Antigravity/Backups"),
        ("antigravity-user", "tree", home / "AppData/Roaming/Antigravity/User"),
        ("antigravity-logs", "tree", home / "AppData/Roaming/Antigravity/logs"),
        ("antigravity-core", "tree", home / ".gemini/antigravity"),
        ("chatgpt-localcache", "tree", home / "AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache"),
        ("codex-app-local", "tree", home / "AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/Codex"),
        ("codex-app-openai", "tree", home / "AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/OpenAI"),
        ("codex-app-roaming", "tree", home / "AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Roaming/Codex"),
    ]
    config = {"schema_version": 1, "queue": str(device / "queue"), "device": args.device,
              "public_key": str(device / "recovery-public.pem"),
              "public_fingerprint": manifest["public_fingerprint"], "host": args.server,
              "ssh_identity": str(key), "status_directory": str(device / "status"),
              "transfer_sessions": True,
              "sources": [{"source_id": n, "kind": k, "path": str(p)}
                          for n, k, p in sources if p.exists()]}
    (device / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (device / "run.py").write_text(
        "import runpy,sys\nfrom pathlib import Path\n"
        "sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))\n"
        "runpy.run_module('uuma.librarian_workstation_cli',run_name='__main__')\n",
        encoding="utf-8",
    )
    (device / "run.cmd").write_text(
        '@"%~dp0venv\\Scripts\\python.exe" -I -B "%~dp0run.py" --config "%~dp0config.json"\n',
        encoding="utf-8",
    )
    request = {"device": args.device, "public_ssh_key": key.with_suffix(".pub").read_text().strip(),
               "source_ids": [x["source_id"] for x in config["sources"]],
               "missing_source_ids": [n for n, _, p in sources if not p.exists()]}
    request_path = device / "enrollment-request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    print(json.dumps({"device_directory": str(device), "enrollment_request": str(request_path),
                      "enrollment_request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
                      "missing_source_ids": request["missing_source_ids"],
                      "server_enrollment": "PENDING", "schedule": "NOT_INSTALLED"}))


if __name__ == "__main__":
    main()
