from pathlib import Path
import sqlite3,json
repo=Path(__file__).resolve().parents[1]
info=json.loads((repo/'.tmp/scholar-g10-native-v1/prepared-existing-copy/receipt.json').read_text(encoding='utf-8'))
before=json.loads((repo/'.tmp/scholar-g10-native-v1/prepared-existing-copy/all-tables.json').read_text(encoding='utf-8'))
db=Path(info['root'])/'data/catalog.db'
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    now={r[0]:[dict(v) for v in c.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
         for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
report={'status':'DIAGNOSTIC_ONLY','tables':len(now),'added':{n:len(now[n]) for n in set(now)-set(before)},
        'removed':sorted(set(before)-set(now)),
        'changed':{n:{'before':len(before[n]),'after':len(now[n]),'old':before[n],'current':now[n]} for n in before if before[n]!=now.get(n)}}
(repo/'.tmp/scholar-g10-native-v1/schema-diagnostic-v2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({**{k:v for k,v in report.items() if k!='changed'},'changed':{n:{'before':v['before'],'after':v['after']} for n,v in report['changed'].items()}},ensure_ascii=False))
