"""Deliver fixed submission packages without exposing local filesystem paths."""
from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any

from .database import transaction
from .service import NotFoundError, RSTV4Error


class PackageUnavailableError(RSTV4Error):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_inventory(directory: Path) -> dict[str, dict[str, Any]]:
    """Capture digests at packaging time; never backfill an old package's proof."""
    result = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            raw = path.read_bytes()
            result[path.name] = {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    return result


def _safe_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", name))


def _directory(root: Path, row: dict[str, Any]) -> Path:
    root = root.resolve()
    directory = (root / row["manuscript_id"] / "packages" / row["job_id"]).resolve()
    if root not in directory.parents:
        raise PackageUnavailableError("The stored package location is unavailable")
    return directory


def _names(manifest: dict[str, Any]) -> list[str]:
    names = manifest.get("files")
    if not isinstance(names, list) or any(not isinstance(n, str) or not _safe_name(n) for n in names):
        raise PackageUnavailableError("The stored package file list is invalid")
    names = sorted(set(names) | {"manifest.json"})
    inventory = manifest.get("file_integrity")
    if inventory is not None and (
        not isinstance(inventory, dict) or set(inventory) != set(names) - {"manifest.json"}
        or any(not isinstance(item, dict) or type(item.get("size_bytes")) is not int
               or item["size_bytes"] < 0 or not isinstance(item.get("sha256"), str)
               or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) for item in inventory.values())
    ):
        raise PackageUnavailableError("The stored package integrity inventory is invalid")
    return names


def _records(db_path: Path, manuscript_id: str, package_id: str | None = None) -> list[dict[str, Any]]:
    with transaction(db_path) as conn:
        if conn.execute("SELECT 1 FROM studio_documents WHERE manuscript_id=?", (manuscript_id,)).fetchone() is None:
            raise NotFoundError("Unknown Studio manuscript")
        rows = conn.execute(
            """SELECT p.*, r.round_number, j.status AS job_status, j.job_kind,
                      j.input_revision
               FROM studio_submission_packages p JOIN studio_jobs j ON p.job_id=j.job_id
               LEFT JOIN review_rounds r ON p.review_round_id=r.review_round_id
               WHERE p.manuscript_id=? AND j.manuscript_id=p.manuscript_id
                 AND (? IS NULL OR p.package_id=?) ORDER BY p.created_at DESC, p.package_id""",
            (manuscript_id, package_id, package_id),
        ).fetchall()
        values = [dict(row) for row in rows]
        for row in values:
            row["manifest"] = json.loads(row.pop("manifest_json"))
            version = conn.execute(
                "SELECT version FROM manuscript_versions WHERE manuscript_id=? AND manuscript_version_id=?",
                (manuscript_id, row["manifest"].get("generated_version_id")),
            ).fetchone()
            row["generated_version_number"] = version["version"] if version else None
    if package_id and not values:
        raise NotFoundError("The submission package does not belong to this manuscript")
    return values


def list_packages(db_path: Path, root: Path, manuscript_id: str) -> list[dict[str, Any]]:
    values = []
    for row in _records(db_path, manuscript_id):
        if row["job_status"] != "SUCCEEDED" or row["job_kind"] != "SUBMISSION_PACKAGE":
            continue
        manifest = row["manifest"]
        directory = _directory(root, row)
        files = []
        for name in _names(manifest):
            path = (directory / name).resolve()
            available = path.parent == directory and path.is_file()
            recorded = (manifest.get("file_integrity") or {}).get(name)
            files.append({"name": name, "available": available,
                          "size_bytes": recorded.get("size_bytes") if recorded else None,
                          "sha256": recorded.get("sha256") if recorded else None})
        values.append({"package_id": row["package_id"], "manuscript_id": manuscript_id,
                       "job_id": row["job_id"], "created_at": row["created_at"],
                       "input_revision": row["input_revision"],
                       "generated_version_id": manifest.get("generated_version_id"),
                       "generated_version_number": row["generated_version_number"],
                       "review_round_id": row["review_round_id"], "round_number": row["round_number"],
                       "baseline_manuscript_version_id": manifest.get("baseline_manuscript_version_id"),
                       "unresolved_comment_ids": manifest.get("unresolved_comment_ids", []),
                       "location_summary": manifest.get("location_summary"), "files": files,
                       "integrity_status": "RECORDED_AT_PACKAGING" if "file_integrity" in manifest
                       else "LEGACY_ORIGINAL_DIGEST_UNAVAILABLE"})
    return values


def package_content(db_path: Path, root: Path, manuscript_id: str, package_id: str,
                    filename: str | None = None) -> tuple[bytes, str, str]:
    row = _records(db_path, manuscript_id, package_id)[0]
    if row["job_status"] != "SUCCEEDED" or row["job_kind"] != "SUBMISSION_PACKAGE":
        raise PackageUnavailableError("The submission package is not complete")
    manifest = row["manifest"]
    names = _names(manifest)
    if filename is not None and filename not in names:
        raise NotFoundError("Unknown file in this submission package")
    directory = _directory(root, row)
    contents = {}
    for name in names:
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise PackageUnavailableError("A fixed package file is missing; keep the original package and create a new one")
        raw = path.read_bytes()
        if name == "manifest.json":
            if raw != _canonical(manifest).encode("utf-8"):
                raise PackageUnavailableError("The original package manifest failed its integrity check")
        elif "file_integrity" in manifest:
            recorded = manifest["file_integrity"][name]
            if (not isinstance(recorded, dict) or len(raw) != recorded.get("size_bytes")
                    or hashlib.sha256(raw).hexdigest() != recorded.get("sha256")):
                raise PackageUnavailableError("A fixed package file failed its integrity check; create a new package")
        contents[name] = raw
    if filename is not None:
        return contents[filename], filename, mimetypes.guess_type(filename)[0] or "application/octet-stream"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in contents.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return buffer.getvalue(), f"{package_id}.zip", "application/zip"
