"""Verify actual annotation initialization and exact owned native deltas."""
from pathlib import Path
import hashlib,json,sqlite3
from datetime import datetime,timezone
repo=Path(__file__).resolve().parents[1]
load=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
diag=load(repo/'.tmp/scholar-g10-native-v1/schema-diagnostic-v2.json')
added={'research_discussion_jobs':0,'research_discussion_requests':1,
       'research_discussion_messages':0,'research_discussion_annotations':1}
assert diag['tables']==109 and diag['added']==added and not diag['removed']
out=repo/'.tmp/scholar-g10-native-v1/final-audit-v2';out.mkdir()
context=out/'context';context.mkdir()
(context/'failed-audit-v1.py').write_bytes((repo/'.tmp/scholar-g10-native-audit-v1.py').read_bytes())
note='''

2026-10-13 G10 final native audit context: initial frozen copy had105tables.
First real research annotation initializes the shipped research_discussions SCHEMA,
adding exactly4tables: requests1/annotations1/messages0/jobs0, now109. Failed v1
assumed initial105 after native use; retained raw helper and RO diagnostic. Verify
the exact four names/counts, all old105 data rows, known native append records and
exact sqlite_sequence increments12->13 plus annotation1. This is initializer and
bookkeeping context, not permission to relax data preservation, invent rows or
rerun any successful UI/model/terminal fullsuite. Keep source-original/G09 raw
DB hashes and original SEALED Snapshot fully identical. G10 only its unchanged
original software group scope; original118 and full11/science remain incomplete.
'''
for name in ['repomemory/findings.md','rules/testing-contracts.md']:
    p=repo/name;(context/(p.name+'.prior.raw')).write_bytes(p.read_bytes())
    with p.open('a',encoding='utf-8',newline='') as f:f.write(note)
info=load(repo/'.tmp/scholar-g10-native-v1/prepared-existing-copy/receipt.json')
before=load(repo/'.tmp/scholar-g10-native-v1/prepared-existing-copy/all-tables.json')
db=Path(info['root'])/'data/catalog.db'
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
    now={r[0]:[dict(v) for v in c.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
         for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
assert len(now)==109 and set(now)-set(before)==set(added) and set(before)<=set(now)
for name,count in added.items():assert len(now[name])==count
key=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True)
for name,rows in before.items():
    if name=='sqlite_sequence':continue
    assert all(key(r) in {key(v) for v in now[name]} for r in rows),name
    if name in diag['changed']:assert now[name]==diag['changed'][name]['current'],name
    else:assert now[name]==rows,name
assert before['sqlite_sequence']==[{'name':'research_workspace_actions','seq':12}]
assert now['sqlite_sequence']==[{'name':'research_workspace_actions','seq':13},{'name':'research_discussion_annotations','seq':1}]
assert set(diag['changed'])=={'manuscript_status_history','manuscripts','research_workspace_actions','sqlite_sequence',
    'studio_change_link_state','studio_changes','studio_documents','studio_operations','studio_sample_candidates','track_snapshot_adoptions'}
ms='manuscript_14aef3be6a534016bf456a15dc865892';track=info['track_id']
assert len(now['manuscripts'])==1 and now['manuscripts'][0]['manuscript_id']==ms
assert now['manuscripts'][0]['track_id']==track and now['manuscripts'][0]['workflow_stage']=='DRAFTING'
assert now['manuscripts'][0]['revision']==1
assert len(now['studio_documents'])==1 and now['studio_documents'][0]['revision']==2
assert now['studio_documents'][0]['active_generated_version_id'] is None
doc=json.loads(now['studio_documents'][0]['document_json'])
thought=doc['sections'][0]['paragraphs'][0]['intents'][0]['thoughts'][0]
assert thought['id']=='thought_0face25a110649c8a6ba51a69d0ebc91'
assert thought['text']=='G10 software source roundtrip only: retain the original source and its recorded conditions; no scientific claim is asserted.'
assert thought['citation_mode']=='PENDING' and thought['citations'][0]['selected'] is False
assert thought['citations'][0]['evidence_id']=='evidence_a6ebbc126275f8d012c2d65da2946832'
assert [r['operation_kind'] for r in now['studio_operations']]==['EDIT','ADD_CITATION_CANDIDATE']
assert [(r['base_revision'],r['resulting_revision']) for r in now['studio_operations']]==[(0,1),(1,2)]
assert len(now['track_snapshot_adoptions'])==1 and now['track_snapshot_adoptions'][0]['track_id']==track
assert now['track_snapshot_adoptions'][0]['snapshot_id']==info['snapshot_id']
assert json.loads(now['research_workspace_actions'][-1]['request_json'])['operation']=='ADOPT_SNAPSHOT'
annotation=now['research_discussion_annotations'][0]
assert annotation['comment']=='G10 software source audit: retain this exact original unit, its page 3 and fixed Paper/Skeleton version. File and parse versions are unrecorded; do not infer scientific approval.'
assert now['research_discussion_requests'][0]['request_id']==annotation['request_id']
assert not now['research_discussion_jobs'] and not now['research_discussion_messages']
assert sha(Path(info['source_root'])/'data/catalog.db')==info['source_db_sha256']
g09=Path('C:/Users/Alandelone/AppData/Local/Temp/scui-citation-source-native-du6504t2/data/catalog.db')
assert sha(g09)=='9f46702f641a18a5418814377dc74e7183d1648516c4d83a5ffcc07990069c7c'
vector=load(repo/'.tmp/scholar-g10-full-tests-v1/source-before.json')
for name,digest in vector.items():assert sha(repo.parent/'RSTV4'/name)==digest,name
(out/'all-tables.json').write_text(json.dumps(now,ensure_ascii=False,indent=2),encoding='utf-8')
receipt={'status':'PASS_EXACT_OWNED_NATIVE_DELTAS_AND_ORIGINAL_PRESERVATION','at':datetime.now(timezone.utc).isoformat(),
 'tables':109,'original105_tables_all_data_preserved':True,'added_annotation_schema':added,
 'allowed_delta_counts':{n:{'before':v['before'],'after':v['after']} for n,v in diag['changed'].items()},
 'manuscript':ms,'track':track,'document_revision':2,'manuscript_cas_revision':1,
 'source_database_unchanged':True,'g09_database_unchanged':True,'all177_backend_sources_exact':True,
 'new_models':0,'new_jobs':0,'science_approval':False,'overall11_complete':False,'database_sha256':sha(db)}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False))
