from pathlib import Path
from collections import Counter
from contextlib import closing
import hashlib,json,math,shutil,sqlite3,sys

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
root=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-g11-native-22n_zg_d')
v3=repo/'.tmp/scholar-quickread-authorized-v3';v4=repo/'.tmp/scholar-quickread-authorized-v4'
dest=repo/'docs/reviews/scholar-rstv4-2026-09-30/formal-gpu-newparse-quickread-2026-10-15'
assert dest.is_dir() and not list(dest.iterdir()), 'Only the verified empty v1 audit output directory may be reused'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
encode=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False)
def put(path,value):
 with (dest/path).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def normalized(db):
 s=snapshot(db);s['schema']=[list(r) for r in s['schema']];return s
def rows(s,n):return [dict(zip(s['tables'][n]['columns'],r)) for r in s['tables'][n]['rows']]
before=read(v3/'before-all-105-tables.json');migrated=read(v3/'after-initialization-all-tables.json')
budgeted=read(v3/'after-budget-all-tables.json');failed=read(v3/'after-execution-all-tables.json')
after=read(v4/'after-all-tables.json');live=normalized(root/'data/catalog.db')
assert len(before['tables'])==105 and len(live['tables'])==106
assert live==after and read(v4/'before-all-tables.json')==failed
assert normalized(v3/'catalog-before.db')==before
assert set(live['tables'])-set(before['tables'])=={'studio_submission_bindings'}
assert live['tables']['studio_submission_bindings']['rows']==[]
assert all(t['columns']==live['tables'][n]['columns'] for n,t in before['tables'].items())
assert set(map(encode,before['schema']))<=set(map(encode,migrated['schema']))
assert migrated['schema']==live['schema']
assert [n for n in before['tables'] if before['tables'][n]!=migrated['tables'][n]]==['schema_version']
assert rows(before,'schema_version')[0]['version']==13 and rows(live,'schema_version')[0]['version']==14
target='job_fe4651959298eab54d88abd9edaf6760';cid='collection_62ca47c927342115eb5f8fd870af9ca6'
gpu='job_76d39031d8cc329ec431e6a896a08f54';parse='parse_run_bb2661e7c11bb18dd684661073472d71'
req='g11-newparse-quickread-time-budget-v1'
changed=[n for n in before['tables'] if before['tables'][n]!=live['tables'][n]]
assert set(changed)=={'acquisition_attempts','acquisition_jobs','acquisition_model_call_events','acquisition_worker_presence','collection_budget_events','collections','paper_assessments','schema_version','sqlite_sequence'}
diff={}
for n in changed:
 old=Counter(map(encode,before['tables'][n]['rows']));new=Counter(map(encode,live['tables'][n]['rows']))
 diff[n]={'before_rows':sum(old.values()),'after_rows':sum(new.values()),'removed':[json.loads(x) for x in (old-new).elements()],'added':[json.loads(x) for x in (new-old).elements()]}
