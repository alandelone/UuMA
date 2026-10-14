from pathlib import Path
import json
import sqlite3
r=Path.cwd()
f=json.loads((r/'.tmp/scholar-generated-assets-native-v1.json').read_text(encoding='utf-8'))
with sqlite3.connect(f"file:{(Path(f['root'])/'data/catalog.db').as_posix()}?mode=ro",uri=True) as c:
    c.row_factory=sqlite3.Row
    print('ACTUAL_NATIVE_CALLS',[{k:dict(row)[k] for k in ['call_id','task','status','contract_json','error_json','completed_at']} for row in c.execute('SELECT * FROM studio_model_calls WHERE manuscript_id=?',[f['manuscript_id']])])
print((r/'rules/testing-contracts.md').read_text(encoding='utf-8'))
print((r/'docs/reviews/scholar-rstv4-2026-09-30/generated-materials-contract-2026-10-09.md').read_text(encoding='utf-8'))
