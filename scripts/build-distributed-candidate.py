"""Package a review candidate without credentials, runtime databases, or Git metadata."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    files = []
    suffixes = {".py", ".md", ".toml", ".json", ".yaml", ".yml", ".ps1", ".html", ".js", ".css"}
    for directory in ["src", "profiles", "integrations/hermes", "deploy/distributed"]:
        for path in (root / directory).rglob("*"):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix in suffixes
                and not any(part in {"__pycache__", "node_modules", ".git"} for part in path.parts)
            ):
                files.append(path)
    files.extend(root / name for name in ["README.md", "pyproject.toml", "deploy/components.json"])
    files.append(root / "scripts" / "bind-server-provider-pool.py")
    files.extend(
        root / "tests" / name
        for name in [
            "test_distributed_control.py",
            "test_node_transport.py",
            "test_component_releases.py",
            "test_a2a_protocol.py",
            "test_remote_mcp_auth.py",
            "test_runtime_registry.py",
            "test_node_bootstrap.py",
            "test_source_snapshot.py",
            "test_release_backend.py",
            "test_profile_migration.py",
            "test_remote_desktop_bridge.py",
            "test_assigned_runtime_guard.py",
            "test_uuma_control_guard.py",
            "test_workstation_node.py",
            "test_provider_pool.py",
            "test_provider_pool_binding.py",
            "test_provider_pool_web.py",
            "test_provider_oauth.py",
        ]
    )
    material = {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(set(files))}
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in material.items()}
    source_id = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    output = root / ".uuma-local" / "distributed-candidates"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"candidate-{source_id}.zip"
    receipt = {
        "schema_version": 1,
        "source_id": source_id,
        "production_ready": False,
        "kind": "working-tree review candidate, not an approved Git release",
        "base_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "files": hashes,
    }
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, body in material.items():
            bundle.writestr(name, body)
        bundle.writestr("source-receipt.json", json.dumps(receipt, indent=2))
    with archive.open("rb") as handle:
        archive_digest = hashlib.file_digest(handle, "sha256").hexdigest()
    report = {
        "archive": str(archive),
        "sha256": archive_digest,
        "source_id": source_id,
        "file_count": len(material),
        "production_ready": False,
    }
    (output / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
