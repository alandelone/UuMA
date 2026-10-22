"""Fail closed when a retained local database has moved to a remote owner."""
from pathlib import Path


def require_local_owner(database: Path) -> None:
    marker = database.with_name(database.name + ".remote-owner.json")
    if marker.exists():
        raise RuntimeError(
            "This domain database is an archived workstation copy. "
            "Use its authenticated server semantic service."
        )
