"""Build a credential-free, content-addressed server account-pool review candidate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    files = {"source/uuma/__init__.py": b""}
    for name in ["provider_pool", "provider_pool_web", "provider_oauth", "provider_guard"]:
        body = (root / "src" / "uuma" / (name + ".py")).read_bytes()
        files[f"source/uuma/{name}.py"] = body
        files[f"source/uuma_{name}.py"] = body
    page = (root / "src/uuma/provider_pool.html").read_bytes()
    files.update({"source/provider_pool.html": page, "source/uuma/provider_pool.html": page})
    for relative in [
        "scripts/bind-server-provider-pool.py", "scripts/build-provider-pool-candidate.py",
        "tests/test_provider_pool.py", "tests/test_provider_pool_binding.py",
        "tests/test_provider_pool_web.py", "tests/test_provider_oauth.py",
        "tests/test_provider_pool_supervision.py",
    ]:
        files[relative] = (root / relative).read_bytes()
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
    release_id = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    directory = root / ".uuma-local" / "provider-pool-candidates" / release_id
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "candidate.zip"
    manifest = {
        "schema_version": 1, "release_id": release_id, "files": hashes,
        "production_active": False, "kind": "working-tree review candidate",
        "base_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
        ).strip(),
    }
    if not archive.exists():
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
            for name, body in files.items():
                bundle.writestr(name, body)
            bundle.writestr("manifest.json", json.dumps(manifest, indent=2))
    report = {
        **manifest, "archive": str(archive),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    (directory / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (root / ".uuma-local/provider-pool-candidates/latest.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({"release_id": release_id, "archive": str(archive)}))


if __name__ == "__main__":
    main()
