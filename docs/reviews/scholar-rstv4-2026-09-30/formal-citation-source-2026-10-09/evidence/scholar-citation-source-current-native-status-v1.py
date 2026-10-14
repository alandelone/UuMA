from pathlib import Path
import json,sqlite3,sys
sys.stdout.reconfigure(encoding='utf-8');fixture=json.loads(Path('.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'));db=Path(fixture['root'])/'data/catalog.db'
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row
 for table,fields in [('studio_jobs','job_id,manuscript_id,job_kind,status'),('studio_model_calls','call_id,manuscript_id,task,status,contract_json,error_json'),('research_discussion_jobs','request_id,status,error_json'),('studio_chat_messages','message_id,role,anchor_type,anchor_id,status')]:
  print(table,json.dumps([dict(r) for r in conn.execute(f'SELECT {fields} FROM {table} ORDER BY rowid')],ensure_ascii=False))
