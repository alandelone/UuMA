from pathlib import Path
import json
import sqlite3
root=Path.cwd()
fixtures=[json.loads((root/name).read_text(encoding='utf-8')) for name in ['.tmp/scholar-source-hierarchy-fixture-v1.json','.tmp/scholar-intent-correspondence-native-v1.json']]
connections=[sqlite3.connect(Path(f['root'])/'data/catalog.db') for f in fixtures]
for conn in connections: conn.row_factory=sqlite3.Row
names=[row[0] for row in connections[0].execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
changed=[]
for name in names:
    values=[[dict(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for conn in connections]
    if values[0]!=values[1]:
        item={'table':name,'counts':[len(v) for v in values],'columns':[r[1] for r in connections[1].execute(f'PRAGMA table_info("{name}")')]}
        changed.append(item)
        print(json.dumps(item,ensure_ascii=False))
for conn in connections: conn.close()
(root/'.tmp/scholar-intent-correspondence-native-diagnostic-v1.json').write_text(json.dumps(changed,indent=2),encoding='utf-8')
