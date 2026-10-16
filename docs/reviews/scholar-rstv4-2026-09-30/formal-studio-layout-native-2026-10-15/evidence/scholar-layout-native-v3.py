"""Read the original successful v7 after apostrophe/toolbar fixes; no generation."""
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=(repo/'.tmp/scholar-layout-native-v1.py').read_text(encoding='utf8')
code=code[:code.index("if __name__=='__main__':{'prepare':prepare_layout")]
code=code.replace('scholar-layout-native-v1','scholar-layout-native-v3').replace("body.get('job_kind')","body.get('kind')")
assert code.count("body.get('kind')=='GENERATE'")==1
code=code.replace("body.get('kind')=='GENERATE'","body.get('kind')=='GENERATE' and False")
assert "body.get('kind')=='GENERATE' and False" in code
exec(compile(code,__file__,'exec'))
ROUND='review_round_72931d507bda4bdb813dc14988444892'
def prepare_readback():
    HERE.mkdir(exist_ok=False)
    previous=REPO/'.tmp/scholar-layout-native-v2'
    assert read(previous/'owned-stop-terminal.json')['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    r=read(previous/'receipt.json');root=Path(r['root']);before=snap(root/'data/catalog.db')
    assert before==read(previous/'backend-terminal.json')['copy_final_all_tables']
    doc=next(x for x in records(before,'studio_documents') if x['manuscript_id']==MS)
    manuscript=next(x for x in records(before,'manuscripts') if x['manuscript_id']==MS)
    assert doc['revision']==doc['last_generated_revision']==86
    assert doc['active_generated_version_id']=='manuscript_version_8732ec9497074d82ae2b4359a7c235e5'
    baseline=read(previous/'before110-all-tables.json')
    assert before['tables']['studio_model_calls']==baseline['tables']['studio_model_calls']
    assert before['tables']['studio_response_checks']==baseline['tables']['studio_response_checks']
    assert (previous/'layout-generate-post-once.json').exists() and not (previous/'layout-package-post-once.json').exists()
    changes={'src/rstv4/studio_revision_mapping.py','tests/test_studio_revision_mapping.py'}
    current={n:sha(RST/n) for n in r['backend_source_vector']}
    assert {n for n,h in r['backend_source_vector'].items() if current[n]!=h}==changes
    vector={n:sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']}
    assert {n for n,h in r['frontend_product_vector'].items() if vector[n]!=h}=={'app\\globals.css','components\\studio-workspace.tsx'}
    build=read(REPO/'.tmp/scholar-layout-build-v2.json');assert build['status']=='PASS'
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    r.update(status='SAME_SUCCESSFUL_V7_NO_GENERATION_ALLOWED_APOSTROPHE_AND_TOOLBAR_FIX',frontend_port=port,
             frontend_root=str(Path(build['root']).resolve()),frontend_dist_vector=build['dist_files'],frontend_product_vector=vector,backend_source_vector=current,
             active_generated_version_id=doc['active_generated_version_id'],expected_document_revision=86,expected_generated_revision=86,
             expected_workflow_revision=manuscript['revision'],stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r);write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    write('source-v6-author79.json',read(previous/'source-v6-author79.json'));write('allowed-author-documents.json',[json.loads(doc['document_json'])])
    for name in ['new-round-post-once.json','new-import-post-once.json','layout-generate-post-once.json']:write(name,read(previous/name))
    write('reuse-preflight.json',{'same_root':str(root),'same_successful_v7_and_author86':True,'original_v6_v7_PDFs_and_generated_versions_retained':True,
                                'all_model_calls_and_checks_exact':True,'generation_denied_entirely':True,'old_single_submission_marker_preserved':True,
                                'one_new_package_only':True,'only_two_backend_and_two_frontend_followup_files_changed':True,
                                'backend_source_count':len(current),'frontend_source_count':len(vector),'frontend_dist_count':len(build['dist_files'])})
    print(json.dumps({'status':'PREPARED_SAME_SUCCESSFUL_V7_NO_GENERATION','frontend_port':port}))
if __name__=='__main__':{'prepare':prepare_readback,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
