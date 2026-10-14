"""Reproduce catalog startup writes on an exclusive disposable backup only."""
import hashlib
import json
import sqlite3
from pathlib import Path

from rstv4.database import initialize_catalog

repo = Path(__file__).resolve().parents[1]
receipt = repo / '.tmp/scholar-database-startup-diagnostic-v1.json'
copy = repo / '.tmp/scholar-database-startup-diagnostic-v1.db'
assert not receipt.exists() and not copy.exists()
root = Path(json.loads((repo / '.tmp/scholar-overview-services.json').read_text())['root'])
source = root / 'data/catalog.db'
with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as original:
    with sqlite3.connect(copy) as target:
        original.backup(target)
with sqlite3.connect(copy) as connection:
    connection.execute("UPDATE schema_version SET applied_at='2000-01-01 00:00:00'")

def snapshot():
    with sqlite3.connect(copy) as connection:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        data = {table: connection.execute(
            'SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid').fetchall()
            for table in tables}
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return data, hashlib.sha256(copy.read_bytes()).hexdigest()

before, old_sha = snapshot()
initialize_catalog(copy)
after, new_sha = snapshot()
changed = {table: {'before': before[table], 'after': after[table]}
           for table in before if before[table] != after[table]}
assert set(changed) == {'schema_version'}, changed.keys()
assert old_sha != new_sha
result = {'status': 'REPRODUCED_STARTUP_SCHEMA_TIMESTAMP_WRITE',
          'disposable_database': str(copy), 'source_database_modified': False,
          'table_count': len(before), 'changed_tables': changed,
          'before_sha256': old_sha, 'after_sha256': new_sha}
with receipt.open('x', encoding='utf-8') as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False))
