import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from rstv4.database import (
    CATALOG_VERSION,
    RESEARCH_VERSION,
    initialize_catalog,
    initialize_project,
)


def snapshot(path: Path) -> tuple[list[str], str]:
    connection = sqlite3.connect(path)
    try:
        records = list(connection.iterdump())
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    return records, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("initialize", "component", "version"),
    [
        (initialize_catalog, "catalog", CATALOG_VERSION),
        (initialize_project, "research", RESEARCH_VERSION),
    ],
)
def test_current_database_initialization_preserves_records_and_bytes(
    tmp_path: Path, initialize: Callable[[Path], None], component: str, version: int
) -> None:
    path = tmp_path / "current.db"
    initialize(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE schema_version SET applied_at=? WHERE component=?",
            ("2000-01-01 00:00:00", component),
        )
        assert connection.execute(
            "SELECT version FROM schema_version WHERE component=?", (component,)
        ).fetchone()[0] == version
    before = snapshot(path)

    initialize(path)
    initialize(path)

    assert snapshot(path) == before


@pytest.mark.parametrize(
    ("initialize", "component", "version"),
    [
        (initialize_catalog, "catalog", CATALOG_VERSION),
        (initialize_project, "research", RESEARCH_VERSION),
    ],
)
def test_database_version_change_records_application_once(
    tmp_path: Path, initialize: Callable[[Path], None], component: str, version: int
) -> None:
    path = tmp_path / "upgrade.db"
    initialize(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE schema_version SET version=?,applied_at=? WHERE component=?",
            (version - 1, "2000-01-01 00:00:00", component),
        )

    initialize(path)

    with sqlite3.connect(path) as connection:
        applied_version, applied_at = connection.execute(
            "SELECT version,applied_at FROM schema_version WHERE component=?", (component,)
        ).fetchone()
    assert applied_version == version
    assert applied_at != "2000-01-01 00:00:00"
    applied = snapshot(path)
    initialize(path)
    assert snapshot(path) == applied
