import json
import sqlite3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
proof = json.loads((repo / '.tmp/scholar-durable-model-reconcile-step-v10.json').read_text())
assert proof['job']['status'] == 'SUCCEEDED'
result = json.loads(proof['job']['result_json'])
root = Path(proof['root'])
with sqlite3.connect((root / 'data/catalog.db').as_uri() + '?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    units = [dict(row) for row in conn.execute('SELECT * FROM skeleton_units WHERE skeleton_id=? ORDER BY seq_idx', (result['skeleton_id'],))]
    skeleton = dict(conn.execute('SELECT * FROM paper_skeletons WHERE skeleton_id=?', (result['skeleton_id'],)).fetchone())
assert len(units) == result['units'] == 3
calls = [c for c in proof['calls'] if c['status'] == 'RETURNED']
assert len(calls) == 12
audit = {'status':'READ_BACK_ALL_12_ACTUAL_LAYER_RETURNS_AND_NEW_3_UNIT_SKELETON',
         'root':str(root), 'skeleton':skeleton, 'units':units,
         'calls':calls, 'scientific_approval':False,
         'source_is_software_verification_document':True, 'build_scientific_quality_verified':False}
with (repo / '.tmp/scholar-experiment-controls-source-audit-v1.json').open('x', encoding='utf-8') as h:
    json.dump(audit, h, ensure_ascii=False, indent=2)
print(json.dumps({'status':audit['status'],'skeleton_id':result['skeleton_id'],
                  'units':3,'actual_returns':12,'columns':list(units[0])}))
