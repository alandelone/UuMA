from pathlib import Path
from contextlib import closing
from datetime import datetime,timedelta,timezone
import hashlib,json,re,shutil,socket,sqlite3,sys
import psutil

repo=Path(__file__).resolve().parents[1]
v1=repo/'.tmp/scholar-quickread-native-preview-v1';v2=repo/'.tmp/scholar-quickread-native-preview-v2'
dest=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-newparse-quickread-native-readback-2026-10-15'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=repo.parent/'RSTV4'
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
def snap(p):
 s=snapshot(p);s['schema']=[list(r) for r in s['schema']];return s
def records(s,n):
 t=s['tables'][n];return [dict(zip(t['columns'],row)) for row in t['rows']]
def files(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
root=Path(read(v2/'receipt.json')['root']);baseline=read(repo/'.tmp/scholar-quickread-authorized-v4/after-all-tables.json')
assert len(baseline['tables'])==106 and snap(root/'data/catalog.db')==baseline
frozen_files=read(v2/'before-all-files.json');assert files(root)==frozen_files
vector=read(repo/'.tmp/scholar-quickread-authorized-v3/source-vector-311.json')
assert len(vector)==311 and all(sha(source/p)==v for p,v in vector.items())
http=[]
for phase in [v1,v2]:
 receipt=read(phase/'receipt.json');terminal=read(phase/'terminal.json');owned=read(phase/'owned-stop-terminal.json');ready=read(phase/'ready.json')
 assert receipt['model_operations']==receipt['workers']==receipt['job_executions']==0
 assert terminal['models_workers_jobs_budget_mutations']==0
 assert owned['status']=='EXACT_OWNED_API_STOPPED_PORT_FREE_ORIGINAL106_FILES311_EXACT' and owned['no_other_processes_stopped']
 assert read(phase/'before106-all-tables.json')==read(phase/'terminal106-all-tables.json')==snap(phase/'catalog-before.db')==baseline
 assert read(phase/'before-all-files.json')==read(phase/'terminal-all-files.json')==frozen_files
 assert terminal['all106_exact'] and terminal['all_files_exact'] and terminal['source311_exact']
 for identity in [ready['identity'],read(phase/'launched.json')['identity']]:
  try:p=psutil.Process(identity['pid'])
  except psutil.NoSuchProcess:continue
  assert p.create_time()!=identity['create_time'], 'Exact owned process still exists; never signal a reused PID'
 with socket.socket() as check:check.bind(('127.0.0.1',ready['port']))
 requests=sorted(phase.glob('request-*.json'));responses=sorted(phase.glob('response-*.json'));assert len(requests)==len(responses)
 for requestpath in requests:
  q=read(requestpath);p=read(requestpath.with_name(requestpath.name.replace('request-','response-')))
  allowed=q['method'] in {'GET','HEAD','OPTIONS'} or (q['method']=='POST' and q['path'] in {'/api/catalog/discussion/context','/api/catalog/discussion/history'} | ({'/api/catalog/papers/query'} if phase==v2 else set()))
  assert q['allowed']==allowed
  if not allowed:
   assert phase==v1 and q['path']=='/api/catalog/papers/query' and q['method']=='POST' and p=={'status_code':403,'write_denied':True}
  elif q['path']=='/favicon.ico':assert p['status_code']==404
  else:assert p['status_code']==200
  if q['method']=='POST':assert q['path'] in {'/api/catalog/papers/query','/api/catalog/discussion/context','/api/catalog/discussion/history'}
  http.append({'preview':phase.name,'serial':requestpath.name,'method':q['method'],'path':q['path'],'allowed':q['allowed'],'status_code':p['status_code']})
assert len(http)==37 and sum(not r['allowed'] for r in http)==1 and sum(r['status_code']==404 for r in http)==2
assert len(list(v1.glob('request-*.json')))==12 and len(list(v2.glob('request-*.json')))==25
log1=read(v1/'native-ui-log.json');log2=read(v2/'native-ui-log.json');assert len(log1)==10 and len(log2)==3
assert ':53118/' in log1[0]['state'] and all(':54984/' in r['state'] for r in log1[1:]+log2)
combined=[{'evidence_file':str((phase/'native-ui-log.json').relative_to(repo)),'local_step':item['step'],**item} for phase,log in [(v1,log1),(v2,log2)] for item in log]
combined.sort(key=lambda item:item['at_utc'])
bylabel={r['label']:r for r in combined};assert len(bylabel)==13
paper='paper_dde0a449e93444c2771e7b0edeb7daf9';target='job_fe4651959298eab54d88abd9edaf6760'
parse_id='parse_run_bb2661e7c11bb18dd684661073472d71';oldparse='parse_run_5de840df2a60a2b9d9705d6f92807413'
assessment_id='assessment_2663f1581433c6e731b80ff6eca5113f';skel_id='skeleton_ad1dc385a70f2dd67e89eb1ebec075cd'
cid='collection_62ca47c927342115eb5f8fd870af9ca6'
events=records(baseline,'acquisition_model_call_events');assert len(events)==34
target_events=sorted((r for r in events if r['job_id']==target),key=lambda r:r['event_seq'])
assert [r['event_kind'] for r in target_events]==['STARTED','RETURNED']
returned=target_events[-1];expected_call={'source':json.loads(returned['source_json']),'input':json.loads(returned['input_json']),'output':json.loads(returned['output_json']),'contract':json.loads(returned['contract_json']),'error_type':returned['error_type']}
assert expected_call['source']['parse_run_id']==parse_id
expected_call_id='acquisition-call-57ed124b5066bed2f2fb9a4137f607d68ffc83b527a590ef12bf8f1f9b30175c'
assert returned['call_id']==expected_call_id and expected_call['contract']['actual_model']=='gemini-3.5-flash-lite'
assert expected_call['contract']['router_run_id']=='run_1d896e58474643dc8a6528159fddc051'
def call_from_ax(state):
 marker='text {\n  "source":';start=state.index(marker)+len('text ')
 return json.JSONDecoder().raw_decode(state[start:])[0]
for item in [bylabel['new-quickread-original-call-open-read-only'],*log2]:assert call_from_ax(item['state'])==expected_call
assessment=next(r for r in records(baseline,'paper_assessments') if r['assessment_id']==assessment_id)
assert assessment['model_name']==expected_call['contract']['actual_model'] and assessment['input_digest']==expected_call['source']['job_input_digest']
card=json.loads(assessment['result_json']);assert card['question'] is None and card['deep_read_reasons']==card['evidence_quotes']==[]
assert card=={k:v for k,v in expected_call['output'].items() if k!='_contract'}
question_state=bylabel['new-quickread-question-original-version-expanded']['state']
for key in ['assessment_id','input_digest','prompt_version','model_name']:assert f'{key}: {assessment[key]}' in question_state
def fulltext(state):
 m=re.search(r'container 当前固定对象的完整原文\n[ \t]*\d+ text (.*?)(?=\n[ \t]*\d+ (?:button|checkbox|container|text))',state,re.S)
 assert m,'Expanded original source text was not captured';return m.group(1)
assert fulltext(question_state)=='null' and 'CATALOG / assessment' in question_state and 'QUICK_READ / question' in question_state
parse=next(r for r in records(baseline,'parse_runs') if r['parse_run_id']==parse_id)
file=next(r for r in records(baseline,'source_file_versions') if r['file_version_id']==parse['file_version_id'])
assert sha(Path(file['storage_path']))==file['sha256']=='85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99' and Path(file['storage_path']).stat().st_size==1827
blocks=sorted((r for r in records(baseline,'document_blocks') if r['parse_run_id']==parse_id),key=lambda r:r['sequence'])
assert len(blocks)==3 and expected_call['input']=={'blocks':[{'block_id':r['block_id'],'section':r['section'],'text':r['text']} for r in blocks]}
parse_state=bylabel['latest-gpu-parse-select-discussion-original-no-send']['state']
expected_parse_meta={'parse_run_id':parse_id,'file_version_id':file['file_version_id'],'file_sha256':file['sha256'],'parser_name':parse['parser_name'],'parser_version':parse['parser_version'],'config_digest':parse['config_digest'],'parse_status':parse['status']}
assert fulltext(parse_state)=='\n\n'.join(r['text'] for r in blocks)
assert all(f'{k}: {v}' in parse_state for k,v in expected_parse_meta.items()) and '选择独立原文单元（3）' in parse_state
skel=next(r for r in records(baseline,'paper_skeletons') if r['skeleton_id']==skel_id)
paper_version=next(r for r in records(baseline,'paper_versions') if r['paper_version_id']==skel['paper_version_id'])
skel_source=json.loads(paper_version['source_json']);assert skel_source['parse_run_id']==oldparse and oldparse!=parse_id
assert paper_version['version']==skel['version']==1 and skel['extractor_model']=='gemini-3.7-flash'
units=sorted((r for r in records(baseline,'skeleton_units') if r['skeleton_id']==skel_id),key=lambda r:r['seq_idx'])
old_state=bylabel['historical-skeleton-v1-select-discussion-explicit-old-source-no-send']['state']
assert fulltext(old_state)=='\n\n'.join(r['raw_text'] for r in units)
expected_old_meta={'paper_id':paper,'paper_version_id':paper_version['paper_version_id'],'paper_version':1,'skeleton_id':skel_id,'version':1,'file_version_id':skel_source['file_version_id'],'parse_run_id':oldparse,'content_digest':skel['content_digest'],'parsed_digest':paper_version['parsed_digest'],'pdf_digest':paper_version['pdf_digest'],'extractor_model':skel['extractor_model'],'prompt_version':skel['prompt_version']}
assert all(f'{k}: {v}' in old_state for k,v in expected_old_meta.items()) and 'CATALOG / skeleton' in old_state
refs=[r for r in records(baseline,'reference_entries') if r['citing_paper_id']==paper];assert len(refs)==6
progress=bylabel['original-collection-progress-open-after-quickread-success']['state']
assert all(r['raw_text'] in progress and r['raw_text'] in old_state for r in refs)
assert all(r['page_number']==2 for r in refs)
jobs=records(baseline,'acquisition_jobs');current=[r for r in jobs if r['collection_id']==cid]
assert len(current)==4 and all(r['status']=='SUCCEEDED' for r in current)
quick=next(r for r in current if r['job_id']==target);gpu=next(r for r in current if r['job_id']=='job_76d39031d8cc329ec431e6a896a08f54')
assert quick['attempts']==quick['fencing_token']==1 and gpu['attempts']==6
collection=next(r for r in records(baseline,'collections') if r['collection_id']==cid);assert collection['status']=='ACTIVE' and collection['revision']==4
assert 'COLLECTION / ACTIVE' in progress and cid in progress and '尚有引用未解析 · 待处理任务 0 · 原文引用 6，未解析 6' in progress
assert all(text in progress for text in ['获取 PDF · 已完成 · 1 项','PDF 解析 · 已完成 · 1 项','快速阅读 · 已完成 · 1 项','范围筛选 · 已完成 · 1 项','g11-original-newparse-quickread-once-v4'])
attempt=next(r for r in records(baseline,'acquisition_attempts') if r['job_id']==target)
local=lambda value:datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8))).strftime('%Y年%m月%d日 %H:%M:%S')
assert local(attempt['started_at'])+' → '+local(attempt['completed_at']) in progress
frontier={r['reference_entry_id']:r for r in records(baseline,'collection_reference_frontier') if r['collection_id']==cid}
assert sum(frontier.get(r['reference_entry_id'],{}).get('state',r['resolution_status'])!='RESOLVED' for r in refs)==6
budget=[r for r in records(baseline,'collection_budget_events') if r['request_id']=='g11-newparse-quickread-time-budget-v1'];assert len(budget)==1
limits=json.loads(budget[0]['limits_json']);assert limits=={'max_active_seconds':175828,'max_papers':500,'max_registered_pdf_bytes':10737418240,'max_task_attempts':None}
assert '48.84111111111111' in progress and 'Value: 500' in progress and 'Value: 10' in progress
assert '尚未绑定讨论对象' in progress and 'entry area (disabled) 问题' in progress and 'button (disabled) 发送问题' in progress
post_targets=[json.loads(read(p)['body_utf8']) for p in v2.glob('request-*.json') if read(p)['path']=='/api/catalog/discussion/context']
assert {(p['object_kind'],p['object_id'],p.get('part')) for p in post_targets}=={('paper',paper,None),('assessment',assessment_id,'question'),('parse',parse_id,None),('skeleton',skel_id,None)}
tests=read(repo/'.tmp/scholar-rv-prompt-full-v1/receipt.json');assert tests['status']=='PASS' and tests['same_new311_frozen_vector'] and '1130 passed, 20 warnings in 501.61s' in tests['summary']
assert snap(root/'data/catalog.db')==baseline and files(root)==frozen_files
audit={'status':'PASS_NATIVE_READ_ONLY_NEWPARSE_QUICKREAD_SOURCE_AND_HISTORY_READBACK','native_observation_count':13,'v1_failed_preview_observations':1,'v2_successful_preview_observations':12,'capture_streams':{'v1_log_count':10,'v2_log_count':3},'http_request_count':37,'v1_http_count':12,'v2_http_count':25,'initial_harness_read_query_403':1,'normal_favicon_404':2,'all_other_http_200':True,'full106_before_after_live_and_execution_baseline_exact':True,'all_non_sidecar_file_bytes_exact':True,'source311_exact':True,'all34_model_events_exact':True,'actual_new_model_call_json_full_object_matches_persisted':True,'actual_model':expected_call['contract']['actual_model'],'actual_run_id':expected_call['contract']['router_run_id'],'new_assessment_id':assessment_id,'question_original_text':'null','new_parse_id':parse_id,'new_parse_ordered_blocks_exact':3,'original_pdf_sha256':file['sha256'],'original_pdf_size':1827,'historical_skeleton_id':skel_id,'historical_parse_id':oldparse,'historical_model':skel['extractor_model'],'historical_skeleton_full_original_text_exact':True,'historical_skeleton_not_newparse_generation':True,'collection_id':cid,'collection_status':'ACTIVE','four_current_jobs_succeeded':True,'frontier_jobs':0,'unresolved_references':6,'reference_fulltexts_and_page2_exact':True,'quickread_attempts':1,'gpu_attempts':6,'authorized_budget_event_still_once':True,'limits':limits,'preview_models_workers_job_executions_budget_mutations':0,'chat_messages_annotations_deepread_requests_sent':0,'all_exact_owned_previews_stopped_and_ports_free':True,'root_retained':str(root),'retained_test_result':'1130 passed / 20 existing warnings / 501.61s','tests_rerun':False,'scientific_approval':False,'collection_complete':False,'ca08_ac08_ch03_only_bounded_native_read_support':True,'original118_complete':False,'integrated11_complete':False}
dest.mkdir(exist_ok=False)
def put(name,value):
 p=dest/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
