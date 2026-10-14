"""Read-only current G10 database and immutable source comparison."""
from pathlib import Path
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

repo=Path(__file__).resolve().parents[1]
info=json.loads((repo/'.tmp/scholar-g10-native-v1/prepared-existing-copy/receipt.json').read_text(encoding='utf-8'))
before=json.loads((repo/'.tmp/scholar-g10-native-v1/prepared-existing-copy/all-tables.json').read_text(encoding='utf-8'))
db=Path(info['root'])/'data/catalog.db'
out=repo/'.tmp/scholar-g10-native-v1/final-audit-v1'
out.mkdir(exist_ok=False)
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    now={r[0]:[dict(v) for v in c.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
         for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert set(before)==set(now) and len(now)==105
key=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True)
delta={}
for name,rows in before.items():
    original={key(r) for r in rows}
    current={key(r) for r in now[name]}
    assert original<=current, f'Original rows changed or disappeared: {name}'
    if rows!=now[name]:
        delta[name]={'before':len(rows),'after':len(now[name]),'new_rows':[r for r in now[name] if key(r) not in original]}
source=Path(info['source_root'])/'data/catalog.db'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(source)==info['source_db_sha256']
g09=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-citation-source-native-du6504t2/data/catalog.db')
assert sha(g09)=='9f46702f641a18a5418814377dc74e7183d1648516c4d83a5ffcc07990069c7c'
(out/'all-tables.json').write_text(json.dumps(now,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'READ_ONLY_DELTA_OBSERVED_NOT_COMPLETION','observed_at':datetime.now(timezone.utc).isoformat(),
         'root':str(db.parent.parent),'table_count':len(now),'all_original_rows_exact':True,
         'source_database_unchanged':True,'g09_database_unchanged':True,'current_db_sha256':sha(db),
         'delta':delta,'overall11_complete':False}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({**{k:v for k,v in receipt.items() if k!='delta'},'delta_counts':{k:{a:b for a,b in v.items() if a!='new_rows'} for k,v in delta.items()}},ensure_ascii=False))
