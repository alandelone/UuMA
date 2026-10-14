"""Record all isolated database tables before a guarded fixed-code reload."""
import hashlib
import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
output = repo / '.tmp/scholar-database-startup-fixed-baseline-v1.json'
assert not output.exists()
root = Path(json.loads((repo / '.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))['root'])
db = root / 'data/catalog.db'
canonical = lambda value: hashlib.sha256(json.dumps(
    value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    default=lambda raw: {'bytes_hex': raw.hex()}).encode()).hexdigest()
with sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True) as connection:
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    data = {table: connection.execute(
        'SELECT * FROM "' + table.replace('"', '""') + '" ORDER BY rowid').fetchall()
        for table in tables}
    schema = connection.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
    assert not connection.execute(
        "SELECT 1 FROM studio_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()
    assert not connection.execute(
        "SELECT 1 FROM research_discussion_jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()
result = {'root': str(root), 'database_sha256': hashlib.sha256(db.read_bytes()).hexdigest(),
          'all_table_sha256': {table: canonical(rows) for table, rows in data.items()},
          'schema_sha256': canonical(schema), 'schema_versions': data['schema_version'],
          'previous_batch_byte_equality_failed': True,
          'previous_batch_database_sha256': json.loads((repo / '.tmp/scholar-studio-shared-final-v1.json').read_text(encoding='utf-8'))['database_sha256']}
with output.open('x', encoding='utf-8') as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps({key: value for key, value in result.items() if key != 'all_table_sha256'}))
