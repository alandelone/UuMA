"""Final CSS-only package readback; all execution and document mutation denied."""
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
runtime_source=(repo/'.tmp/scholar-layout-native-v1.py').read_text(encoding='utf8')
runtime_source=runtime_source[:runtime_source.index("if __name__=='__main__':{'prepare':prepare_layout")]
runtime_source=runtime_source.replace('scholar-layout-native-v1','scholar-layout-native-v4')
needle="        if not allowed:return JSONResponse"
assert runtime_source.count(needle)==1
runtime_source=runtime_source.replace(needle,"        allowed=method=='POST' and path in {'/api/research/discussion/context','/api/research/discussion/history'}\n"+needle)
exec(compile(runtime_source,__file__,'exec'))
ROUND='review_round_72931d507bda4bdb813dc14988444892'
def prepare_final_readback():
    HERE.mkdir(exist_ok=True);previous=REPO/'.tmp/scholar-layout-native-v3'
    assert not any(HERE.iterdir()), 'Never overwrite a prepared runtime'
    assert read(previous/'owned-stop-terminal.json')['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    r=read(previous/'receipt.json');root=Path(r['root']);before=snap(root/'data/catalog.db')
    assert before==read(previous/'backend-terminal.json')['copy_final_all_tables']
    audited=read(REPO/'.tmp/scholar-layout-package-audit-v1/after110-all-tables.json')
    assert {n for n in before['tables'] if before['tables'][n]!=audited['tables'][n]}=={'studio_sample_candidates'}
    prior_candidates=records(audited,'studio_sample_candidates');current_candidates=records(before,'studio_sample_candidates')
    key=lambda value:canon({k:v for k,v in value.items() if k not in {'created_at','document_revision'}})
    assert sorted(map(key,prior_candidates))==sorted(map(key,current_candidates))
    old_by_key={key(v):v for v in prior_candidates}
    cache_refresh=[{'identity':{k:v for k,v in value.items() if k not in {'created_at','sample_json'}},'old_document_revision':old_by_key[key(value)]['document_revision'],'new_document_revision':value['document_revision'],'old_created_at':old_by_key[key(value)]['created_at'],'new_created_at':value['created_at']}
                   for value in current_candidates if value['created_at']!=old_by_key[key(value)]['created_at']]
    assert len(cache_refresh)==4 and all(v['old_document_revision']==85 and v['new_document_revision']==86 and v['identity']['anchor_id']=='paper' and v['identity']['manuscript_id']==MS for v in cache_refresh)
    assert all(sha(RST/n)==h for n,h in r['backend_source_vector'].items())
    vector={n:sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']}
    assert {n for n,h in r['frontend_product_vector'].items() if vector[n]!=h}=={'app\\globals.css'}
    raw=(REPO/'.tmp/scholar-layout-package-wrap-v1/before.css').read_text(encoding='utf8')
    added='.submission-package li > button { max-width: 100%; height: auto; white-space: normal; overflow-wrap: anywhere; text-align: left; justify-content: flex-start; }\n'
    needle='.submission-package li { min-width: 0; display: grid; justify-items: start; }\n'
    assert raw.count(needle)==1
    assert (REPO.parent/'writing-studio/app/globals.css').read_text(encoding='utf8')==raw.replace(needle,needle+added)
    full=read(REPO/'.tmp/scholar-layout-full-v2/receipt.json');assert full['status']=='PASS' and not full['changed_during_run']
    source=read(Path(full['source_before']))
    changed={n for n,h in source.items() if sha(Path(n))!=h}
    assert changed=={str(REPO.parent/'writing-studio/app/globals.css')}
    build=read(REPO/'.tmp/scholar-layout-build-v3.json');assert build['status']=='PASS'
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    r.update(status='SAME_V7_AND_EXISTING_PACKAGE_FINAL_CSS_READONLY',frontend_port=port,frontend_root=str(Path(build['root']).resolve()),
             frontend_dist_vector=build['dist_files'],frontend_product_vector=vector,stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r);write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('declared-four-sample-cache-revision-time-refreshes.json',{'all_other109_tables_exact':True,'all16_sample_contents_and_identities_exact':True,'exactly_eight_changed_cells':cache_refresh,'source':'native structure view opened Samples during actual760 toolbar verification','first_timestamp_only_hypothesis_failed_and_retained':True})
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('source-v6-author79.json',read(previous/'source-v6-author79.json'));write('allowed-author-documents.json',[])
    write('reuse-preflight.json',{'same_v7_and_existing21_file_package':True,'backend314_exact_to_full1178':True,'full24JS_and_Ruff_pass':True,
                                'only_final_CSS_wrap_rule_since_full_frozen414':True,'all_jobs_models_document_mutations_denied':True,
                                'new_actual_production_build':str(Path(build['root']).resolve()),'source_count':len(source),'all110_and_old_files_preserved':True,
                                'native_package_grid_readback_pending':True})
    print(json.dumps({'status':'PREPARED_EXISTING_V7_PACKAGE_READONLY','frontend_port':port}))
if __name__=='__main__':{'prepare':prepare_final_readback,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
