import json
import sqlite3
import sys
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
ms=fixture['native_manuscript_id']
response=httpx.get(f'http://127.0.0.1:8877/api/manuscripts/{ms}/workspace',timeout=12)
response.raise_for_status()
workspace=response.json()
with sqlite3.connect(f"{(Path(fixture['root'])/'data/catalog.db').as_uri()}?mode=ro",uri=True) as conn:
    conn.row_factory=sqlite3.Row
    changes=[dict(row) for row in conn.execute('SELECT c.*,o.base_revision,o.operation_kind FROM studio_changes c JOIN studio_operations o ON o.operation_id=c.operation_id WHERE c.manuscript_id=? AND o.base_revision>=27 ORDER BY o.base_revision',(ms,))]
result={'label':sys.argv[1],'workspace':workspace,'changes':changes}
with (repo/f'.tmp/scholar-hierarchy-observe-{sys.argv[1]}.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2,ensure_ascii=False)
print(json.dumps({'revision':workspace['document_revision'],'sections':[(s['title'],len(s['paragraphs'])) for s in workspace['document']['sections']], 'changes':[(c['base_revision'],c['operation_kind']) for c in changes]},ensure_ascii=False))