append={'acquisition_attempts':1,'acquisition_model_call_events':2,'acquisition_worker_presence':2,'collection_budget_events':1,'paper_assessments':1}
for n,num in append.items():assert not diff[n]['removed'] and len(diff[n]['added'])==num
jobmap=lambda s:{r['job_id']:r for r in rows(s,'acquisition_jobs')}
oldjobs=jobmap(before);jobs=jobmap(live)
assert oldjobs.keys()==jobs.keys() and len(jobs)==11
assert all(v==jobs[k] for k,v in oldjobs.items() if k!=target)
actual=jobs[target];original=oldjobs[target]
allowed={'status','attempts','fencing_token','result_json','updated_at'}
assert {k for k in original if original[k]!=actual[k]}==allowed
assert original['status']=='READY' and original['attempts']==original['fencing_token']==0
assert actual['status']=='SUCCEEDED' and actual['attempts']==actual['fencing_token']==1
assert actual['lease_owner'] is None and actual['lease_expires_at'] is None
assert json.loads(actual['input_json'])=={'parse_run_id':parse}
assert jobs[gpu]==oldjobs[gpu] and jobs[gpu]['attempts']==6 and jobs[gpu]['status']=='SUCCEEDED'
assert jobmap(failed)==oldjobs and failed['tables']['acquisition_attempts']==before['tables']['acquisition_attempts']
assert failed['tables']['acquisition_model_call_events']==before['tables']['acquisition_model_call_events']
assert [n for n in budgeted['tables'] if budgeted['tables'][n]!=failed['tables'][n]]==['acquisition_worker_presence']
assert all(r['state']=='STOPPED' for r in rows(live,'acquisition_worker_presence'))
events=[r for r in rows(live,'acquisition_model_call_events') if r['job_id']==target]
events.sort(key=lambda r:r['event_seq'])
assert [r['event_kind'] for r in events]==['STARTED','RETURNED']
start,end=events
assert start['call_id']==end['call_id'] and start['source_json']==end['source_json'] and start['input_json']==end['input_json']
assert start['fencing_token']==end['fencing_token']==1 and end['error_type'] is None
source=json.loads(end['source_json']);payload=json.loads(end['input_json']);contract=json.loads(end['contract_json'])
assert source['parse_run_id']==parse and source['job_input_digest']==actual['input_digest']
file=next(r for r in rows(live,'source_file_versions') if r['file_version_id']==source['file_version_id'])
assert sha(Path(file['storage_path']))==file['sha256']==source['pdf_sha256']=='85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99'
assert file['size_bytes']==Path(file['storage_path']).stat().st_size==1827
blocks=sorted((r for r in rows(live,'document_blocks') if r['parse_run_id']==parse),key=lambda r:r['sequence'])
assert len(blocks)==3
assert payload=={'blocks':[{'block_id':r['block_id'],'section':r['section'],'text':r['text']} for r in blocks]}
assert contract['tier']=='light' and contract['task']=='quick_read' and contract['status']=='SUCCESS'
assert contract['prompt_version']=='quick-read-v1' and contract['actual_model']=='gemini-3.5-flash-lite'
assert contract['receipt_id']==end['call_id'] and contract['transport_operation_id']==source['transport_operation_id']
assert contract['router_run_id']=='run_1d896e58474643dc8a6528159fddc051' and contract['delivery']=='durable-run-v1'
result=json.loads(actual['result_json']);output=json.loads(end['output_json'])
assert result['contract']==output['_contract']==contract
assert result['card']=={k:v for k,v in output.items() if k!='_contract'}
card=result['card'];assert all(v is None for k,v in card.items() if k not in {'deep_read_reasons','evidence_quotes'})
assert card['deep_read_reasons']==card['evidence_quotes']==[]
assess=next(r for r in rows(live,'paper_assessments') if r['assessment_id']=='assessment_2663f1581433c6e731b80ff6eca5113f')
assert json.loads(assess['result_json'])==card and assess['input_digest']==actual['input_digest']
assert assess['status']=='COMPLETED' and assess['assessment_type']=='QUICK_READ' and assess['model_name']==contract['actual_model']
attempts=[r for r in rows(live,'acquisition_attempts') if r['job_id']==target]
assert len(attempts)==1 and attempts[0]['status']=='SUCCEEDED' and attempts[0]['fencing_token']==1
assert diff['sqlite_sequence']['removed']==[['acquisition_model_call_events',32]] and diff['sqlite_sequence']['added']==[['acquisition_model_call_events',34]]
oldcollections={r['collection_id']:r for r in rows(before,'collections')};collections={r['collection_id']:r for r in rows(live,'collections')}
assert oldcollections.keys()==collections.keys()
for k,old in oldcollections.items():
 new=collections[k]
 if k!=cid:assert old==new
 else:
  assert {f for f in old if old[f]!=new[f]}=={'revision','updated_at'}
  assert old['revision']==3 and new['revision']==4 and old['status']==new['status']=='ACTIVE'
