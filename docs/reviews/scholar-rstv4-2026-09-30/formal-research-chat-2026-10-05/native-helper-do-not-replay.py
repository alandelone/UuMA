"""One actual fixed-source model discussion and annotations; no scientific writes."""
import ast
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import httpx

repo=Path(__file__).resolve().parents[1]
os.environ.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
path=repo/'.tmp/scholar-research-chat-native-v3.json'
if path.exists():raise RuntimeError('Preserve native mutation receipt; resume read-only')
tree=ast.parse((repo/'.tmp/scholar-overview-native-v1.py').read_text(encoding='utf-8'))
guard=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='process_guard' for target in node.targets))
for check in [(repo/'.tmp/scholar-current-preview-proof.ps1').read_text(encoding='utf-8'),guard]:subprocess.run(['powershell','-NoProfile','-Command',check],cwd=repo,check=True)
root=Path(json.loads((repo/'.tmp/scholar-overview-services.json').read_text(encoding='utf-8'))['root']).resolve()
parent=json.loads((repo/'.tmp/scholar-fieldkg-native-v1.json').read_text(encoding='utf-8'))
sha=lambda raw:hashlib.sha256(raw).hexdigest()
canonical=lambda value:sha(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
proof={'status':'STARTED','root':str(root),'responses':[],'browser_verified':False,'production_data_changed':False,'scientific_approval':False,'actual_model_calls':0}
def persist():path.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
persist()
with httpx.Client(base_url='http://127.0.0.1:8885',timeout=60) as catalog,httpx.Client(base_url='http://127.0.0.1:8874/api',timeout=45) as studio:
 def call(client,method,endpoint,expected=200,**kwargs):
  response=client.request(method,endpoint,**kwargs);body=response.json();proof['responses'].append({'server':'catalog' if client is catalog else 'studio','method':method,'path':endpoint,'status':response.status_code,'body':body});persist();assert response.status_code==expected,response.text[:1500];return body
 old_ms={ms:canonical(call(studio,'GET',f'/manuscripts/{ms}/workspace')) for ms in parent['old_workspace_sha256']}
 assert old_ms==parent['old_workspace_sha256']
 response_ms='manuscript_bd7568923be94a2c8510d176010e4cca'
 packages=call(studio,'GET',f'/manuscripts/{response_ms}/packages');assert len(packages)==7
 zips={}
 for package in packages:
  response=studio.get(f"/manuscripts/{response_ms}/packages/{package['package_id']}/download");assert response.status_code==200;zips[package['package_id']]=sha(response.content)
 assert zips==parent['old_package_zip_sha256']
 field='field_785167b274c54c2f921390317406d0a7';snapshot='fieldkg_snapshot_168ec05c7a2e4ad4a070b224c88e1189'
 view=call(catalog,'GET',f'/api/catalog/fields/{field}/workspace',params={'snapshot':snapshot})
 before_field=canonical(view);source=view['selected_snapshot']['sources'][0];unit=source['units'][0]
 with sqlite3.connect(root/'data/catalog.db') as conn:
  scientific_tables=['research_nodes','research_edges','decisions','fieldkg_evidence_candidates','evidence','fieldkg_candidate_gaps','fieldkg_snapshots','track_snapshot_adoptions','studio_model_calls']
  before_records={name:canonical(conn.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()) for name in scientific_tables}
 target={'module':'FIELDKG','field_id':field,'object_kind':'unit','object_id':unit['unit_id'],'snapshot_id':snapshot}
 bound=call(catalog,'POST','/api/catalog/discussion/context',json=target)
 assert bound['object_text']==unit['raw_text']
 quote={'text':bound['object_text'][:min(30,len(bound['object_text']))],'start':0,'end':min(30,len(bound['object_text'])),'offset_unit':'utf16','annotation':'隔离软件验收：固定原文讨论批注。'}
 selected={'target':bound['target'],'expected_context_sha256':bound['context_sha256'],'quote':quote}
 note={'request_id':'research-chat-native-annotation-v3','source':selected,'comment':'保留当时的原对象、原文、版本与精确选区。'}
 annotation=call(catalog,'POST','/api/catalog/discussion/annotations',201,json=note)
 assert call(catalog,'POST','/api/catalog/discussion/annotations',201,json=note)==annotation
 body={'request_id':'research-chat-native-message-v3','content':'这是软件验收资料。请只依据固定原文，简要说明它记录了什么、哪些文件或解析版本信息未知，并注明讨论意见不会批准任何科研决定。','source':selected}
 call(catalog,'POST','/api/catalog/discussion/messages',409,json={**body,'request_id':'research-chat-native-stale-v3','source':{**selected,'expected_context_sha256':'0'*64}})
 call(catalog,'POST','/api/catalog/discussion/messages',422,json={**body,'request_id':'research-chat-native-quote-v3','source':{**selected,'quote':{**quote,'text':'Invented original'}}})
 receipt=call(catalog,'POST','/api/catalog/discussion/messages',202,json=body)
 started=time.monotonic()
 while receipt['job']['status'] in ['QUEUED','RUNNING'] and receipt['execution_observation']=='LIVE_WORKER' and time.monotonic()-started<360:
  time.sleep(2)
  receipt=call(catalog,'GET',f"/api/catalog/discussion/requests/{body['request_id']}",params={'scope':bound['scope_key']})
 proof['model_request_status']=receipt['job']['status'];proof['execution_observation']=receipt['execution_observation'];persist()
 if receipt['job']['status']=='COMPLETE':
  assert len(receipt['messages'])==2 and receipt['messages'][0]['context']==bound
  assert receipt['messages'][0]['quote']['text']==quote['text']
  assert receipt['job']['input']['source']['context']==bound
  assert receipt['job']['model_contract']['actual_model']
  assert receipt['job']['raw_response'] is not None
  repeat=call(catalog,'POST','/api/catalog/discussion/messages',202,json=body)
  assert repeat['messages']==receipt['messages'] and repeat['job']==receipt['job']
  history=call(catalog,'POST','/api/catalog/discussion/history',json={'target':target})
  assert len(history['messages'])==2 and len(history['annotations'])==1
  historical=call(catalog,'GET',f"/api/catalog/discussion/messages/{receipt['messages'][0]['message_id']}/context",params={'scope':bound['scope_key']})
  assert historical['sources'][0]['context']==bound and historical['sources'][0]['quote']==receipt['messages'][0]['quote']
  proof['actual_model_calls']=1;proof['actual_model']=receipt['job']['model_contract']['actual_model'];proof['actual_contract']=receipt['job']['model_contract']
  proof['status']='PASS_NATIVE_FIXED_SOURCE_DISCUSSION'
 else:
  proof['status']='DISCUSSION_NOT_ACCEPTED';proof['actual_model_calls']=1 if receipt['job']['started_at'] else 0
 with sqlite3.connect(root/'data/catalog.db') as conn:
  assert {name:canonical(conn.execute(f'SELECT * FROM {name} ORDER BY rowid').fetchall()) for name in scientific_tables}==before_records
  assert conn.execute('SELECT COUNT(*) FROM research_discussion_jobs').fetchone()[0]==1
  assert conn.execute('SELECT COUNT(*) FROM research_discussion_annotations').fetchone()[0]==1
 assert canonical(call(catalog,'GET',f'/api/catalog/fields/{field}/workspace',params={'snapshot':snapshot}))==before_field
 assert {ms:canonical(call(studio,'GET',f'/manuscripts/{ms}/workspace')) for ms in old_ms}==old_ms
 current_zips={}
 for package in packages:
  response=studio.get(f"/manuscripts/{response_ms}/packages/{package['package_id']}/download");assert response.status_code==200;current_zips[package['package_id']]=sha(response.content)
 assert current_zips==zips
 page=catalog.get('/');assert page.status_code==200 and page.content==(repo.parent/'RSTV4/src/rstv4/catalog_web.html').read_bytes()
 for endpoint,name in [('/catalog-research-chat.js','catalog_research_chat.js'),('/catalog-research-workspaces.js','catalog_research_workspaces.js')]:
  response=catalog.get(endpoint);assert response.status_code==200 and response.content==(repo.parent/f'RSTV4/src/rstv4/{name}').read_bytes()
 proof.update(old_workspace_sha256=old_ms,old_package_zip_sha256=zips,scientific_records_sha256=before_records,page_sha256=sha(page.content),source_context_sha256=bound['context_sha256'],message_request_id=body['request_id'],annotation_id=annotation['annotation_id'])
 persist()
print(json.dumps({key:value for key,value in proof.items() if key not in ['responses','root','scientific_records_sha256','old_workspace_sha256','old_package_zip_sha256']},ensure_ascii=False))
