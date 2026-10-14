import hashlib
import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
receipt = json.loads((repo / '.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))
db = Path(receipt['root']).resolve() / 'data/catalog.db'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
previous = json.loads((repo / '.tmp/scholar-studio-history-final-v1.json').read_text(encoding='utf-8'))
assert sha(db.read_bytes()) == previous['database_sha256']

def snapshot():
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {table: {'columns': [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')],
                        'rows': conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()}
                for table in tables}

before = snapshot()
assert len(before) == 96
with (repo / '.tmp/scholar-collection-pre-migration-database-v1.db').open('xb') as handle:
    handle.write(db.read_bytes())
with (repo / '.tmp/scholar-collection-pre-migration-tables-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(before, handle, ensure_ascii=False, indent=2)
source_path = repo / '.tmp/scholar-studio-history-owned-reload-v1.py'
source = source_path.read_text(encoding='utf-8').replace('scholar-studio-history-final-', 'scholar-collection-final-')
source = source.replace('fixed_studio_history_preview', 'collection_workflow_preview')
source = source.replace('production_build_studio_history_preview', 'production_build_collection_workflow_preview')
exec(compile(source, str(source_path), 'exec'))

with (repo / '.tmp/scholar-collection-owned-runtime-setup-v1.json').open('x', encoding='utf-8') as handle:
    json.dump({'status': 'OWNED_RELOAD_REQUESTED', 'original_root': receipt['root'],
               'before_database_sha256': previous['database_sha256'], 'tables': 96,
               'migration': 'catalog v5->v6; collections nullable topic_id and creation_request_json'}, handle, indent=2)
print('Owned Catalog/Studio/frontend restart requested; original database snapshot preserved.')
