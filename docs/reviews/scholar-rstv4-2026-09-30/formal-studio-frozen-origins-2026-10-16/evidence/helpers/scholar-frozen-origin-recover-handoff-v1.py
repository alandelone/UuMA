from pathlib import Path
from contextlib import closing
import hashlib, json, sqlite3

repo = Path(__file__).resolve().parents[1]
digest = '777b00417a24bf7b16a02f3b4cc80f2f2d8539f16f5c449a5dd6965dd990d503'
with closing(sqlite3.connect((repo/'.uuma-local/uuma.db').resolve().as_uri()+'?mode=ro',uri=True)) as conn:
    row = conn.execute("SELECT id,time,payload FROM repo_session_events WHERE kind='handoff' AND json_extract(payload,'$.digest')=? ORDER BY id DESC LIMIT 1",(digest,)).fetchone()
assert row is not None, 'Do not discard the previous Scholar handoff'
payload = json.loads(row[2])
content = payload['content']
dest = repo/'.tmp/scholar-frozen-origin-previous-verified-handoff-v1.md'
with dest.open('x',encoding='utf8') as handle:
    handle.write(content)
assert hashlib.sha256(dest.read_bytes()).hexdigest() == digest
assert dest.read_text(encoding='utf8') == content
result = {'status':'EXACT_PREVIOUS_SCHOLAR_HANDOFF_RECOVERED_FROM_SINGLE_NAMED_JOURNAL_EVENT',
          'event_id':row[0],'time':row[1],'sha256':digest,'characters':len(content),'backup':str(dest),
          'live_handoff_not_modified':True,'all_history_not_loaded':True}
with (repo/'.tmp/scholar-frozen-origin-recover-handoff-v1.json').open('x',encoding='utf8') as handle:
    json.dump(result,handle,indent=2)
print(json.dumps(result,indent=2))
