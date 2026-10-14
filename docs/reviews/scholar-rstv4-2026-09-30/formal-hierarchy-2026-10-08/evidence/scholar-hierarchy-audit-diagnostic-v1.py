import json, sqlite3
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db'
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row
    rows=[dict(row) for row in c.execute('SELECT o.base_revision,c.before_json,c.after_json FROM studio_changes c JOIN studio_operations o ON o.operation_id=c.operation_id WHERE o.manuscript_id=? AND o.base_revision IN (34,35,36,38,39,40,41)',(fixture['native_manuscript_id'],))]
result={row['base_revision']:{key:json.loads(row[key]).get('argument_relations') for key in ['before_json','after_json']} for row in rows}
with (repo/'.tmp/scholar-hierarchy-audit-diagnostic-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(json.dumps(result,ensure_ascii=False))
