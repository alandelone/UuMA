import hashlib
import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
receipt = json.loads((repo / '.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))
db = Path(receipt['root']).resolve() / 'data/catalog.db'
previous = json.loads((repo / '.tmp/scholar-collection-pre-migration-tables-v1.json').read_text(encoding='utf-8'))
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    assert len(tables) == 96 and set(tables) == set(previous)
    actual = {}
    for table in tables:
        columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
        rows = [list(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
        actual[table] = canonical(rows)
        if table == 'collections':
            assert columns == previous[table]['columns'] + ['topic_id', 'creation_request_json']
            assert [row[:-2] for row in rows] == previous[table]['rows']
            assert all(row[-2:] == [None, None] for row in rows)
        elif table == 'schema_version':
            assert columns == previous[table]['columns']
            old = {row[0]: row for row in previous[table]['rows']}
            new = {row[0]: row for row in rows}
            assert new.keys() == old.keys()
            for component in old:
                if component == 'catalog':
                    assert old[component][1] == 5 and new[component][1] == 6
                    assert new[component][0] == old[component][0] and new[component][2]
                else:
                    assert new[component] == old[component]
        else:
            assert columns == previous[table]['columns'] and rows == previous[table]['rows'], table
    schema = conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
with sqlite3.connect((repo / '.tmp/scholar-collection-pre-migration-database-v1.db').as_uri() + '?mode=ro', uri=True) as conn:
    old_schema = conn.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
old_definitions = {row[:3]: row[4] for row in old_schema}
new_definitions = {row[:3]: row[4] for row in schema}
assert old_definitions.keys() == new_definitions.keys()
assert [key for key in old_definitions if old_definitions[key] != new_definitions[key]] == [('table','collections','collections')]
baseline = {'database_sha256': sha(db.read_bytes()), 'all_table_sha256': actual,
            'schema_sha256': canonical(schema), 'old_rows_preserved': True,
            'allowed_schema_change': 'collections adds nullable topic_id and creation_request_json',
            'allowed_control_change': 'catalog schema_version 5->6 and actual application timestamp',
            'all_tables': 96, 'new_jobs': 0, 'new_model_calls': 0,
            'before_database_sha256': sha((repo / '.tmp/scholar-collection-pre-migration-database-v1.db').read_bytes())}
with (repo / '.tmp/scholar-collection-post-migration-baseline-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(baseline, handle, ensure_ascii=False, indent=2)
print('Actual v5->v6 migration: all 96 original tables/rows preserved except the declared catalog version application; no new jobs or model calls.')
