from pathlib import Path
import hashlib
import json
import sqlite3
root=Path.cwd()
findings=(root/'repomemory/findings.md').read_text(encoding='utf-8')
print('Full findings read',len(findings),hashlib.sha256(findings.encode('utf-8')).hexdigest())
fixture=json.loads((root/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
before=json.loads((root/'.tmp/scholar-intent-correspondence-native-v1/after-tables.json').read_text(encoding='utf-8'))
with sqlite3.connect(Path(fixture['root'])/'data/catalog.db') as conn:
    conn.row_factory=sqlite3.Row
    after={r[0]:[dict(v) for v in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
           for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
changed=[]
for name in before:
    if before[name]!=after[name]:
        added=[r for r in after[name] if r not in before[name]]
        removed=[r for r in before[name] if r not in after[name]]
        item={'table':name,'before':len(before[name]),'after':len(after[name]),'added':added,'removed':removed}
        changed.append(item)
        print(name,len(before[name]),len(after[name]),'added',len(added),'removed',len(removed))
(root/'.tmp/scholar-intent-correspondence-runtime-data-diagnostic-v1.json').write_text(json.dumps(changed,ensure_ascii=False,indent=2),encoding='utf-8')
print('changed_table_names',[r['table'] for r in changed])
