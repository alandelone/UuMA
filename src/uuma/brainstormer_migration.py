"""Read-only, explicit-file Brainstormer snapshots; never starts a receiver."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Iterable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROFILE_FILES = ("SOUL.md", "profile.yaml", "state.db", "projects.db", "cron/jobs.json",
                 "cron/executions.db", "platforms/telegram.json", "memories/MEMORY.md",
                 "memories/USER.md")
PROFILE_TREES = {"skills": {".md", ".py", ".json", ".yaml", ".yml", ".txt"},
                 "plugins": {".md", ".py", ".json", ".yaml", ".yml", ".txt"},
                 "scripts": {".py", ".ps1", ".sh", ".json", ".yaml", ".yml"},
                 "sessions": {".json", ".jsonl"}, "memories": {".md"}}
_SECRET = re.compile(
    r"(^|[._-])(auth|oauth|credential[s]?|secret[s]?|token[s]?|api[_-]?key)([._-]|$)",
    re.IGNORECASE,
)


def _source(root: Path, relative: str) -> Path:
    part = Path(relative)
    if part.is_absolute() or not part.parts or ".." in part.parts:
        raise ValueError("Snapshot paths must be relative and stay inside their source root")
    if (any(p.startswith(".env") or _SECRET.search(p) for p in part.parts)
            or part.as_posix() == "config.yaml"):
        raise ValueError("Credential paths cannot be included in a migration snapshot")
    path = root / part
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
        raise ValueError("Snapshot paths cannot traverse symbolic links")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Snapshot path escapes its source root")
    return path


def snapshot_file_list(profile_root: Path, data_root: Path) -> dict[str, list[str]]:
    """Propose a bounded inventory for review, excluding config and credential files.

    config.yaml must be regenerated for Linux separately, rather than copied with its
    embedded endpoints or credentials. Debug request dumps and caches are not sessions.
    Additional reviewed files can be passed explicitly to ``create_snapshot``.
    """
    profile_root, data_root = profile_root.resolve(), data_root.resolve()
    profile = {name for name in PROFILE_FILES if (profile_root / name).is_file()}
    for directory, suffixes in PROFILE_TREES.items():
        for path in (profile_root / directory).rglob("*"):
            relative = path.relative_to(profile_root).as_posix()
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if path.name.startswith("request_dump_"):
                continue
            try:
                _source(profile_root, relative)
            except ValueError:
                continue
            profile.add(relative)
    domain = data_root / "brainstormer"
    data = {p.relative_to(data_root).as_posix()
            for pattern in ("projects/*/state.json", "proposals/*.json")
            for p in domain.glob(pattern) if p.is_file()}
    return {"profile": sorted(profile), "data": sorted(data)}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(path: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {"main": _digest(path)}
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        wal = path.with_name(path.name + "-wal")
        result["wal"] = _digest(wal) if wal.is_file() else None
    return result


def _backup_database(source: Path, destination: Path) -> dict[str, Any]:
    deadline = time.monotonic() + 30

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("Consistent SQLite snapshot exceeded its deadline")

    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as reader:
        reader.execute("BEGIN")
        with closing(sqlite3.connect(destination)) as writer:
            reader.backup(writer, pages=256, progress=progress, sleep=0.05)
            integrity = [r[0] for r in writer.execute("PRAGMA integrity_check")]
            if integrity != ["ok"]:
                raise ValueError("Snapshot database did not pass integrity_check")
            tables = [r[0] for r in writer.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )]
            counts = {name: writer.execute(
                'SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"'
            ).fetchone()[0] for name in tables}
        reader.rollback()
    return {"integrity_check": "ok", "table_rows": counts}


def _freeze_evidence(receipt: Path, profile: Path, data: Path) -> dict[str, Any]:
    proof = json.loads(receipt.read_text(encoding="utf-8"))
    if (proof.get("all_writers_stopped") is not True
            or proof.get("source_receiver_stopped") is not True
            or Path(proof.get("profile_root", "")).resolve() != profile
            or Path(proof.get("data_root", "")).resolve() != data
            or not proof.get("verified_at")
            or not proof.get("verification_method")):
        raise ValueError("Final snapshot requires matching external writer-freeze evidence")
    return {"receipt_sha256": _digest(receipt), "verified_at": proof["verified_at"]}


def create_snapshot(*, profile_root: Path, data_root: Path, destination: Path,
                    files: dict[str, Iterable[str]], freeze_receipt: Path | None = None
                    ) -> dict[str, Any]:
    """Copy only a caller-reviewed inventory to a new directory.

    Online snapshots are candidates, never cutover backups. A final snapshot requires
    an external receipt confirming every writer and the source receiver have stopped.
    That receipt is evidence supplied by the cutover controller, not proof generated
    by this passive file copier. This function never opens the production control DB.
    """
    roots = {"profile": profile_root.resolve(), "data": data_root.resolve()}
    if any(not root.is_dir() for root in roots.values()):
        raise ValueError("Explicit existing profile and data roots are required")
    destination = destination.resolve()
    if any(destination.is_relative_to(root) or root.is_relative_to(destination)
           for root in roots.values()):
        raise ValueError("Snapshot destination must be separate from both source trees")
    if set(files) != set(roots):
        raise ValueError("Both profile and data inventories must be supplied")
    selected: list[tuple[str, str, Path]] = []
    for owner, names in files.items():
        for name in sorted(set(names)):
            source = _source(roots[owner], name)
            if not source.is_file():
                raise ValueError(f"Reviewed snapshot file is missing: {owner}/{name}")
            if owner == "data" and not Path(name).parts[0] == "brainstormer":
                raise ValueError("Only Brainstormer domain files belong in this snapshot")
            if source.suffix.lower() in {".db-wal", ".db-shm"} or name.endswith(
                ("-wal", "-shm", ".lock", ".log")
            ):
                raise ValueError("Use consistent SQLite backups, not sidecars or locks")
            selected.append((owner, name, source))
    proof = (_freeze_evidence(freeze_receipt, roots["profile"], roots["data"])
             if freeze_receipt is not None else None)
    if proof:
        required = snapshot_file_list(roots["profile"], roots["data"])
        actual = {(owner, name) for owner, name, _ in selected}
        if any((owner, name) not in actual for owner, names in required.items() for name in names):
            raise ValueError("Final snapshot inventory omits recognized runtime or domain state")
    before = {(owner, name): _fingerprint(source) for owner, name, source in selected}
    destination.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 1, "created_at": datetime.now(UTC).isoformat(),
        "status": "IN_PROGRESS", "snapshot_kind": "final" if proof else "candidate",
        "production_cutover_ready": False, "freeze_evidence": proof, "files": [],
        "source_roots": {k: str(v) for k, v in roots.items()},
        "config_requires_regeneration": True,
    }
    try:
        for owner, name, source in selected:
            target = destination / owner / name
            target.parent.mkdir(parents=True, exist_ok=True)
            metadata: dict[str, Any] = {}
            if source.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                metadata = _backup_database(source, target)
            else:
                content = source.read_bytes()
                if source.suffix.lower() == ".json":
                    json.loads(content)
                target.write_bytes(content)
            manifest["files"].append({"path": f"{owner}/{name}",
                                      "sha256": _digest(target),
                                      "bytes": target.stat().st_size, **metadata})
        changed = [f"{owner}/{name}" for owner, name, source in selected
                   if _fingerprint(source) != before[owner, name]]
        stable = not changed
        manifest["changed_source_files"] = changed
        if proof and not stable:
            raise ValueError("A frozen source changed during its final snapshot")
        manifest.update(status="COMPLETE", source_files_stable=stable,
                        production_cutover_ready=bool(proof and stable))
    except Exception:
        manifest["status"] = "FAILED"
        raise
    finally:
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return manifest
