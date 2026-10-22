"""Content-addressed engine snapshots, including local edits, excluding runtime state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

from .node_journal import digest

PRIVATE_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".uuma-local",
    "sessions", "logs", "backups", "cache", ".cache",
}
PRIVATE_NAMES = {".env", "auth.json", "tokens.json", "credentials.json"}


def snapshot(root: Path, output: Path, includes: list[str], *, engine: str) -> dict:
    root = root.resolve()
    if not includes or not engine:
        raise ValueError("An engine identity and explicit source paths are required")
    for name in includes:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or "\\" in name:
            raise ValueError("Source paths must be relative repository paths")
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    raw = subprocess.check_output([
        "git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
        "--exclude-standard", "--", *includes,
    ])
    material = {}
    for value in raw.split(b"\0"):
        if not value:
            continue
        name = value.decode("utf-8")
        relative = PurePosixPath(name)
        if (
            any(part.lower() in PRIVATE_PARTS for part in relative.parts)
            or relative.parts[0].lower() == "data"
            or relative.name.lower() in PRIVATE_NAMES
            or relative.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".wal", ".key", ".pem"}
            or name.endswith(("-wal", "-shm"))
        ):
            continue
        path = root / name
        if not path.exists():
            continue  # A local tracked deletion must remain deleted in this snapshot.
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Engine snapshots do not follow source symlinks")
        if path.is_file():
            material[name] = path.read_bytes()
    if not material:
        raise ValueError("No source files matched the explicit engine scope")
    if engine == "hermes":
        # The gateway imports packages such as tui_gateway during background
        # startup. A valid wheel install alone cannot detect an incomplete source
        # snapshot, because its editable finder can hide missing packages.
        metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        packages = metadata["tool"]["setuptools"]["packages"]["find"]["include"]
        required = {name.split(".")[0] for name in packages if "*" not in name}
        missing = sorted(name for name in required
                         if not any(p.startswith(name + "/") for p in material))
        if missing:
            raise ValueError("Hermes snapshot misses declared runtime packages: "
                             + ", ".join(missing))
    files = {name: hashlib.sha256(body).hexdigest() for name, body in sorted(material.items())}
    source_id = digest({"engine": engine, "source_commit": revision, "files": files})
    receipt = {
        "schema_version": 1, "engine": engine, "source_commit": revision,
        "source_id": source_id, "files": files, "includes": includes,
        "working_tree_edits_preserved": True, "runtime_state_included": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{engine}-{source_id}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, body in sorted(material.items()):
            bundle.writestr(name, body)
        bundle.writestr("engine-source-receipt.json", json.dumps(receipt, indent=2))
    report = {
        "engine": engine, "source_commit": revision, "source_id": source_id,
        "archive": str(archive), "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "file_count": len(files), "runtime_state_included": False,
    }
    (output / f"{engine}-{source_id}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--include", action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.root, args.output, args.include, engine=args.engine)))


if __name__ == "__main__":
    main()
