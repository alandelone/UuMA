from pathlib import Path
import json
import sqlite3
import hashlib

r=Path.cwd()
f=json.loads((r/'.tmp/scholar-generated-assets-native-v1.json').read_text(encoding='utf-8'))
with sqlite3.connect(f"file:{(Path(f['root'])/'data/catalog.db').as_posix()}?mode=ro",uri=True) as c:
    c.row_factory=sqlite3.Row
    for name in ['studio_jobs','studio_submission_packages','manuscript_versions','manuscripts']:
        print(name,[dict(x) for x in c.execute('SELECT * FROM '+name+' WHERE manuscript_id=?',[f['manuscript_id']])])
    art=dict(c.execute("SELECT * FROM studio_artifacts WHERE manuscript_id=? AND artifact_kind='GENERATED_JSON'",[f['manuscript_id']]).fetchone())
    generated=json.loads(Path(art['storage_path']).read_text(encoding='utf-8'))
    print('GENERATED_KEYS',list(generated))
    print('PARAGRAPH',generated['sections'][0]['paragraphs'][0])
    before=f['after_fixture_tables']
    now={x[0]:[dict(row) for row in c.execute('SELECT * FROM "'+x[0]+'" ORDER BY rowid')]
         for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    print('EXISTING_ROW_DIFFS',[(name,[{k:row[k] for k in row if k.endswith('_id')} for row in rows if row not in now[name]])
          for name,rows in before.items() if any(row not in now[name] for row in rows)])
print('DOWNLOADS',[(p.name,p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()) for p in (Path.home()/'Downloads').iterdir() if p.is_file() and (p.name.startswith('manuscript') or p.name.startswith('submission_package'))])
print((r.parent/'RSTV4/tests/test_studio_generated_assets.py').read_text(encoding='utf-8')[:5100])