request=read(v3/'authorized-budget-request.json');response=read(v3/'authorized-budget-response.json')
limits=request['request']['limits'];oldlimits=request['original_limits']
assert request['request']['request_id']==req and request['request']['expected_revision']==3
assert limits['max_active_seconds']==math.ceil(request['usage_observed_immediately_before_update']['active_seconds'])+1800==175828
assert {k:v for k,v in limits.items() if k!='max_active_seconds'}=={k:v for k,v in oldlimits.items() if k!='max_active_seconds'}
assert response['limits']==limits and response['revision']==4
budgetevents=[r for r in rows(live,'collection_budget_events') if r['request_id']==req]
assert len(budgetevents)==1 and json.loads(budgetevents[0]['limits_json'])==limits
files={p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.endswith(('-wal','-shm'))}
oldfiles=read(v3/'before-files.json')
assert all(files[k]==v for k,v in oldfiles.items() if k!='data/catalog.db')
newfiles=sorted(set(files)-set(oldfiles))
deliverypath='data/artifacts/model-delivery/'+hashlib.sha256(source['transport_operation_id'].encode()).hexdigest()+'.json'
delivery=read(root/deliverypath)
assert delivery['operation_id']==source['transport_operation_id'] and delivery['run_id']==contract['router_run_id']
assert delivery['base_url']=='https://api.95963210.xyz/v1'
assert set(newfiles)=={'.rstv4-local/workers/model-g11-original-newparse-quickread-v3.lock','data/catalog.pre-v14.bak',deliverypath}
assert normalized(root/'data/catalog.pre-v14.bak')==before
vector=read(v3/'source-vector-311.json');assert len(vector)==311
assert all(sha(repo.parent/'RSTV4'/p)==digest for p,digest in vector.items())
health=read(v3/'gateway-health.json');assert health['status']==200 and health['mode']=='http' and not health['inference_submitted'] and not health['changed_client_signature_or_credentials']
assert read(v3/'execution-receipt.json')['model_events']==[]
assert read(v4/'execution-receipt.json')['actual_job_status']=='SUCCEEDED'
put('live-readonly-106-tables.json',live);put('live-files.json',files);put('declared-row-diff.json',diff)
audit={'status':'PASS_ACTUAL_ORIGINAL_NEWPARSE_QUICK_READ_PRESERVATION_AUDIT','before_table_count':105,'after_table_count':106,'new_tables':['studio_submission_bindings'],'new_table_empty':True,'original_tables_exact':105-len(changed),'changed_original_tables':changed,'all_old_append_rows_exact':True,'other_ten_jobs_exact':True,'gpu_attempt6_exact':True,'historical_parses_references_source_files_scientific_rows_exact':True,'old_model_events_exact':32,'new_model_events':2,'single_successful_attempt':attempts[0]['attempt_id'],'final_live_equals_v4_after':True,'budget_request_id':req,'budget_applied_once':True,'active_seconds_limit':limits['max_active_seconds'],'other_limits_exact':True,'worker_presence_all_stopped':True,'deep_read_executed':False,'new_jobs_queued':0,'original_non_database_files_exact':len(oldfiles)-1,'new_files':newfiles,'source_vector_311_exact':True,'source_pdf_bytes':1827,'source_pdf_sha256':file['sha256'],'source_parse_id':parse,'source_block_count':3,'target_job_id':target,'model_contract':contract,'assessment_id':assess['assessment_id'],'scientific_content_all_null_empty':True,'scientific_approval':False,'original118_complete':False,'integrated11_complete':False}
put('independent-audit.json',audit)
for phase in (v3,v4):
 out=dest/phase.name;out.mkdir()
 for p in phase.iterdir():
  if p.is_file() and not p.name.endswith(('-wal','-shm')):shutil.copyfile(p,out/p.name)
