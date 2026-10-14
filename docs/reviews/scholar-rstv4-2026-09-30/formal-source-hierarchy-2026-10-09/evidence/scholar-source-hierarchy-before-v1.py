import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
fixture = json.loads((repo / '.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
destination = repo / '.tmp/scholar-source-hierarchy-before-v1'
destination.mkdir(exist_ok=False)
paths = [
    'RSTV4/src/rstv4/database.py', 'RSTV4/src/rstv4/parser_quality.py',
    'RSTV4/src/rstv4/acquisition.py', 'RSTV4/src/rstv4/research_views.py',
    'RSTV4/src/rstv4/studio_templates.py',
    'writing-studio/lib/studio-types.ts',
    'writing-studio/components/studio-template-adoption.tsx',
]
hashes = {}
for relative in paths:
    source = repo.parent / relative
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
database = Path(fixture['root']) / 'data/catalog.db'
with sqlite3.connect(f'file:{database.as_posix()}?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    tables = {r[0]: [dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
              for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    schema = [dict(r) for r in conn.execute('SELECT * FROM sqlite_master ORDER BY type,name')]
    with sqlite3.connect(destination / 'catalog.db') as backup:
        conn.backup(backup)
gold = Path(fixture['golden_root']) / 'data/catalog.db'
assert hashlib.sha256(gold.read_bytes()).hexdigest() == fixture['golden_database_sha256']
record = {'source_sha256': hashes, 'tables': tables, 'schema': schema,
          'database': str(database), 'golden_database': str(gold),
          'golden_sha256': fixture['golden_database_sha256'], 'download_tests_paused': True}
(destination / 'baseline.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': 'PASS_BACKUP', 'source_files': len(paths), 'tables': len(tables),
                  'golden_unchanged': True, 'download_tests_paused': True}))
