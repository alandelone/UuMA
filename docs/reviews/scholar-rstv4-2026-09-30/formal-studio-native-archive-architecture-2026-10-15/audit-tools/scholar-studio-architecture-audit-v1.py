from pathlib import Path
import hashlib,json,os,re,subprocess,sys
repo=Path(__file__).resolve().parents[1]
rst=repo.parent/'RSTV4';front=repo.parent/'writing-studio'
here=repo/'.tmp/scholar-studio-architecture-v1'
here.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(n,v):
    with (here/n).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
r=read(repo/'.tmp/scholar-studio-current-native-restart-v5/receipt.json')
build=Path(r['frontend_root'])
for n,h in r['backend_source_vector'].items():assert sha(rst/n)==h,n
for n,h in r['frontend_product_vector'].items():
    assert sha(front/n)==h and sha(build/n)==h,n
for n,h in r['frontend_dist_vector'].items():assert sha(build/n)==h,n
source=[p for d in ['app','components','lib'] for p in (front/d).rglob('*') if p.is_file() and p.suffix in {'.ts','.tsx','.js','.jsx','.css'}]
assert {str(p.relative_to(front)) for p in source}==set(r['frontend_product_vector'])
shared=rst/'src/rstv4/catalog_research_chat.js'
paths=[p for p in source if p.suffix!='.css']+[shared]
inputs={'files':[{'relative':str(p.relative_to(front)) if front in p.parents else '../RSTV4/src/rstv4/'+p.name,'path':str(p)} for p in paths]}
put('ast-input.json',inputs)
parser=repo/'.tmp/scholar-studio-architecture-scan-v1.cjs'
result=subprocess.run(['node',str(parser),str(here/'ast-input.json'),str(here/'ast-results.json')],capture_output=True,text=True,check=True)
ast=read(here/'ast-results.json')
assert all(not x['parse_diagnostics'] for x in ast['files'])
runtime_imports=sorted({i['module'] for f in ast['files'] for i in f['imports'] if not i['type_only']})
forbidden_import=re.compile(r'(^|[/@-])(sqlite3?|better-sqlite3|sql\.js|duckdb|prisma|pg|mysql2?|mongodb|openai|anthropic|google-generativeai)([/@-]|$)|^node:(net|tls|sqlite|child_process)$',re.I)
assert not [i for i in runtime_imports if forbidden_import.search(i)]
env=[{'file':f['file'],**e} for f in ast['files'] for e in f['env']]
assert {e['name'] for e in env}<={'NEXT_PUBLIC_RSTV4_API','NEXT_PUBLIC_PAPER_CATALOG_URL','RSTV4_API'}
calls=[{'file':f['file'],**c} for f in ast['files'] for c in f['calls']]
network=[c for c in calls if re.search(r'fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|axios|Worker',c['callee'],re.I)]
direct=[c for c in network if c['callee'] in {'fetch','fetchFile'}]
assert {(x['file'],x['callee']) for x in direct}=={('lib\\studio-api.ts','fetch'),('lib\\studio-downloads.ts','fetchFile')}
dangerous=[c for c in calls if c['callee'] in {'eval','Function','new Function'} or re.search(r'XMLHttpRequest|WebSocket|EventSource|sendBeacon|axios|Worker',c['callee'],re.I)]
assert not dangerous,dangerous
client=[build/n for n in r['frontend_dist_vector'] if Path(n).parts[:2]==('dist','client')]
assert len(client)==23
text_files=[p for p in client if p.suffix in {'.js','.json','.css','.svg','.html','.map'}]
active_key=os.environ.get('ROUTER_API_KEY','local-router').encode()
markers=[rb'ROUTER_API_KEY',rb'UNLIMITED_LLMAPI_BASE_URL',rb'api\.95963210\.xyz',rb'/chat/completions',rb'better-sqlite3',rb'node:sqlite',rb'sqlite3\.Database',rb'postgres(?:ql)?://',rb'mongodb(?:\+srv)?://',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
scans=[]
for p in client:
    raw=p.read_bytes()
    found=[pattern.decode() for pattern in markers if re.search(pattern,raw,re.I)]
    has_key=bool(active_key and active_key in raw)
    assert not found and not has_key, 'Forbidden client marker or configured credential in '+p.name
    scans.append({'file':str(p.relative_to(build)),'bytes':len(raw),'sha256':sha(p),'forbidden_marker_matches':found,'configured_gateway_key_present':has_key})
package=read(front/'package.json')
assert not [k for k in package.get('dependencies',{}) if forbidden_import.search(k)]
api=(front/'lib/studio-api.ts').read_text(encoding='utf-8')
assert "fetch(`${API_BASE}${path}`" in api
assert "headers.set('Content-Type', 'application/json')" in api
assert 'Authorization' not in api and 'Bearer' not in api
assert 'base_revision: baseRevision' in api and 'operation_id: operationId' in api
offline=(front/'lib/offline-outbox.ts').read_text(encoding='utf-8')
assert "const STORE = 'pending-saves'" in offline and 'baseRevision: number' in offline
assert 'localStorage' in offline and 'indexedDB.open(DB_NAME, 1)' in offline
proxy=(front/'lib/studio-downloads.ts').read_text(encoding='utf-8')
assert "base.username || base.password" in proxy and "!['127.0.0.1', 'localhost'].includes(base.hostname)" in proxy
assert "redirect: 'error'" in proxy
put('runtime-imports.json',runtime_imports)
put('network-call-sites.json',network)
put('environment-references.json',env)
put('client-assets-scan.json',scans)
put('source-91.json',r['frontend_product_vector'])
put('dist-76.json',r['frontend_dist_vector'])
put('backend-source-311.json',r['backend_source_vector'])
put('boundary-inputs.json',{str(p):sha(p) for p in [front/'package.json',front/'vite.config.ts',shared,parser]})
evidence={}
for p,a,b in [(front/'lib/studio-api.ts',28,88),(front/'lib/studio-api.ts',96,133),(front/'lib/offline-outbox.ts',3,19),(front/'lib/offline-outbox.ts',32,61),(front/'lib/studio-downloads.ts',30,57),(front/'app/api/studio-files/[...path]/route.ts',1,8),(rst/'src/rstv4/studio_api.py',348,359),(rst/'src/rstv4/studio.py',609,676),(rst/'src/rstv4/model_gateway.py',168,179)]:
    key=f'{p}:{a}-{b}'
    evidence[key]='\n'.join(f'{i+1}: {line}' for i,line in enumerate(p.read_text(encoding='utf-8').splitlines()) if a<=i+1<=b)
put('reviewed-boundary-source-excerpts.json',evidence)
for n,h in r['backend_source_vector'].items():assert sha(rst/n)==h,n
for n,h in r['frontend_product_vector'].items():assert sha(front/n)==h and sha(build/n)==h,n
for n,h in r['frontend_dist_vector'].items():assert sha(build/n)==h,n
receipt={'status':'PASS_CURRENT_BUILD_ST01_STATIC_ARCHITECTURE_BOUNDARY_NOT_NATIVE_FINAL_FLOW',
 'frontend_product_files':91,'frontend_dist_files':76,'backend_files':311,
 'typescript_parsed_files_including_shared_controller':len(ast['files']),
 'client_assets_scanned_all_bytes':len(client),'client_text_assets':len(text_files),
 'runtime_imports_count':len(runtime_imports),'direct_network_calls':direct,
 'no_direct_vendor_db_or_model_sdk_imports':True,'no_configured_gateway_credential_in_client_assets':True,
 'no_model_provider_endpoint_or_secret_env_names_in_client_assets':True,
 'browser_local_indexeddb_is_pending_save_outbox_not_authoritative_backend_db':True,
 'authority': 'browser API request with manuscript/base revision/operation ID -> FastAPI -> StudioService.save_document transaction',
 'fixed_file_proxy_restricts_loopback_api_no_credentials_redirect_error':True,
 'three_frozen_vectors_unchanged_before_after':True,'model_network_calls':0,'browser_actions':0,
 'db_or_business_mutations':0,'new_servers':0,'new_builds':0,'new_tests_or_full_repeats':0,
 'remaining':'Track/Paper/manuscript same-ID final native integration remains; static audit is not blanket security certification or final11 acceptance',
 'overall118_complete':False,'final_all11_integrated_complete':False}
put('receipt.json',receipt)
print(json.dumps(receipt,ensure_ascii=False))
