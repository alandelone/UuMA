from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .models import ArtifactRecord


class ArtifactStore:
    """Content-addressed storage for declared durable task artifacts."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        source: str | Path,
        *,
        media_type: str,
        logical_name: str,
        created_by: str,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> ArtifactRecord:
        source_path = Path(source).resolve(strict=True)
        digest = self._digest(source_path)
        destination = self.root / digest[:2] / digest[2:4] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source_path, destination)
        return ArtifactRecord(
            digest=digest,
            media_type=media_type,
            size_bytes=source_path.stat().st_size,
            logical_name=logical_name,
            local_path=str(destination),
            created_by=created_by,
            task_id=task_id,
            run_id=run_id,
        )

    @staticmethod
    def _digest(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()

