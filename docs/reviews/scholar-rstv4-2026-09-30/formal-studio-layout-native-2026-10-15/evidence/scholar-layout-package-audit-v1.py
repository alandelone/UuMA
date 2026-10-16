from pathlib import Path
from collections import Counter
from io import BytesIO
import hashlib
import json
import sqlite3
import sys
import urllib.request
import zipfile

repo=Path.cwd();sys.path.insert(0,str(repo/'.tmp/scholar-g11-parallel-v1'))
from runtime_copy_and_serve import snapshot
folder=repo/'.tmp/scholar-layout-package-audit-v1';folder.mkdir(exist_ok=True)
assert not any(folder.iterdir()), 'Never overwrite completed audit evidence'
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,value):(folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
runtime=repo/'.tmp/scholar-layout-native-v3';r=read(runtime/'receipt.json');root=Path(r['root']);db=root/'data/catalog.db'
after=snapshot(db);before=read(repo/'.tmp/scholar-layout-native-v1/before110-all-tables.json')
def records(state,name):
    table=state['tables'][name];return [dict(zip(table['columns'],row)) for row in table['rows']]
assert json.dumps(after['schema'],sort_keys=True)==json.dumps(before['schema'],sort_keys=True)
changed={name for name in before['tables'] if before['tables'][name]!=after['tables'][name]}
allowed={'studio_documents','manuscripts','studio_sample_candidates','studio_operations','studio_changes','studio_change_link_state',
         'comment_changes','studio_comment_response_state','review_rounds','studio_review_round_baselines','review_comments','studio_jobs','manuscript_versions',
         'studio_artifacts','studio_submission_packages'}
assert changed<=allowed,changed-allowed
mutable={'studio_documents','manuscripts','studio_sample_candidates'}
for name,table in before['tables'].items():
    assert table['columns']==after['tables'][name]['columns']
    if name not in mutable:
        old=Counter(json.dumps(row,sort_keys=True) for row in table['rows'])
        new=Counter(json.dumps(row,sort_keys=True) for row in after['tables'][name]['rows'])
        assert all(new[k]>=v for k,v in old.items()),name
for name in ['studio_model_calls','studio_response_checks','studio_assets']:
    assert before['tables'][name]==after['tables'][name],name
assert len(records(after,'manuscript_versions'))-len(records(before,'manuscript_versions'))==1
assert len(records(after,'studio_artifacts'))-len(records(before,'studio_artifacts'))==5
old_jobs={j['job_id'] for j in records(before,'studio_jobs')}
new_jobs=[j for j in records(after,'studio_jobs') if j['job_id'] not in old_jobs]
assert len(new_jobs)==2 and {j['job_kind'] for j in new_jobs}=={'GENERATE','SUBMISSION_PACKAGE'}
assert all(j['status']=='SUCCEEDED' and j['input_revision']==86 for j in new_jobs)
package_job=next(j for j in new_jobs if j['job_kind']=='SUBMISSION_PACKAGE')
package=next(p for p in records(after,'studio_submission_packages') if p['job_id']==package_job['job_id'])
manifest=json.loads(package['manifest_json']);directory=root/'data/writing-studio'/package['manuscript_id']/'packages'/package['job_id']
assert manifest['baseline_manuscript_version_id']=='manuscript_version_e1c764ab2d5a4e97898eda9f5d815d01'
assert manifest['generated_version_id']=='manuscript_version_8732ec9497074d82ae2b4359a7c235e5'
assert manifest['unresolved_comment_ids']==['comment_f71edb5758ef41f3b0d96d8cdbed18d5']
assert manifest['location_summary']['layout_only_rows']==1 and manifest['location_summary']['unknown_or_unattributed_rows']==0
assert len(manifest['file_integrity'])==20
for name,item in manifest['file_integrity'].items():
    assert (directory/name).stat().st_size==item['size_bytes'] and sha(directory/name)==item['sha256'],name
assert (directory/'manifest.json').read_bytes()==json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
diagnostic=read(repo/'.tmp/scholar-layout-location-after-fix-v1/receipt.json')
assert sha(directory/'clean-manuscript.pdf')==diagnostic['pdfs'][1]['sha256']
assert sha(directory/'baseline-manuscript.pdf')==diagnostic['pdfs'][0]['sha256']
mapping=read(directory/'change-realization-map.json');assert len(mapping['rows'])==1 and mapping['rows'][0]['status']=='LAYOUT_ONLY'
assert not mapping['rows'][0]['supports_scientific_text_modification'] and not mapping['scientific_acceptance']
url=f"http://127.0.0.1:8877/api/manuscripts/{package['manuscript_id']}/packages/{package['package_id']}/download"
with urllib.request.urlopen(url,timeout=30) as response:archive=response.read();assert response.status==200
with zipfile.ZipFile(BytesIO(archive)) as bundle:
    assert set(bundle.namelist())==set(manifest['file_integrity'])|{'manifest.json'}
    for name in bundle.namelist():assert bundle.read(name)==(directory/name).read_bytes()
(folder/'verified-package.zip').write_bytes(archive)
for name in ['manifest.json','change-realization-map.json','change-location-map.csv','unresolved-comments.json','response-verification.json']:
    if (directory/name).exists():(folder/name).write_bytes((directory/name).read_bytes())
old_files=read(repo/'.tmp/scholar-layout-native-v1/before110-all-files.json')
for name,h in old_files.items():
    if name not in {'data/catalog.db','data/catalog.db-shm','data/catalog.db-wal'}:assert sha(root/name)==h,name
assert snapshot(db)==after
write('after110-all-tables.json',after)
receipt={'status':'PASS_ORIGINAL_LAYOUT_JOB_AND_ONE_NATIVE_PACKAGE_EXACT','new_jobs':[{'job_id':j['job_id'],'kind':j['job_kind'],'status':j['status']} for j in new_jobs],
         'package_id':package['package_id'],'directory':str(directory),'files':21,'zip_bytes':len(archive),'zip_sha256':hashlib.sha256(archive).hexdigest(),
         'every_fixed_file_manifest_and_zip_member_exact':True,'v6_and_v7_original_pdf_bytes_exact':True,'layout_only_rows':1,
         'pending_A215_preserved_no_new_check':True,'all_old_immutable110_rows_preserved':True,'all_old_non_database_files_exact':True,
         'unchanged_models_assets_checks':True,'schema_changes':False,'changed_tables':sorted(changed),'browser_download_not_retested':True,
         'native_package_file_label_overflow_remains_to_fix':True,'all118_complete':False,'final11_complete':False}
write('receipt.json',receipt);print(json.dumps(receipt,indent=2))
