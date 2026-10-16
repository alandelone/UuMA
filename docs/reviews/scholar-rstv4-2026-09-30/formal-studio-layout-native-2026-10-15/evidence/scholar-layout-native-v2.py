"""Continue exact native r85/round4; correct only the acceptance job request field."""
from pathlib import Path
from copy import deepcopy
repo=Path(__file__).resolve().parents[1]
code=(repo/'.tmp/scholar-layout-native-v1.py').read_text(encoding='utf8')
code=code[:code.index("if __name__=='__main__':{'prepare':prepare_layout")]
code=code.replace('scholar-layout-native-v1','scholar-layout-native-v2').replace("body.get('job_kind')","body.get('kind')")
exec(compile(code,__file__,'exec'))
ROUND='review_round_72931d507bda4bdb813dc14988444892'
def prepare_continue():
    HERE.mkdir(exist_ok=True)
    assert not any(HERE.iterdir()), 'Retain any prepared runtime; never overwrite receipts'
    previous=REPO/'.tmp/scholar-layout-native-v1'
    assert read(previous/'owned-stop-terminal.json')['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    r=read(previous/'receipt.json');root=Path(r['root']);before=snap(root/'data/catalog.db')
    assert before==read(previous/'backend-terminal.json')['copy_final_all_tables']
    doc=next(x for x in records(before,'studio_documents') if x['manuscript_id']==MS)
    manuscript=next(x for x in records(before,'manuscripts') if x['manuscript_id']==MS)
    original=read(previous/'source-v6-author79.json')
    assert doc['revision']==85 and doc['last_generated_revision']==79 and json.loads(doc['document_json'])==original
    assert not (previous/'layout-generate-post-once.json').exists() and not (previous/'layout-package-post-once.json').exists()
    assert next(x for x in records(before,'studio_review_round_baselines') if x['review_round_id']==ROUND)['baseline_manuscript_version_id']==SOURCE
    assert len([x for x in records(before,'review_comments') if x['review_round_id']==ROUND])==1
    source=read(previous/'before110-all-tables.json')
    for table in ['studio_model_calls','studio_jobs','manuscript_versions','studio_artifacts','studio_response_checks']:
        assert before['tables'][table]==source['tables'][table],table
    expected=deepcopy(original);expected['layout']={'page_margin':'narrow'}
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    r.update(status='SAME_R85_EXISTING_ROUND4_REQUEST_FIELD_CONTEXT_CORRECTED',frontend_port=port,expected_document_revision=85,
             expected_workflow_revision=manuscript['revision'],stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r);write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('source-v6-author79.json',original);write('allowed-author-documents.json',[original,expected])
    for name in ['new-round-post-once.json','new-import-post-once.json']:write(name,read(previous/name))
    write('reuse-preflight.json',{'same_root':str(root),'current_author85_equals_fixed_v6_author79':True,'original_source_v6':SOURCE,
                                'all_existing_jobs_models_versions_artifacts_checks_exact':True,'new_round_or_import_replayed':False,
                                'old_guard_key_job_kind_corrected_to_shipped_API_kind_before_first_job_submission':True,
                                'one_new_layout_job_and_one_package_allowed_only':True,'models_workers_gpu':0,
                                'backend_source_count':len(r['backend_source_vector']),'frontend_source_count':len(r['frontend_product_vector']),
                                'frontend_dist_count':len(r['frontend_dist_vector'])})
    print(json.dumps({'status':'PREPARED_SAME_R85_NO_JOB_REPLAY','frontend_port':port}))
if __name__=='__main__':{'prepare':prepare_continue,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
