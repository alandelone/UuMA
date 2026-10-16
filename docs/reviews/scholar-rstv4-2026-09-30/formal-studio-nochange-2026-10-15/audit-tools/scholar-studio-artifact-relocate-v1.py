from pathlib import Path
from contextlib import closing
import importlib.util,json,hashlib,sqlite3,shutil,re
repo=Path(__file__).resolve().parents[1]
h=repo/'.tmp/scholar-studio-artifact-relocation-v1';h.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('owned_v9_relocation_guard',repo/'.tmp/scholar-studio-current-native-restart-v9.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=m.read(m.HERE/'receipt.json');root=Path(r['root']).resolve();db=root/'data/catalog.db'
def put(n,v):
    with (h/n).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)
m.guard(r)
before=m.snap(db)
assert before==m.read(m.HERE/'backend-terminal.json')['copy_final_all_tables']
assert len(before['tables'])==110
put('before110-all-tables.json',before);put('before-all-files.json',m.filemap(root))
with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
    c.row_factory=sqlite3.Row
    artifacts=[dict(row) for row in c.execute('SELECT * FROM studio_artifacts ORDER BY artifact_id')]
    with closing(sqlite3.connect(h/'catalog-before.db')) as backup:c.backup(backup)
assert m.snap(h/'catalog-before.db')==before
assert len(artifacts)==25
protected={Path(p).resolve():digest for p,digest in r['protected_external_artifacts'].items()}
assert set(Path(a['storage_path']).resolve() for a in artifacts)==set(protected)
plan=[]
for a in artifacts:
    source=Path(a['storage_path']).resolve()
    assert source.is_file() and m.sha(source)==a['sha256']==protected[source]
    assert source.stat().st_size==a['size_bytes']
    assert re.fullmatch(r'[a-zA-Z0-9_-]+',a['manuscript_id']) and re.fullmatch(r'[a-zA-Z0-9_-]+',a['job_id'])
    assert source.parent.name==a['job_id'] and source.parent.parent.name=='generated' and source.parent.parent.parent.name==a['manuscript_id']
    dest=(root/'data/writing-studio'/a['manuscript_id']/'generated'/a['job_id']/source.name).resolve()
    assert dest.is_relative_to(root/'data/writing-studio') and dest!=source
    exists=dest.exists()
    if exists:assert dest.is_file() and m.sha(dest)==a['sha256'] and dest.stat().st_size==a['size_bytes']
    plan.append({'artifact_id':a['artifact_id'],'from':a['storage_path'],'to':str(dest),'sha256':a['sha256'],'size_bytes':a['size_bytes'],'target_preexisting_exact':exists})
put('exact-relocation-plan.json',plan)
for item in plan:
    dest=Path(item['to']);dest.parent.mkdir(parents=True,exist_ok=True)
    if not item['target_preexisting_exact']:
        with Path(item['from']).open('rb') as source,dest.open('xb') as target:shutil.copyfileobj(source,target,1024*1024)
    assert m.sha(dest)==item['sha256'] and dest.stat().st_size==item['size_bytes']
with closing(sqlite3.connect(db)) as c:
    c.execute('BEGIN IMMEDIATE')
    for item in plan:
        changed=c.execute('UPDATE studio_artifacts SET storage_path=? WHERE artifact_id=? AND storage_path=? AND sha256=? AND size_bytes=?',(item['to'],item['artifact_id'],item['from'],item['sha256'],item['size_bytes']))
        assert changed.rowcount==1
    c.commit()
after=m.snap(db)
assert after['schema']==before['schema']
assert set(after['tables'])==set(before['tables'])
assert {n for n in before['tables'] if before['tables'][n]!=after['tables'][n]}=={'studio_artifacts'}
def records(state):
    table=state['tables']['studio_artifacts']
    return {row[0]:dict(zip(table['columns'],row)) for row in table['rows']}
old=records(before);new=records(after)
assert set(old)==set(new)
for item in plan:
    a=old[item['artifact_id']];z=new[item['artifact_id']]
    assert {k for k in a if a[k]!=z[k]}=={'storage_path'}
    assert z['storage_path']==item['to']
    assert m.sha(Path(item['from']))==m.sha(Path(item['to']))==item['sha256']
m.guard(r)
put('after110-all-tables.json',after);put('after-all-files.json',m.filemap(root))
put('receipt.json',{'status':'PASS_DECLARED_OWNED_COPY_ARTIFACT_LOCATION_CONTEXT_REPAIR',
 'root':str(root),'artifact_rows_relocated':25,'only_changed_table':'studio_artifacts','only_changed_field':'storage_path',
 'other109_tables_exact':True,'all_generated_ids_hashes_sizes_contents_metadata_except_path_exact':True,
 'old_absolute_files_unchanged':True,'existing_A206_and_new_A211_rows_unchanged':True,
 'current311_frontend91_dist76_and_original109_external25_exact':True,
 'no_product_or_test_change':True,'no_schema_migration':True,'no_model_gpu_or_native_mutation_replay':True,
 'no_path_guard_bypass':True,'all118_complete':False,'final11_complete':False})
context='''

2026-10-15 Studio copied-fixture artifact path context: A211 native no-change review
correctly rejected fixed-v5 PDF because all25 copied studio_artifacts.storage_path
values still named an external original temp root. Keep verified_artifact_bytes
root containment, original artifact SHA/size, generation/version/model/input guards.
Before continuing, quiesce the owned copy, retain its complete110-table/raw backup,
copy exact original25 bytes under owned data/writing-studio/MS/generated/job/name,
then relocate ONLY those25 owned-copy storage_path values in one guarded transaction.
Verify every other109 table and every other artifact field exact, original files
unchanged, and no generation/model/GPU/native replay. Retain the old path mapping,
failed UI evidence and both snapshots. This is fixture-location repair, not product
guard relaxation, new generated output, or scientific approval.
'''
for path in [repo/'rules/testing-contracts.md',repo/'repomemory/findings.md']:
    with path.open('a',encoding='utf-8') as f:f.write(context)
print(json.dumps(m.read(h/'receipt.json')))
