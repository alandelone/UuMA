from pathlib import Path
import hashlib
import json
import sys
repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-g11-parallel-v1'
sys.path.insert(0,str(here))
from runtime_copy_and_serve_v8 import product_guard,check_sources,read_json,RECEIPT,snapshot
vector=product_guard();prepared=read_json(RECEIPT);check_sources(prepared)
phase=here/'actual-mineru-gpu-health-retry-v1'
proof=read_json(phase/'actual-mineru-once-result.json')
assert proof['status']=='PASS_OWNED_SINGLE_EXECUTION_NOT_COMPLETE_G11'
assert proof['actual_mineru_executed'] and proof['device_mode']=='cuda'
job_id='job_76d39031d8cc329ec431e6a896a08f54';collection_id='collection_62ca47c927342115eb5f8fd870af9ca6'
before=read_json(phase/'actual-mineru-once-before-all-tables.json')
after=read_json(phase/'actual-mineru-once-after-all-tables.json')
current=json.loads(json.dumps(snapshot(Path(proof['root'])/'data/catalog.db')))
assert current==after,'Readback must not mutate any rows/schema'
assert before['schema']==after['schema'] and before['tables'].keys()==after['tables'].keys()
changed={k for k in before['tables'] if before['tables'][k]!=after['tables'][k]}
assert changed=={'acquisition_attempts','acquisition_jobs','acquisition_worker_presence','document_blocks','paper_versions','parse_runs'}
def rows(s,name):
    t=s['tables'][name];return [dict(zip(t['columns'],r)) for r in t['rows']]
for table in changed-{'acquisition_jobs'}:
    old=before['tables'][table];new=after['tables'][table]
    assert old['columns']==new['columns']
    newrows={r[0]:r for r in new['rows']};assert len(newrows)==len(new['rows'])
    for row in old['rows']:assert newrows[row[0]]==row,(table,row[0])
expected_add={'acquisition_attempts':1,'acquisition_jobs':1,'acquisition_worker_presence':1,'document_blocks':3,'paper_versions':1,'parse_runs':1}
for table,n in expected_add.items():assert len(after['tables'][table]['rows'])-len(before['tables'][table]['rows'])==n
old_jobs={r['job_id']:r for r in rows(before,'acquisition_jobs')}
new_jobs={r['job_id']:r for r in rows(after,'acquisition_jobs')}
for old_id,row in old_jobs.items():
    new=new_jobs[old_id]
    if old_id!=job_id:assert row==new
    else:
        assert row['status']=='READY' and row['attempts']==5 and row['fencing_token']==5
        fields={k for k in row if row[k]!=new[k]}
        assert fields=={'status','attempts','fencing_token','result_json','updated_at'},fields
target=new_jobs[job_id]
assert target['status']=='SUCCEEDED' and target['attempts']==6 and target['fencing_token']==6
assert target['lease_owner'] is None and target['lease_expires_at'] is None
created_jobs=[new_jobs[k] for k in new_jobs.keys()-old_jobs.keys()]
assert len(created_jobs)==1
quick=created_jobs[0]
assert quick['job_id']=='job_fe4651959298eab54d88abd9edaf6760'
assert quick['job_type']=='QUICK_READ' and quick['status']=='READY' and quick['attempts']==0 and quick['fencing_token']==0
assert quick['collection_id']==collection_id
parse_id=proof['new_actual_publication']['parse_run_id']
assert json.loads(quick['input_json'])=={'parse_run_id':parse_id}
newparse=next(r for r in rows(after,'parse_runs') if r['parse_run_id']==parse_id)
assert newparse['file_version_id']==prepared['original_file_id'] and newparse['status']=='SUCCEEDED'
manifest=json.loads(newparse['artifact_manifest_json'])
q=manifest['quality']
assert q['body_blocks']==3 and q['reference_entries']==6 and q['reference_heading_found']
assert q['reference_page_alignment']['aligned']==6
assert q['reference_page_alignment']['missing_source_numbered_references']==[]
assert q['reference_page_alignment']['numbering_checked']
assert manifest['review_correction_action_ids']==['review_action_c9cf579d1305bd30e9012368443ac386']
source=Path(manifest['source_pdf_path'])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert source.stat().st_size==1827 and sha(source)=='85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99'
blocks=[r for r in rows(after,'document_blocks') if r['parse_run_id']==parse_id]
assert len(blocks)==3 and sum(len(r['text']) for r in blocks)==q['body_text_chars']==204
assert all(r['page_number']==1 for r in blocks)
version=next(r for r in rows(after,'paper_versions') if r['paper_version_id']==proof['new_actual_publication']['paper_version_id'])
assert sha(Path(version['parsed_path']))==version['parsed_digest'] and version['pdf_digest']==sha(source)
parsed=json.loads(Path(version['parsed_path']).read_text(encoding='utf-8'))
assert len(parsed['references'])==6
refs=rows(after,'reference_entries');assert len(refs)==6
assert {r['page_number'] for r in refs}=={2}
assert before['tables']['reference_entries']==after['tables']['reference_entries']
for n in range(1,7):assert sum(r['raw_text'].startswith('['+str(n)+']') for r in refs)==1
context=here/'gpu-health-retry-context-v1'
dom=(context/'05-native-new-parse-fixed-source.dom.txt').read_text(encoding='utf-8')
assert parse_id in dom and '2 parse run(s) · 6 reference entries' in dom
assert 'parse_run_5de840df2a60a2b9d9705d6f92807413' in dom
assert 'QUICK_READ · READY' in dom
successdom=(context/'03-native-gpu-success.dom.txt').read_text(encoding='utf-8')
assert 'SUCCEEDED · g11-single-owned-gpu-health-attempt6' in successdom
assert all(before['tables'][k]==after['tables'][k] for k in before['tables'] if k not in changed)
out={'status':'PASS_ACTUAL_GPU_PARSE_PUBLICATION_NATIVE_READBACK_AND_105_TABLE_AUDIT','gpu_attempt':6,'original_pdf_sha256':sha(source),'parse_run_id':parse_id,'paper_version_id':version['paper_version_id'],'body_blocks':3,'reference_entries':6,'quality':q,'schema_exact':True,'unchanged_tables':len(before['tables'])-len(changed),'old_rows_exact_in_append_tables':True,'old_other_jobs_exact':True,'same_original_reference6_correction_preserved':True,'reference_rows_exact':True,'old_source_and_model_scientific_rows_exact':True,'native_readback_all_tables_exact':True,'spawned_quick_read':{'job_id':quick['job_id'],'status':quick['status'],'attempts':0,'executed':False},'remote_language_model_calls':0,'actual_local_vision_models_executed':True,'cpu_fallback_executed':False,'g11_complete':False,'original118_complete':False,'all11_complete':False,'source_vector':vector}
(here/'actual-gpu-success-final-audit-v1.json').open('x',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in {'quality','source_vector'}},ensure_ascii=False))