helpers=dest/'execution-context';helpers.mkdir()
for name in ['scholar-quickread-authorized-once-v3.py','scholar-quickread-authorized-continue-v4.py','scholar-quickread-independent-audit-v1.py','scholar-quickread-independent-audit-v2.py',Path(__file__).name]:shutil.copyfile(repo/'.tmp'/name,helpers/name)
shutil.copyfile(root/deliverypath,dest/'original-durable-model-delivery.json')
proofcode=dest/'verified-product-contract';proofcode.mkdir()
for name in ['durable_model_delivery.py','acquisition_model_calls.py','model_gateway.py','acquisition_worker.py']:shutil.copyfile(repo.parent/'RSTV4/src/rstv4'/name,proofcode/name)
report='''# Original GPU-newparse QuickRead actual execution — 2026-10-15

The original GPU parse's previously unexecuted QuickRead now actually succeeded once. This is a bounded software execution and provenance result. Original118 coverage and the same-current-source combined11-group acceptance remain incomplete; no scientific approval or user-review gate was advanced.

## Actual original execution

The user reported that the original public service now allowed the unchanged native client and had already authorized30 additional runnable minutes after recovery. One original-client health observation returnedHTTP200; no client signature, credential or endpoint change was used. No health inference was submitted. The exact original Collection received one idempotent budget event `g11-newparse-quickread-time-budget-v1`: observed active usage174027.656299seconds, so ceil(usage)+1800 =175828seconds. Other limits remain500papers,10GiB registeredPDF and no task-attempt limit. Existing elapsed usage/history was retained; Collection revision3→4. No second extension occurred.

Original job `job_fe4651959298eab54d88abd9edaf6760` was claimed through the actual worker/lease path restricted toMODEL_READ and the sole eligible exact job. Attempt1/fence1 ran06:47:26.002733–06:47:30.591114UTC, completedSUCCEEDED and released its lease. The old GPU job remainsSUCCEEDED/attempt6 exactly. No GPU reexecution, deep read, other job execution or new dependent job occurred. The scheduling wrapper narrowed queues; production claim, lease, source validation, model call, assessment and completion code remained unchanged.

One STARTED and one RETURNED append-only event bind the same call, job, fence, input digest and operation. The actual returned durable transport contract identifies light/quick-read-v1, model `gemini-3.5-flash-lite`, router run `run_1d896e58474643dc8a6528159fddc051`,279prompt+67completion=346tokens andSUCCESS. The retained original delivery handle independently matches the operation/run and original public endpoint. These are retained native client receipts and persisted records, not a separate new remote router query during this audit.

## Source and result boundary

The actual model input contains exactly the three ordered stored blocks from `parse_run_bb2661e7c11bb18dd684661073472d71`. Source receipt pins `source_file_491d18ddee7958c95deb123a188280d5`, the original1827-byte PDF SHA `85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99`, and original job-input digest. Exact current bytes, stored parse, references and historical human correction were preserved. One appended COMPLETED/QUICK_READ assessment matches the returned card and actual model metadata.

The PDF is an explicit software fixture. Its returned question, method, materials, contribution, results and limitations are allnull; evidence_quotes and deep_read_reasons are empty. This proves an actual conservative model call and durable source-bound publication, not meaningful scientific understanding, external review or approval. Historical QuickRead/Skeleton results are preserved and do not substitute for new deep-reading coverage. No new downstream scientific content was invented.

## Independent full-state preservation

The original root actually migrated105→106tables, adding only empty `studio_submission_bindings`, with catalog schema13→14. All old table definitions/columns remain exact; the old schema objects are retained. This is not the Studio copy's110-table baseline. The retained pre-v14 backup and v3 original backup independently match the entire before105 snapshot.

Of the original105tables,96 remain exactly identical. The nine changed tables contain only: one appended successful attempt; target QuickRead status/attempt/fence/result/completion timestamp; two appended model events; two new STOPPED worker-presence rows; one appended budget event; target Collection revision/timestamp; one appended QuickRead assessment; declared schema version; model-event sequence32→34. Every old append-table row and every other ten jobs remain exact. Old parses, all references, source files, historical model receipts/assessments and all unrelated scientific/control rows remain exact. No rows were deleted. Current readonly106-table snapshot equals the complete v4 postexecution snapshot exactly.

All ten original non-database files remain byte-identical; new files are only model lock, declared pre-v14 backup and the original durable delivery handle. The current311-file product source vector remains exact. This audit made no model call, job claim, budget change, product edit, gate transition or database rewrite. Readonly SQLite may maintain transient shared-memory sidecars; these are excluded from immutable payload-file hashes and never treated as scientific evidence.

## Preserved failed context and remaining work

The v3 failure remains in full. Its test preflight required every worker presence to beSTOPPED, although native run_once had just registered its ownIDLE presence before claim. It failed before any claim, attempt or model call; the already-authorized budget event had applied once. The corrected v4 harness accepts only its exact ownIDLE instance, still requires all other workersSTOPPED, requires the sole eligible original target, verifies unchanged READY/attempt0/fence0 and no prior target model events, and uses the original native claim. Production guards were not weakened, failed history was not removed, the budget was not repeated and no successful result was replayed.

The first independent readonly audit stopped on a mistaken `raw_text` column assumption. The actual current `_handle_quick_read` contract and retained105-table snapshot use `document_blocks.text`. Audit v2 next stopped on an assumed `model.lock` filename: actual `instance_lock(role, slot)` creates `model-g11-original-newparse-quickread-v3.lock`. After documenting both exact contracts in rules/testing-contracts.md at the current verification gate, audit v3 preserves both failed helpers and compares the entire actual payload against all three exact stored `text` values, block IDs and sections, and requires the exact new-file set including the declared slot-specific lock. No model/job was rerun and no assertion was relaxed.

Native Collection/Paper current-result readback and the remaining original118/11-group integrated branches still require their own evidence. No blanket pass is claimed. Mission and review boundaries remain with the Orchestrator/user.
'''
(dest/'acceptance.md').write_text(report,encoding='utf-8')
manifest={p.relative_to(dest).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(dest.rglob('*')) if p.is_file()}
put('manifest.json',manifest)
assert all(sha(dest/p)==entry['sha256'] for p,entry in manifest.items())
receipt={'report_path':dest.relative_to(repo).as_posix(),'payload_files':len(manifest),'acceptance_sha256':sha(dest/'acceptance.md'),'manifest_sha256':sha(dest/'manifest.json'),'independent_audit_sha256':sha(dest/'independent-audit.json'),'actual_tables':106,'original_tables_exact':96,'model_reexecuted_during_audit':False,'overall_complete':False}
with (repo/'.tmp/scholar-quickread-independent-audit-v1-receipt.json').open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2)
print(json.dumps(receipt,ensure_ascii=False))
