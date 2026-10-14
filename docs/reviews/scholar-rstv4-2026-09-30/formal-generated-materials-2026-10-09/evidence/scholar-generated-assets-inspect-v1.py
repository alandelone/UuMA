from pathlib import Path
import hashlib
import json
import sqlite3

r=Path.cwd()
d=json.loads((r/'.tmp/scholar-generated-assets-full-v1.json').read_text(encoding='utf-8'))
print('FULL_KEYS',list(d))
print('FULL_RESULTS',[(v['command'][-1],v['exit_code']) for v in d.get('results',[])])
for key in d:
    if isinstance(d[key],dict):print('OBJECT',key,'SIZE',len(d[key]))
    elif key!='results':print('FIELD',key,str(d[key])[:1000])
assert d['before_sha256']==d['after_sha256']
assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha for path,sha in d['after_sha256'].items())
print('ALL_SOURCES_STABLE',len(d['after_sha256']))
f=json.loads((r/'.tmp/scholar-generated-assets-native-v1.json').read_text(encoding='utf-8'))
c=sqlite3.connect(f"file:{(Path(f['root'])/'data/catalog.db').as_posix()}?mode=ro",uri=True)
c.row_factory=sqlite3.Row
names=[x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'studio_%' OR name LIKE '%artifact%')")]
print('NATIVE_TABLES',[(name,[y[1] for y in c.execute('PRAGMA table_info('+name+')')]) for name in names])
for name in ['studio_jobs','studio_artifacts','studio_generated_versions','studio_manuscripts']:
    if name not in names:continue
    rows=[dict(x) for x in c.execute('SELECT * FROM '+name+' WHERE manuscript_id=?',[f['manuscript_id']])]
    print(name,json.dumps(rows,ensure_ascii=False)[:10000])
downloads={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in (Path.home()/'Downloads').iterdir() if p.is_file() and
           (p.name.startswith('manuscript') or p.name.startswith('submission_package'))}
(r/'.tmp/scholar-generated-assets-downloads-before-v1.json').write_text(json.dumps(downloads,indent=2),encoding='utf-8')
print('DOWNLOADS',downloads)
print((r.parent/'RSTV4/tests/test_studio_generated_assets.py').read_text(encoding='utf-8')[5000:17000])
