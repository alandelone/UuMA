"""Read current published bytes and the original discussion without new operations."""
import ast
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx

repo=Path(__file__).resolve().parents[1]
path=repo/'.tmp/scholar-research-chat-readonly-v1.json'
if path.exists():raise RuntimeError('Preserve exclusive read-only receipt')
tree=ast.parse((repo/'.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='process_guard' for target in node.targets))
subprocess.run(['powershell','-NoProfile','-Command',guard],cwd=repo,check=True)
native=json.loads((repo/'.tmp/scholar-research-chat-native-v3.json').read_text(encoding='utf-8'))
assert native['status']=='PASS_NATIVE_FIXED_SOURCE_DISCUSSION'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
db=Path(native['root'])/'data/catalog.db'
before=sha(db.read_bytes())
with sqlite3.connect(f'{db.resolve().as_uri()}?mode=ro',uri=True) as conn:
 counts={name:conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ['research_discussion_jobs','research_discussion_messages','research_discussion_annotations']}
assert counts=={'research_discussion_jobs':1,'research_discussion_messages':2,'research_discussion_annotations':1}
bound=next(row['body'] for row in native['responses'] if row['path']=='/api/catalog/discussion/context')
with httpx.Client(base_url='http://127.0.0.1:8885',timeout=30) as client:
 receipt=client.get(f"/api/catalog/discussion/requests/{native['message_request_id']}",params={'scope':bound['scope_key']});assert receipt.status_code==200
 receipt=receipt.json();assert receipt['job']['status']=='COMPLETE' and receipt['messages'][0]['context']==bound
 assert receipt['job']['model_contract']==native['actual_contract']
 historical=client.get(f"/api/catalog/discussion/messages/{receipt['messages'][0]['message_id']}/context",params={'scope':bound['scope_key']});assert historical.status_code==200
 historical=historical.json();assert historical['sources'][0]['context']==bound and historical['sources'][0]['quote']==receipt['messages'][0]['quote']
 published={}
 for endpoint,name in [('/','catalog_web.html'),('/catalog-research-chat.js','catalog_research_chat.js'),('/catalog-research-workspaces.js','catalog_research_workspaces.js')]:
  response=client.get(endpoint);assert response.status_code==200 and response.content==(repo.parent/f'RSTV4/src/rstv4/{name}').read_bytes();published[name]=sha(response.content)
assert sha(db.read_bytes())==before
result={'status':'PASS_CURRENT_DISCUSSION_AND_PUBLISHED_BYTES_READONLY','new_operations':0,'new_model_calls':0,'browser_verified':False,'counts':counts,'database_sha256':before,'source_context_sha256':bound['context_sha256'],'actual_contract':receipt['job']['model_contract'],'published_sha256':published,'historical_source_state':historical['sources'][0]['current_source_state']}
with path.open('x',encoding='utf-8') as out:json.dump(result,out,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