put('audit/independent-audit.json',audit);put('audit/http-readonly-inventory.json',http);put('audit/native-observations-chronological.json',combined)
put('audit/expected-native-model-call.json',expected_call);put('audit/expected-native-source-versions.json',{'assessment':{k:assessment[k] for k in ['assessment_id','input_digest','prompt_version','model_name']},'parse':expected_parse_meta,'skeleton':expected_old_meta})
put('audit/final-live106-all-tables.json',baseline);put('audit/final-live-files.json',files(root));put('audit/current-source-vector311.json',vector)
for phase in [v1,v2]:
 out=dest/phase.name;out.mkdir()
 for p in phase.iterdir():
  if p.is_file() and not p.name.endswith(('-wal','-shm')):shutil.copyfile(p,out/p.name)
contracts=dest/'audit-contracts';contracts.mkdir()
for p in [Path(__file__),repo/'.tmp/scholar-quickread-native-preview-v1.py',repo/'.tmp/scholar-quickread-native-preview-v2.py',source/'src/rstv4/catalog_web.py',source/'src/rstv4/research_context.py',source/'src/rstv4/research_discussions.py',source/'src/rstv4/acquisition.py']:
 shutil.copyfile(p,contracts/p.name)
shutil.copyfile(repo/'.tmp/scholar-rv-prompt-full-v1/receipt.json',dest/'retained-current311-full-test-receipt.json')
prior=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-gpu-newparse-quickread-2026-10-15'
prior_manifest=read(prior/'manifest.json');assert all(sha(prior/p)==entry['sha256'] for p,entry in prior_manifest.items())
put('verified-prior-execution-references.json',{str((prior/p).relative_to(repo)):sha(prior/p) for p in ['acceptance.md','manifest.json','independent-audit.json']})
report='''# Original newparse QuickRead native readonly readback — 2026-10-15

The real native Catalog now reads back the original successful newparse QuickRead, its actual model receipt and exact source, while explicitly distinguishing the old Skeleton. The original Collection shows all four current tasks completed but remainsACTIVE with six unresolved references. This supports only bounded CA08/AC08/CH03 native-read branches. Collection completion, original118 and complete11-group integrated acceptance are not established.

## Actual native readback

Thirteen retained observations were audited by timestamp and actual browser URL. The first53118 preview failed at the Catalog list because the test wrapper incorrectly allowedGET but rejected the application's semantic readonly `POST /api/catalog/papers/query`. The original route uses `_read_catalog` and performs a query. After the exact owned preview stopped with all106tables/files/source311 unchanged, v2 admitted that single semantic query in addition to context/history reads. No product guard or browser security setting was changed. The first capture file contains10observations: its first is the failed53118preview and its next9 belong to recovered54984preview. The second capture file adds3expanded source observations from54984. Directory names and restarted local step numbers are not treated as chronology.

Native Paper details displayed the actual new quick_read call and expanded its complete source/input/output/contract JSON. Independent decoding equals the persisted RETURNED event in full: call `acquisition-call-57ed124b5066bed2f2fb9a4137f607d68ffc83b527a590ef12bf8f1f9b30175c`, actual `gemini-3.5-flash-lite`, router run `run_1d896e58474643dc8a6528159fddc051`, original input digest and durable transport operation. The displayed source pins `parse_run_bb2661e7c11bb18dd684661073472d71` and the unchanged1827-byte PDF SHA `85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99`.

Selecting the actual QuickRead question and expanding original/version metadata displayed `assessment_2663f1581433c6e731b80ff6eca5113f`, its exact input digest, quick-read-v1 and actual model. Its complete original question is literallynull. The source card's other scientific fields are likewise null, and evidence/deep-read lists empty. The source is an explicit software fixture; an actual conservative empty answer is preserved without inventing a scientific finding.

Native selection of the latest GPU parse displayed its exact parse/file IDs, PDF hash, parser/version/config digest and all three ordered stored block texts in full. Selecting Skeleton v1 instead displayed its original `parse_run_5de840df2a60a2b9d9705d6f92807413`, old paper version1, `skeleton_ad1dc385a70f2dd67e89eb1ebec075cd`, original digests and `gemini-3.7-flash`/paper-skeleton-v1. Its full three-unit original text independently matches storage. The old Skeleton is preserved as historical work; it is not attributed to the new GPU parse or new QuickRead.

Opening the original Topic's Collection progress showed the same original Collection, four completed stages including QuickRead, and the real worker-v4 successful execution at14:47:26–14:47:30 local time. The original GPU attempt6 remains intact. The UI reports zero pending frontier tasks **and six unresolved original references**, all six raw texts and page2 locations matching storage. Collection status isACTIVE; zero queued tasks does not establish collection completion. The previously approved time limit remains175828seconds with one original budget event;500papers,10GiB and unlimited attempts remain unchanged. Native displayed elapsed usage is the historical observation, not a new audit-time usage measurement.

Switching to the overview/Collection cleared the selected discussion source and disabled send/annotation controls. No question, annotation, deep-read request, budget save, worker start or job execution was submitted. Source switching/readback alone does not prove the remaining scope-comparison, model-response or mutation branches of CH03 or other requirements.

## Independent preservation and HTTP boundary

Both preview before/terminal snapshots, their independent full backups and the current readonly database equal the actual original execution's full106-table final snapshot exactly, including schema and all34 model events. All non-sidecar payload file bytes and the current311-file source vector remain exact. This is the actual original GPU/QuickRead root, not a regenerated copy or a historical successful result substituted for a new run.

All37captured HTTP requests were inventoried: v1 had12, v2 had25. The sole denied request was the initial wrapper's semantic query403; each preview also returned an ordinary favicon404. Every other request returned200. Allowed POSTs were only Catalog listing and discussion context/history. No message, annotation, deep-read, budget, collection or job mutation route occurred. The retained HTTP response records contain status/content-type metadata, not full raw response bodies; complete visible native model/source JSON and text were independently checked against the immutable database rather than represented as uncaptured HTTP payloads.

The readonly middleware denied model gateway access, and no worker was launched. Its initialization and observed reads preserve all106tables and original files exactly. Both exact owned API/launcher identities have exited;53118/54984are free and original data remains retained. This audit sends no process signal and never stops an oldPID. SQLite WAL/shared-memory sidecars are excluded from immutable payload hashes; all actual database rows/schema and non-sidecar bytes are compared.

## Retained evidence and limits

The evidence includes both complete preview runs, initial wrapper failure, exact readonly requests/response metadata, all13native observations, four screenshots, both backups and complete before/terminal/live checkpoints, source contracts and current source hashes. The previous actual-execution report's entire payload manifest is reverified; its references are retained. The current-source1130passed/20existing-warning test result remains valid because source311 is exact; tests and model executions were not rerun.

Native source provenance/readback passed for this bounded fixture. Scientific understanding, new deep-reading quality, unresolved-reference resolution, broader CH03 behavior, all remaining original118 rows and the complete11-group integrated flow remain separate unfinished work. No scientific approval or mission/review gate transition is claimed.
'''
(dest/'acceptance.md').write_text(report,encoding='utf-8')
manifest={p.relative_to(dest).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(dest.rglob('*')) if p.is_file()}
put('manifest.json',manifest)
assert all(sha(dest/p)==v['sha256'] and (dest/p).stat().st_size==v['bytes'] for p,v in manifest.items())
seal={'status':'SEALED_NATIVE_READONLY_NEWPARSE_QUICKREAD_READBACK','report_path':dest.relative_to(repo).as_posix(),'payload_files':len(manifest),'acceptance_sha256':sha(dest/'acceptance.md'),'manifest_sha256':sha(dest/'manifest.json'),'audit_sha256':sha(dest/'audit/independent-audit.json'),'full106_exact':True,'native_observations':13,'overall_complete':False}
with (repo/'.tmp/scholar-quickread-native-readback-audit-v1-seal.json').open('x',encoding='utf-8') as stream:json.dump(seal,stream,indent=2)
print(json.dumps(seal,ensure_ascii=False))
