import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
receipt=json.loads((repo/'.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))
db=Path(receipt['root']).resolve()/'data/catalog.db'
previous=json.loads((repo/'.tmp/scholar-collection-original-final-v1.json').read_text(encoding='utf-8'))
assert hashlib.sha256(db.read_bytes()).hexdigest()==previous['database_sha256']
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
 tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
 before={table:conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables}
assert len(before)==96
with (repo/'.tmp/scholar-review-pre-migration-v1.db').open('xb') as h:h.write(db.read_bytes())
with (repo/'.tmp/scholar-review-pre-migration-rows-v1.json').open('x',encoding='utf-8') as h:json.dump(before,h,ensure_ascii=False,indent=2)
path=repo/'.tmp/scholar-studio-history-owned-reload-v1.py'
source=path.read_text(encoding='utf-8').replace('scholar-studio-history-final-','scholar-review-final-')
source=source.replace('fixed_studio_history_preview','review_recovery_preview').replace('production_build_studio_history_preview','production_build_review_recovery_preview')
exec(compile(source,str(path),'exec'))
print('Verified original isolated runtime reloaded for v7 review ledger; exact pre-migration database preserved.')
