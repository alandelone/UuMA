from pathlib import Path
import json,sqlite3,hashlib
repo=Path.cwd();fixture=json.loads((repo/'.tmp/scholar-citation-source-native-v1.json').read_text(encoding='utf-8'));db=Path(fixture['root'])/'data/catalog.db';out=repo/'.tmp/scholar-citation-source-failed-discussion-v1';out.mkdir()
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
 conn.row_factory=sqlite3.Row
 tables={name:[dict(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name in ['research_discussion_jobs','research_discussion_messages','studio_model_calls','studio_chat_messages']}
assert len(tables['research_discussion_jobs'])==1 and tables['research_discussion_jobs'][0]['status']=='FAILED'
failed=tables['research_discussion_jobs'][0];contract=json.loads(failed['model_contract_json'])
assert contract['actual_model']=='gemini-3.8-flash'
assert 'not supplied' in json.loads(failed['error_json'])['detail']
(out/'original-records.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'context.md').write_text('The native fixture initially replaced StudioService.gateway only. The browser uses the separate ResearchDiscussionService.gateway; it therefore made a real Gemini reply, which the unchanged fixed-source validator rejected for citing unsupplied evidence. Preserve this FAILED job, actual contract, raw response, projected author message and numeric quote. Do not claim zero remote calls for this fixture, do not approve the rejected reply, weaken the validator or alter the record. Configure both services explicitly to the declared software fixture for subsequent native software checks. This is an execution-context correction, not a scientific learner/prompt modification. Original baseline scientific runs belong to other roots and were not modified. Exact HTTP attempt count is not established by one saved reply record.\n',encoding='utf-8')
print(json.dumps({'status':'FAILED_REAL_REPLY_PRESERVED','actual_model':contract['actual_model'],'recorded_real_replies':1,'http_attempt_count_not_established':True,'sha256':hashlib.sha256((out/'original-records.json').read_bytes()).hexdigest()}))
