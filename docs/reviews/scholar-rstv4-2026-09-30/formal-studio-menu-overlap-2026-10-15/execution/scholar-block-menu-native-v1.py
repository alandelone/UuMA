"""Same preserved r81/v6 fixture, new two-file menu build; no jobs or models."""
from pathlib import Path
import json,socket,uuid
repo=Path(__file__).resolve().parents[1]
code=(repo/'.tmp/scholar-studio-current-native-restart-v10.py').read_text(encoding='utf8')
code=code[:code.index("if __name__=='__main__'")]
code=code.replace("HERE=REPO/'.tmp/scholar-studio-current-native-restart-v10'","HERE=REPO/'.tmp/scholar-block-menu-native-v1'")
needle="        if not allowed:return JSONResponse"
assert code.count(needle)==1
code=code.replace(needle,"        allowed=(method=='PUT' and path==base+'/document') or (method=='POST' and path in {'/api/research/discussion/context','/api/research/discussion/history'})\n"+needle)
code=code.replace("['GET','HEAD','POST','PATCH','DELETE','OPTIONS']","['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS']")
code=code.replace("workspace['document_revision']==workspace['last_generated_revision']==62","workspace['document_revision']==r['expected_document_revision'] and workspace['last_generated_revision']==r['expected_generated_revision']")
code=code.replace("workspace['manuscript']['revision']==6","workspace['manuscript']['revision']==r['expected_workflow_revision']")
code=code.replace('scui-publication-chain-build-mlpu7aqn','scui-block-menu-build-mjllkr43')
code=code.replace("str(REPO/'.tmp/scholar-studio-current-native-restart-v10-stop-owned.py')","str(REPO/'.tmp/scholar-block-menu-native-v1-stop.py')")
exec(compile(code,__file__,'exec'))
ROUND='review_round_e4845ca796d74594b33b86fb529b4404'
def prepare_menu():
    HERE.mkdir(exist_ok=False)
    previous=REPO/'.tmp/scholar-complex-native-runtime-v1'
    assert read(previous/'owned-stop-terminal.json')['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
    assert read(REPO/'.tmp/scholar-complex-native-seal-v1.json')['status']=='SEALED_BOUNDED_COMPLEX_NATIVE_NOT_ALL11'
    r=read(previous/'receipt.json');root=Path(r['root'])
    before=snap(root/'data/catalog.db')
    assert before==read(REPO/'.tmp/scholar-complex-stale-freeze-v1/after110.json')
    document=next(x for x in records(before,'studio_documents') if x['manuscript_id']==MS)
    manuscript=next(x for x in records(before,'manuscripts') if x['manuscript_id']==MS)
    assert document['revision']==81 and document['last_generated_revision']==79
    build=read(REPO/'.tmp/scholar-block-menu-build-v1.json');assert build['status']=='PASS'
    built=Path(build['root'])
    vector={n:sha(REPO.parent/'writing-studio'/n) for n in r['frontend_product_vector']}
    assert {n for n,h in r['frontend_product_vector'].items() if vector[n]!=h}=={'app\\globals.css','components\\studio-workspace.tsx'}
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    r.update(status='SAME_R81_V6_FIXTURE_MENU_ONLY_SOURCE_FIX',frontend_root=str(built),frontend_port=port,frontend_product_vector=vector,frontend_dist_vector=build['dist_files'],active_generated_version_id=document['active_generated_version_id'],expected_document_revision=81,expected_generated_revision=79,expected_workflow_revision=manuscript['revision'],stop_nonce=uuid.uuid4().hex,stop_file=str(HERE/'stop.request.json'))
    guard(r)
    write('receipt.json',r);write('before110-all-tables.json',before);write('before110-all-files.json',filemap(root))
    write('reuse-preflight.json',{'same_root_preserved':str(root),'exact_previous_terminal110':True,'new_copies_or_schema_or_jobs_or_models':0,'only_frontend_menu_two_files_changed':True,'real_new_build':True,'expected_document_revision':81,'expected_generated_revision':79})
    write('previous-owned-identity-audit.json',read(previous/'owned-stop-terminal.json'))
    print(json.dumps({'status':'PREPARED_MENU_FIX_SAME_R81_V6','frontend_port':port,'build':str(built)}))
if __name__=='__main__':{'prepare':prepare_menu,'launch':launch,'serve':serve,'stop':stop}[sys.argv[1]]()
