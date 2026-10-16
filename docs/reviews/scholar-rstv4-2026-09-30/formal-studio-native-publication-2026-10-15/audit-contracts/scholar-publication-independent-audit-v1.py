from pathlib import Path
from collections import Counter
from contextlib import closing
import hashlib,json,shutil,socket,sqlite3,sys
import psutil

repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-studio-current-native-restart-v10'
native=repo/'.tmp/scholar-nochange-native-v9'
old=repo/'.tmp/scholar-studio-current-native-v2'
prior=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-studio-nochange-2026-10-15'
dest=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-studio-native-publication-2026-10-15'
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
enc=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
digest=lambda x:hashlib.sha256(enc(x).encode()).hexdigest()
def records(s,n):
 t=s['tables'][n];return [dict(zip(t['columns'],row)) for row in t['rows']]
def normalized(db):
 s=snapshot(db);s['schema']=[list(x) for x in s['schema']];return s
def filemap(root,sidecars=False):
 return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and (sidecars or not p.name.endswith(('-wal','-shm')))}
receipt=read(here/'receipt.json');root=Path(receipt['root']);stop=read(here/'owned-stop-terminal.json');terminal=read(here/'backend-terminal.json')
assert stop['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE' and stop['root_preserved']==str(root)
assert terminal['server_stopped'] and terminal['models_allowed']==terminal['workers_started']==0
owner=read(here/'ownership.json')
for identity in [owner['frontend'],owner['backend'],*owner['frontend_windows_console_children']]:
 try:p=psutil.Process(identity['pid'])
 except psutil.NoSuchProcess:continue
 assert p.create_time()!=identity['create_time'], 'Original owned process still present'
for port in owner['ports']:
 with socket.socket() as stream:stream.bind(('127.0.0.1',port))
base=read(here/'action-002-all-tables.json');final=read(here/'action-018-all-tables.json')
assert len(base['tables'])==len(final['tables'])==110 and base['schema']==final['schema']
assert terminal['copy_final_all_tables']==final and normalized(root/'data/catalog.db')==final
ms='manuscript_56652adf9d054cb6ab3819efacf3475c';vid='manuscript_version_de30b95a2d6843059d3c8b420627bf58'
allowed={'manuscripts','manuscript_status_history','submission_events','studio_submission_bindings','studio_assets'}
changed=[n for n,t in base['tables'].items() if t!=final['tables'][n]]
assert set(changed)==allowed
diff={}
for n in changed:
 t=base['tables'][n];u=final['tables'][n];assert t['columns']==u['columns']
 a=Counter(map(enc,t['rows']));b=Counter(map(enc,u['rows']))
 diff[n]={'before_rows':sum(a.values()),'after_rows':sum(b.values()),'removed':[json.loads(x) for x in (a-b).elements()],'added':[json.loads(x) for x in (b-a).elements()]}
for n,num in {'manuscript_status_history':2,'submission_events':4,'studio_submission_bindings':4,'studio_assets':2}.items():
 assert not diff[n]['removed'] and len(diff[n]['added'])==num
before_ms={r['manuscript_id']:r for r in records(base,'manuscripts')};after_ms={r['manuscript_id']:r for r in records(final,'manuscripts')}
assert before_ms.keys()==after_ms.keys()
assert all(v==after_ms[k] for k,v in before_ms.items() if k!=ms)
assert {k for k,v in before_ms[ms].items() if v!=after_ms[ms][k]}=={'revision','updated_at','writing_status','workflow_stage'}
assert before_ms[ms]['revision']==6 and before_ms[ms]['workflow_stage']=='WHOLE_PAPER_REVIEW'
assert after_ms[ms]['revision']==8 and after_ms[ms]['workflow_stage']=='PUBLICATION' and after_ms[ms]['writing_status']=='READY_TO_SUBMIT'
assert before_ms[ms]['title']==after_ms[ms]['title'] and not after_ms[ms]['needs_scientific_review']
doc=next(r for r in records(final,'studio_documents') if r['manuscript_id']==ms)
assert doc['revision']==doc['last_generated_revision']==62 and doc['active_generated_version_id']==vid
version=next(r for r in records(final,'manuscript_versions') if r['manuscript_version_id']==vid)
assert version['version']==5 and version['manuscript_id']==ms
inputs=json.loads(version['inputs_json']);assert inputs['studio_revision']==62
job=next(r for r in records(final,'studio_jobs') if r['job_id']==inputs['job_id'])
assert job['status']=='SUCCEEDED' and job['job_kind']=='GENERATE' and job['input_revision']==62
events={r['event_id']:r for r in records(final,'submission_events')};bindings={r['event_id']:r for r in records(final,'studio_submission_bindings')}
assets={r['asset_id']:r for r in records(final,'studio_assets')}
expected={3:{'manuscripts','manuscript_status_history'},10:{'studio_submission_bindings','submission_events'},11:{'studio_submission_bindings','submission_events'},12:{'manuscripts','manuscript_status_history','studio_submission_bindings','submission_events'},13:{'studio_assets'},14:{'studio_assets'},15:{'studio_submission_bindings','submission_events'}}
phase=[];previous=base;new_events=[];asset_ids=[];requests={};responses={}
for number in range(3,19):
 tag=f'action-{number:03d}';s=read(here/(tag+'-all-tables.json'));request=read(here/(tag+'-request.json'));response=read(here/(tag+'-response.json'))
 assert s['schema']==base['schema'] and s['tables'].keys()==base['tables'].keys()
 changes=[n for n in base['tables'] if previous['tables'][n]!=s['tables'][n]]
 assert set(changes)==expected.get(number,set()), (number,changes)
 assert response['status_code']==(201 if number in {10,11,12,13,14,15} else 200)
 if 'body_utf8' in request:
  raw=request['body_utf8'].encode();assert hashlib.sha256(raw).hexdigest()==request['body_sha256'] and len(raw)==request['body_bytes']
  payload=json.loads(request['body_utf8'])
 else:payload=None
 if number==3:
  assert request['path']==f'/api/manuscripts/{ms}/stage' and payload=={'stage':'FINALIZATION_SUBMISSION','expected_revision':6,'reason':'Author moved paper to FINALIZATION_SUBMISSION'}
  stage_ms=next(r for r in records(s,'manuscripts') if r['manuscript_id']==ms)
  assert stage_ms['revision']==7 and stage_ms['workflow_stage']=='FINALIZATION_SUBMISSION'
 elif number in {10,11,12,15}:
  assert request['path']==f'/api/manuscripts/{ms}/submission-events'
  assert payload['status']=={10:'SUBMITTED',11:'ACCEPTED',12:'PUBLISHED',15:'ARCHIVED'}[number]
  assert payload['generated_version_id']==vid and payload['round_number']==3
  assert payload['venue']=='SOFTWARE_FIXTURE Local WF09-10 — no external submission' and 'SOFTWARE_FIXTURE' in payload['detail']
  event=response['body'];event_id=event['event_id'];new_events.append(event_id)
  stored=events[event_id];binding=bindings[event_id];frozen=json.loads(binding['snapshot_json'])
  assert all(event[k]==v for k,v in stored.items()) and event['binding']['status']=='BOUND'
  assert event['binding']['snapshot']==frozen and event['binding']['snapshot_sha256']==binding['snapshot_sha256']==hashlib.sha256(binding['snapshot_json'].encode()).hexdigest()
  canonical_request={k:payload.get(k) for k in ['venue','round_number','status','detail','generated_version_id','final_asset_id','proof_asset_id']};canonical_request['acknowledged']=payload.get('acknowledged',False)
  assert binding['operation_id']==payload['operation_id'] and binding['request_sha256']==digest(canonical_request)
  assert binding['manuscript_id']==ms and binding['created_at']==stored['created_at']
  assert frozen['event']=={k:stored[k] for k in ['manuscript_id','venue','round','status','detail']}
  fv=frozen['generated_version'];assert fv['manuscript_version_id']==vid and fv['version']==5 and fv['document_revision']==62 and fv['job_id']==job['job_id']
  assert fv['content_sha256']==hashlib.sha256(version['content'].encode()).hexdigest() and fv['inputs_sha256']==hashlib.sha256(version['inputs_json'].encode()).hexdigest()
  assert fv['template_manifest']['author_document_sha256']==digest(json.loads(doc['document_json']))
  if number in {10,12,15}:assert payload['acknowledged'] is True
 elif number in {13,14}:
  assert request['path']==f'/api/manuscripts/{ms}/assets'
  returned=response['body'];asset_ids.append(returned['asset_id']);asset=assets[returned['asset_id']]
  assert all(returned[k]==v for k,v in asset.items() if k!='metadata_json') and returned['metadata']==json.loads(asset['metadata_json'])
 else:assert request['path'] in {'/api/research/discussion/history','/api/research/discussion/context'}
 phase.append({'action':number,'method':request['method'],'path':request['path'],'status_code':response['status_code'],'changed_tables':changes})
 previous=s;requests[number]=payload;responses[number]=response['body']
assert len(new_events)==len(set(new_events))==4 and len(asset_ids)==len(set(asset_ids))==2
frozen=[json.loads(bindings[event_id]['snapshot_json']) for event_id in new_events]
assert [v['event']['status'] for v in frozen]==['SUBMITTED','ACCEPTED','PUBLISHED','ARCHIVED']
assert frozen[0]['parent_event_id'] is None
assert [v['parent_event_id'] for v in frozen[1:]]==new_events[:-1]
assert [v['accepted_event_id'] for v in frozen]==[None,None,new_events[1],new_events[1]]
assert all(v['generated_version']==frozen[0]['generated_version'] for v in frozen)
assert all(v['files'] is None for v in frozen[:3])
assert new_events[-1]=='submission_11ea9271d86a4f43ba6fa6c486b31174'
files_receipt=read(repo/'.tmp/scholar-wf-native-files-v1/receipt.json');assert files_receipt['scientific_approval'] is False
for role,asset_id in zip(['final','proof'],asset_ids):
 asset=assets[asset_id];path=Path(asset['storage_path']);assert root.resolve() in path.resolve().parents and asset['manuscript_id']==ms
 assert asset['status']=='READY' and asset['asset_kind']=='DOCUMENT'
 assert path.stat().st_size==asset['size_bytes'] and sha(path)==asset['sha256']
 original=repo/'.tmp/scholar-wf-native-files-v1'/asset['filename'];assert original.read_bytes()==path.read_bytes()
 assert frozen[-1]['files'][role]=={'asset_id':asset_id,'filename':asset['filename'],'sha256':asset['sha256'],'byte_size':asset['size_bytes'],'media_type':asset['media_type']}
 assert requests[15][role+'_asset_id']==asset_id
finalasset=assets[asset_ids[0]];proofasset=assets[asset_ids[1]]
assert finalasset['size_bytes']==13830 and finalasset['sha256']=='f3d27b83a2256d7cffa25e3162b67e060fc55c30311abcc6329c8d3394f0e0e4'
assert proofasset['size_bytes']==739 and proofasset['sha256']=='319b444fb182840168b1d2e3e83f6da18c19aacf6b42044f4f3f2455d29e5ca1'
originalpdf=next(r for r in records(final,'studio_artifacts') if r['job_id']==job['job_id'] and r['artifact_kind']=='PDF')
assert originalpdf['sha256']==finalasset['sha256'] and Path(originalpdf['storage_path']).read_bytes()==Path(finalasset['storage_path']).read_bytes()
prooftext=Path(proofasset['storage_path']).read_text(encoding='utf-8');assert 'synthetic local proof fixture' in prooftext and 'not a publisher proof or a scientific approval' in prooftext
beforefiles=read(here/'before110-all-files.json');afterfiles=filemap(root)
assert all(afterfiles[k]==v for k,v in beforefiles.items() if k!='data/catalog.db' and not k.endswith(('-wal','-shm')))
newpaths=set(afterfiles)-{k for k in beforefiles if not k.endswith(('-wal','-shm'))}
assert newpaths=={Path(assets[aid]['storage_path']).relative_to(root).as_posix() for aid in asset_ids}
original=Path(receipt['original']);assert filemap(original,sidecars=True)==read(old/'protected-original-files.json')
assert sha(original/'data/catalog.db')==receipt['original_db_sha256']
assert len(read(old/'original-all-tables.json')['tables'])==109
assert len(receipt['protected_external_artifacts'])==25 and all(sha(Path(p))==v for p,v in receipt['protected_external_artifacts'].items())
assert len(receipt['backend_source_vector'])==311 and all(sha(repo.parent/'RSTV4'/p)==v for p,v in receipt['backend_source_vector'].items())
front=repo.parent/'writing-studio';build=Path(receipt['frontend_root'])
assert len(receipt['frontend_product_vector'])==91 and all(sha(front/p)==v and sha(build/p)==v for p,v in receipt['frontend_product_vector'].items())
assert len(receipt['frontend_dist_vector'])==76 and all(sha(build/p)==v for p,v in receipt['frontend_dist_vector'].items())
assert {str(p.relative_to(build)) for p in (build/'dist').rglob('*') if p.is_file()}==set(receipt['frontend_dist_vector'])
log=read(native/'native-ui-log.json');assert len(log)==45 and read(prior/'audit/native-ui-log-first18.json')==log[:18]
bylabel={r['label']:r for r in log}
guardcases={'wf09-filled-submission-unacknowledged-disabled':('＋ 记录',True),'wf09-submission-acknowledged-enabled':('＋ 记录',False),'wf10-published-before-accepted-disabled':('＋ 记录',True),'wf10-published-ack-without-acceptance-still-disabled':('＋ 记录',True),'wf10-published-after-local-acceptance-awaits-ack':('＋ 记录',True),'wf10-archive-ack-without-file-selection-disabled':('确认归档完成',True),'wf10-both-files-selected-no-archive-ack-disabled':('确认归档完成',True),'wf10-files-and-local-archive-ack-enabled':('确认归档完成',False)}
guards=[]
for label,(button,disabled) in guardcases.items():
 item=bylabel[label];matches=[line for line in item['state'].splitlines() if ' button ' in line and line.rstrip().endswith(button)]
 assert len(matches)==1 and ('(disabled)' in matches[0])==disabled
 guards.append({'label':label,'step':item['step'],'button':button,'disabled':disabled,'observed_ax_line':matches[0].strip()})
final_ui=log[-1]['state'];assert '正在读取此成文版本的段落与来源' not in final_ui
assert all(text in final_ui for text in [new_events[-1],vid,finalasset['sha256'],proofasset['sha256'],'Fixed citation source - software acceptance','此版本的固定参考文献'])
assert log[-1]['label']=='wf10-final-read-complete-or-exact-pending-observation'
audit={'status':'PASS_NATIVE_LOCAL_WF09_WF10_PUBLICATION_PROVENANCE','full_table_count':110,'unchanged_tables':105,'changed_tables':changed,'schemas_exact':True,'old_append_rows_exact':True,'all_comments_checks_links_original_and_a211_exact':True,'author_revision':62,'active_generated_version':5,'generated_version_id':vid,'workflow_revision_before':6,'workflow_revision_after':8,'single_explicit_stage_write':True,'published_service_automatically_enters_publication':True,'archive_no_extra_revision':True,'new_event_ids':new_events,'new_asset_ids':asset_ids,'all_event_bindings_hashes_parent_acceptance_and_fixed_version_exact':True,'source311_frontend91_dist76_exact':True,'all_original109_tables_raw_db_and_files_exact':True,'external25_exact':True,'all_old_owned_files_exact_except_expected_catalog':True,'new_owned_files_only_two_uploaded_assets':True,'native_observations_total':45,'prior_a211_first18_exact':True,'wf_native_observations':23,'final_native_generated_read_complete':True,'final_archive_receipt_persists_after_native_reload':True,'final_live_snapshot_equals_last_action018_and_terminal':True,'owned_processes_absent_and_ports_free':True,'root_retained':str(root),'models_executed_in_studio':0,'workers_started':0,'scientific_approval':False,'external_submission_or_acceptance':False,'original118_complete':False,'integrated11_complete':False}
dest.mkdir(exist_ok=False)
def put(name,value):
 p=dest/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
put('audit/independent-audit.json',audit);put('audit/phase-by-phase-changes.json',phase);put('audit/declared-row-diff.json',diff);put('audit/native-negative-guards.json',guards);put('audit/final-files.json',afterfiles);put('audit/native-wf-observations.json',log[22:])
for p in here.iterdir():
 if p.is_file() and (p.name.startswith('action-') or p.name in {'backend-terminal.json','owned-stop-terminal.json','receipt.json','ownership.json','ready.json','before110-all-files.json','before110-all-tables.json','preparation-manifest.json'}):
  out=dest/'runtime'/p.name;out.parent.mkdir(exist_ok=True);shutil.copyfile(p,out)
for p in native.iterdir():
 if p.is_file() and (p.name.startswith(('wf09','wf10','wf-generated')) or p.name=='native-ui-log.json'):
  out=dest/'native'/p.name;out.parent.mkdir(exist_ok=True);shutil.copyfile(p,out)
for p in (repo/'.tmp/scholar-wf-native-files-v1').iterdir():
 if p.is_file():
  out=dest/'exact-uploaded-fixtures'/p.name;out.parent.mkdir(exist_ok=True);shutil.copyfile(p,out)
for path in [Path(__file__),repo.parent/'RSTV4/src/rstv4/studio_publication.py',repo.parent/'RSTV4/src/rstv4/studio.py']:
 out=dest/'audit-contracts'/path.name;out.parent.mkdir(exist_ok=True);shutil.copyfile(path,out)
report='''# Native local WF09–10 publication and archive acceptance — 2026-10-15

The current Studio completed the actual local software-fixture chain: finalization → SUBMITTED → ACCEPTED → PUBLISHED → exact-file archive → native reload and persistent receipt. This is bounded WF09/WF10 software evidence. Original118 coverage and the same-current-source combined11-group acceptance remain incomplete. No scientific approval, external journal submission/acceptance/publication or UuMA gate transition is asserted.

## Actual native behavior and guards

The official in-app browser operated the same current311-file backend,91-file frontend and existing76-file build. Of45 retained native observations, the first18 A211 observations remain exactly equal to their previous sealed prefix; steps23–45 provide23 WF observations, with four intervening read/navigation observations preserved. A211 checks and all old comments/links remain unchanged throughout this workflow phase.

The real stage request returned200 and changed workflow revision6→7, WHOLE_PAPER_REVIEW→FINALIZATION_SUBMISSION. The SUBMITTED form could not record until its displayed fixed-version acknowledgement was checked. Before acceptance, selecting PUBLISHED could not record even with that acknowledgement checked. After a single explicit local ACCEPTED event, PUBLISHED still required the displayed-version acknowledgement. Each of SUBMITTED, ACCEPTED and PUBLISHED was submitted once and returned201. All venue/detail strings explicitly state SOFTWARE_FIXTURE/local/no external submission or scientific approval.

PUBLISHED automatically entered PUBLICATION through the original service, revision7→8. An attempted click using an obsolete accessibility node then reported stale state and made no second stage request. No extra stage transition was needed. The existing v5 and author structure r62 were retained.

Two native file-chooser uploads each returned201 exactly once. The final PDF is the original generated v5 byte-for-byte:13830bytes, SHA256 `f3d27b83a2256d7cffa25e3162b67e060fc55c30311abcc6329c8d3394f0e0e4`. The739-byte TXT proof is explicitly synthetic local UI evidence, not a publisher proof; SHA256 `319b444fb182840168b1d2e3e83f6da18c19aacf6b42044f4f3f2455d29e5ca1`. Its text disclaims external publication, DOI registration, scientific evidence and unperformed amendments. The report includes exact uploaded bytes and verifies their stored asset bytes/hashes, manuscript ownership and fixed-version binding.

Archive confirmation remained disabled with acknowledgement but no selected files, and with both files selected but no archive acknowledgement. It enabled only after selecting both exact files and acknowledging this local fixture. The archive action returned201 once, event `submission_11ea9271d86a4f43ba6fa6c486b31174`. A subsequent intentional native reload showed the same persistent archive receipt, original v5/r62, both filenames, SHA256 values and sizes. The final generated read completed, including fixed manuscript text and references; the intermediate loading observation is preserved.

## Independent full-state and binding audit

Every stage was compared against its immediate complete110-table predecessor. Action003 changed manuscripts and appended status history; actions010/011 appended only event/binding; action012 additionally performed automatic PUBLICATION/history; actions013/014 each appended one asset; action015 appended only archive event/binding. Discussion context/history actions004–009 and016–018 were readonly and changed no tables.

Across action002→final,105 of110tables remain precisely identical. Only five tables change: manuscripts, manuscript_status_history, submission_events, studio_submission_bindings and studio_assets. No old append row is removed or changed. The target manuscript changes only writing_status, workflow_stage, revision and updated_at; its title and every other field remain exact, as do all other manuscripts. Two status-history rows, four events, four bindings and two assets are appended. ARCHIVED preserves revision8 and PUBLICATION. Schema and all author documents/history, current and old generated versions/jobs/artifacts, sources, approvals,210 old comments plus A211, response checks and change links remain exact.

Each new binding independently matches its exact canonical original request, operation ID, event body, timestamp and frozen snapshot SHA256. Parent linkage is SUBMITTED→ACCEPTED→PUBLISHED→ARCHIVED. Publication and archive both point to the exact local ACCEPTED event. All four freeze the same generated version, content/input hashes, original successful generation job, author r62 digest and recorded template/source manifest. The archive alone binds the two exact owned, READY document assets. Full row-level differences are archived.

The original109-table source root's raw database and all original files remain exact;25 external original artifacts remain byte-identical. All preexisting owned payload files remain exact except the expected database changes; only two uploaded asset files are new. Current backend311/frontend91/build76 vectors remain exact. Studio ran no model, worker or generation. This separate workflow did not rerun GPU or QuickRead.

The final complete readonly110-table snapshot equals both the last action018 checkpoint and the actual stopped backend terminal snapshot. Exact owned frontend/backend/console identities have exited, ports8877/50114 are free and the root/data are retained. Other user pages and processes were not closed by this audit.

## Preserved failures and practical limits

Initial generated-view reads were pending/failed; their real diagnostics remain archived. An intentional official reload recovered real200 reads without modifying security settings or fabricating responses. The first file-chooser label wait timed out and reset the browser kernel before any asset POST; subsequent observed-label native chooser uploads each created only one asset. Timeout and stale-node observations are retained; successful business actions were not replayed.

These software fixtures exercise local state, guards and immutable provenance, including a deliberately synthetic proof. They do not validate the quality of a real journal proof or scientific result. Remaining original118 requirements, updated delivery quality, complex source/mapping/reasoning branches, native slow-read behavior and complete11-group integrated acceptance still require their own evidence. Historical passing groups are not promoted to a current whole-system pass.
'''
(dest/'acceptance.md').write_text(report,encoding='utf-8')
manifest={p.relative_to(dest).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(dest.rglob('*')) if p.is_file()}
put('manifest.json',manifest)
assert all(sha(dest/n)==v['sha256'] and (dest/n).stat().st_size==v['bytes'] for n,v in manifest.items())
seal={'status':'SEALED_INDEPENDENT_WF09_WF10_NATIVE_LOCAL_CHAIN','report_path':dest.relative_to(repo).as_posix(),'payload_files':len(manifest),'acceptance_sha256':sha(dest/'acceptance.md'),'manifest_sha256':sha(dest/'manifest.json'),'audit_sha256':sha(dest/'audit/independent-audit.json'),'native_log_sha256':sha(dest/'native/native-ui-log.json'),'same_current_sources':{'backend':311,'frontend':91,'build':76},'unchanged_tables':105,'overall_complete':False}
with (repo/'.tmp/scholar-publication-independent-audit-v1-seal.json').open('x',encoding='utf-8') as stream:json.dump(seal,stream,indent=2)
print(json.dumps(seal,ensure_ascii=False))
