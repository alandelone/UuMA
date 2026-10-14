from pathlib import Path
import copy,hashlib,json,sqlite3,sys,subprocess,collections,difflib
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();sys.path.insert(0,str(repo.parent/'RSTV4/src'))
from rstv4.studio_read_views import generated_version
from pypdf import PdfReader
out=repo/'.tmp/scholar-g01-final-audit-v1';out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
fixture=read(repo/'.tmp/scholar-citation-source-native-v1.json');root=Path(fixture['root']);db=root/'data/catalog.db';db_before=sha(db);ms=fixture['manuscript_id']
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
    tables={r[0]:[dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    versions=[generated_version(conn,root/'data/writing-studio',ms,r['manuscript_version_id']) for r in conn.execute('SELECT * FROM manuscript_versions WHERE manuscript_id=? ORDER BY version',(ms,))]
assert len(tables)==109 and len(versions)==4
before=read(repo/'.tmp/scholar-g01-two-paragraph-before-reorder-v3/all-tables.json');initial=read(repo/'.tmp/scholar-g01-two-paragraph-baseline-tables-v1.json')
after_previous=read(repo/'.tmp/scholar-g01-two-paragraph-after-old-locations/all-tables.json')
for table in before:
    if table not in {'studio_documents','manuscripts','studio_sample_candidates'}:assert all(row in tables[table] for row in before[table]),table
for table in tables:
    if table!='studio_sample_candidates':assert tables[table]==after_previous[table],table
sample_keys=['manuscript_id','anchor_id','query_key','candidate_id']
cache_refreshes=[]
for old in before['studio_sample_candidates']:
    matches=[r for r in tables['studio_sample_candidates'] if all(r[k]==old[k] for k in sample_keys)];assert len(matches)==1
    new=matches[0];changed=[k for k in old if old[k]!=new[k]];assert set(changed)<={'document_revision','created_at'}
    assert new['sample_json']==old['sample_json']
    if changed:cache_refreshes.append({'key':{k:old[k] for k in sample_keys},'changed_fields':changed})
doc3=json.loads(before['studio_documents'][0]['document_json']);doc4=json.loads(tables['studio_documents'][0]['document_json']);doc_initial=json.loads(initial['studio_documents'][0]['document_json'])
alpha,beta=doc3['sections'][0]['paragraphs'];assert alpha['id']=='paragraph_e197b886c810436a823c7171839afac2' and beta['id']=='paragraph_895901de3a694d6f9a4b996e5459feeb'
original=copy.deepcopy(doc3);original['sections'][0]['paragraphs']=[alpha];assert original==doc_initial
expected=copy.deepcopy(doc3);section=expected['sections'][0];section['paragraphs']=[beta,alpha];section['block_order']=[beta['id'],alpha['id']];section['paragraph_groups']=[]
assert expected==doc4
ops=[r for r in tables['studio_operations'] if r not in before['studio_operations']];assert len(ops)==1 and ops[0]['operation_kind']=='MOVE_BLOCKS' and ops[0]['base_revision']==10 and ops[0]['resulting_revision']==11
changes=[r for r in tables['studio_changes'] if r not in before['studio_changes']];assert len(changes)==1 and json.loads(changes[0]['before_json'])==doc3 and json.loads(changes[0]['after_json'])==doc4
assert tables['studio_documents'][0]['revision']==11 and tables['studio_documents'][0]['last_generated_revision']==11 and tables['studio_documents'][0]['active_generated_version_id']==versions[3]['generated_version_id']
assert {k:v for k,v in before['manuscripts'][0].items() if k not in {'revision','updated_at'}}=={k:v for k,v in tables['manuscripts'][0].items() if k not in {'revision','updated_at'}}
assert tables['manuscripts'][0]['workflow_stage']=='WHOLE_PAPER_REVIEW'
v3,v4=versions[2:];p3=[b for b in v3['blocks'] if b['kind']=='paragraph'];p4=[b for b in v4['blocks'] if b['kind']=='paragraph']
assert v3['input_revision']==10 and v4['input_revision']==11
assert [b['object_id'] for b in p3]==[alpha['id'],beta['id']] and [b['object_id'] for b in p4]==[beta['id'],alpha['id']]
assert [b['display_text'] for b in p3]==['First source [1]. Next [2]. Repeat [1].','Beta software paragraph cites original page 1 [2] and additional source [1].']
assert [b['display_text'] for b in p4]==['Beta software paragraph cites original page 1 [1] and additional source [2].','First source [2]. Next [1]. Repeat [2].']
assert [r['evidence_id'] for r in v3['references']]==list(reversed([r['evidence_id'] for r in v4['references']]))
assert tables['studio_chat_messages']==before['studio_chat_messages'] and tables['research_discussion_messages']==before['research_discussion_messages'] and tables['research_discussion_jobs']==before['research_discussion_jobs']
assert len(tables['studio_chat_messages'])==9 and len(tables['studio_model_calls'])==11 and len(tables['research_discussion_jobs'])==5
counts=dict(collections.Counter(r['status'] for r in tables['studio_model_calls']));assert counts=={'VALIDATED':6,'REJECTED':1,'RETURNED':4}
new_calls=[r for r in tables['studio_model_calls'] if r not in initial['studio_model_calls']];assert len(new_calls)==6
assert all(json.loads(r['contract_json'])['actual_model']=='TEST_FIXTURE_G01_NATIVE' for r in new_calls)
assert len(tables['studio_jobs'])==4 and all(r['status']=='SUCCEEDED' for r in tables['studio_jobs'])
assert all(r['status'] in {'COMPLETE','FAILED'} for r in tables['research_discussion_jobs'])
artifacts=[]
for artifact in tables['studio_artifacts']:
    path=Path(artifact['storage_path']);assert path.is_relative_to(root) and path.stat().st_size==artifact['size_bytes'] and sha(path)==artifact['sha256']
    artifacts.append({'id':artifact['artifact_id'],'kind':artifact['artifact_kind'],'revision':artifact['document_revision'],'path':str(path),'sha256':artifact['sha256'],'bytes':artifact['size_bytes']})
assert len(artifacts)==20
pdfs={}
for revision in [10,11]:
    artifact=next(r for r in tables['studio_artifacts'] if r['document_revision']==revision and r['artifact_kind']=='PDF');reader=PdfReader(artifact['storage_path']);assert len(reader.pages)==1
    text=' '.join(reader.pages[0].extract_text().split());assert '[@evidence_' not in text
    pdfs[str(revision)]={'pages':len(reader.pages),'text':text,'sha256':artifact['sha256']}
proof=repo/'.tmp/scholar-g01-two-paragraph-native-proof-v1'
for name,text in [('final-alpha-old-v3-highlight.dom.txt','mark: First source [1]. Next [2]. Repeat [1].'),('final-beta-old-v3-highlight.dom.txt','mark: Beta software paragraph cites original page 1 [2] and additional source [1].'),('alpha-old-v3-after-refresh.dom.txt','mark: First source [1]. Next [2]. Repeat [1].'),('beta-old-v3-after-refresh.dom.txt','mark: Beta software paragraph cites original page 1 [2] and additional source [1].')]:assert text in (proof/name).read_text(encoding='utf-8'),name
assert '[@evidence_' in (proof/'before-fix-loading-internal-ids.txt').read_text(encoding='utf-8')
loading=(proof/'after-fix-loading-no-internal-ids.txt').read_text(encoding='utf-8');assert '正在读取此成文版本' in loading and '[@evidence_' not in loading
finaldom=(proof/'final-current-v4-beta-v3-source.dom.txt').read_text(encoding='utf-8');assert 'button "📚 evidence_' not in finaldom and '查看此回复的第 1 个引用来源' in finaldom
assert v3['generated_version_id']+'/sources/evidence_6b169de2b78d452f919391b00916f2c8/pdf#page=1' in finaldom
oldseal=read(repo/'.tmp/scholar-citation-source-seal-v1.json');oldreport=Path(oldseal['directory']);oldmanifest=read(oldreport/'manifest.json')
assert len(oldmanifest['files'])==207 and all(sha(oldreport/p)==digest for p,digest in oldmanifest['files'].items())
current_source={p:sha(Path(p)) for p in oldmanifest['current_source_sha256']};changed_source=[p for p in current_source if current_source[p]!=oldmanifest['current_source_sha256'][p]]
assert len(changed_source)==1 and Path(changed_source[0])==repo.parent/'writing-studio/components/studio-workspace.tsx'
oldfront=oldreport/'source-after/writing-studio/components/studio-workspace.tsx';newfront=Path(changed_source[0]);assert sha(oldfront)==oldmanifest['current_source_sha256'][changed_source[0]]
(out/'frontend-display-change.patch').write_text(''.join(difflib.unified_diff(oldfront.read_text(encoding='utf-8').splitlines(True),newfront.read_text(encoding='utf-8').splitlines(True),fromfile='source-before/studio-workspace.tsx',tofile='source-after/studio-workspace.tsx')),encoding='utf-8')
assert all(r['exit_code']==0 for r in read(repo/'.tmp/scholar-g01-loading-front-v1.json'))
build=read(repo/'.tmp/scholar-g01-loading-build-v1.json');assert build['status']=='PASS' and build['original_source_and_dist_unchanged']
assert sha(Path(build['root'])/'components/studio-workspace.tsx')==sha(newfront)
scope=(repo/'docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md').read_text(encoding='utf-8')
import re
requirements=[x for x in scope.splitlines() if re.match(r'^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+',x)];groups=[x for x in scope.splitlines() if re.match(r'^\|\s*G-\d+',x)];assert len(requirements)==118 and len(groups)==11
runtime=read(repo/'.tmp/scholar-g01-loading-runtime-refresh-v1.json');process_ids=[p['ProcessId'] for p in runtime['new_verified_port3008_chain']]+[104836,104544]
ps='Get-CimInstance Win32_Process -Filter "'+ ' OR '.join('ProcessId='+str(p) for p in process_ids)+'" | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json -Depth 3'
processes=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',ps],encoding='utf-8-sig'))
assert set(process_ids)=={p['ProcessId'] for p in processes}
for saved in runtime['new_verified_port3008_chain']:assert saved==next(p for p in processes if p['ProcessId']==saved['ProcessId'])
ports=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command','Get-NetTCPConnection -State Listen | Select-Object LocalPort,OwningProcess | ConvertTo-Json'],encoding='utf-8-sig'))
assert not any(p['LocalPort'] in [3000,3004,3005,3006,3007] for p in ports)
assert any(p['LocalPort']==3008 and p['OwningProcess']==111168 for p in ports) and any(p['LocalPort']==8881 and p['OwningProcess']==104544 for p in ports)
assert sha(db)==db_before
receipt={'status':'PASS_G01_ORIGINAL_TWO_PARAGRAPH_NATIVE_ACCEPTANCE','previous_goal_turn':'PROGRESS','original_requirements':118,'original_groups':11,'g01_original_definition':groups[0],'g01_software_native_acceptance':True,'all11_complete':False,'database_read_only_and_physical_bytes_exact':True,'initial_alpha_author_content_exact':True,'r10_to_r11_only_move_and_explicit_empty_groups_block_order':True,'one_actual_ui_move_operation':ops[0]['operation_id'],'original_v3_messages_calls_versions_artifacts_exact':True,'all109tables_audited':True,'sample_cache_changes_only_revision_and_timestamp':cache_refreshes,'four_versions':[v['generated_version_id'] for v in versions],'model_call_status_counts':counts,'new_g01_model_calls':6,'new_g01_calls_explicit_software_fixture':True,'one_original_actual_gemini_rejection_retained':True,'new_backend_source_changes':False,'changed_frontend_source':changed_source,'current_source_sha256':current_source,'all20artifact_bytes_exact':artifacts,'new_pdf_text':pdfs,'prior207files_exact':True,'current_owned_processes':processes,'obsolete_preview_ports_still_closed':True}
(out/'all-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8');(out/'generated-versions.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2),encoding='utf-8');(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'sample_cache_changes_only_revision_and_timestamp','all20artifact_bytes_exact','current_source_sha256','current_owned_processes','new_pdf_text'}},ensure_ascii=False),flush=True)
