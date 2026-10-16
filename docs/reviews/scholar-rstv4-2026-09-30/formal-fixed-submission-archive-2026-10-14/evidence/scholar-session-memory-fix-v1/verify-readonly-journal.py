"""Project a frozen, read-only real journal into this owned evidence directory."""
import hashlib
import json
import sqlite3
import tracemalloc
from pathlib import Path

from uuma.session import Session

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
PROJECTION = OUT / "readonly-projection"
PROJECTION.mkdir()
db = sqlite3.connect((ROOT / ".uuma-local/uuma.db").as_uri() + "?mode=ro", uri=True)
db.execute("BEGIN")


def journal_digest():
    result = hashlib.sha256()
    count = 0
    for row in db.execute("SELECT id,time,kind,payload FROM repo_session_events ORDER BY id"):
        for field in row:
            raw = str(field).encode("utf-8")
            result.update(len(raw).to_bytes(8, "big"))
            result.update(raw)
        count += 1
    return count, result.hexdigest()


try:
    before = journal_digest()
    instance = Session.__new__(Session)
    instance.root = PROJECTION
    instance.db = db  # No constructor/schema writes against the shared source.
    tracemalloc.start()
    instance.progress()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    path = PROJECTION / "active-session/progress.md"
    checked = 0
    with path.open(encoding="utf-8") as stream:
        assert stream.readline() == "# Progress\n"
        assert stream.readline() == "\n"
        assert stream.readline() == "<!-- automatic-session-journal -->\n"
        for seq, time, kind, raw in db.execute(
            "SELECT id,time,kind,payload FROM repo_session_events ORDER BY id"
        ):
            source = json.loads(raw)
            expected = {key: value for key, value in source.items()
                        if key not in {"content", "snapshot"}}
            if "snapshot" in source:
                snapshot = source["snapshot"]
                expected["files_observed"] = (
                    len(snapshot) if isinstance(snapshot, (dict, list)) else 1
                )
            line = stream.readline()
            prefix = f"- {time} #{seq} {kind}: "
            assert line.startswith(prefix)
            assert json.loads(line[len(prefix):]) == expected
            checked += 1
        assert stream.read() == ""
    assert checked == before[0]
    assert journal_digest() == before
    receipt = {
        "status": "PASS_REAL_READONLY_FULL_JOURNAL_PROJECTION",
        "source_mode": "ro",
        "source_rows": checked,
        "frozen_all_row_fields_sha256": before[1],
        "every_projected_row_fields_exact": True,
        "source_rows_and_fields_exact_after_projection": True,
        "projection_python_peak_bytes": peak,
        "output_bytes": path.stat().st_size,
        "handoff_body_not_printed": True,
        "business_commands_replayed": 0,
        "shared_session_closed": False,
    }
    with (OUT / "readonly-journal-receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt))
finally:
    db.close()
