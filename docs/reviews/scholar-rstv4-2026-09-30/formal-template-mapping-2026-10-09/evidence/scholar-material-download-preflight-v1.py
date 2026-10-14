import hashlib,json,shutil
from pathlib import Path
repo=Path(__file__).resolve().parents[1];front=repo.parent/'writing-studio'
full=json.loads((repo/'.tmp/scholar-template-mapping-full-v2.json').read_text(encoding='utf-8'))
assert full['status']=='PASS' and full['changed_during_verification']==[]
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in full['after_sha256'].items())
out=repo/'.tmp/scholar-material-download-before-v1';out.mkdir()
paths=['lib/studio-api.ts','components/studio-workspace.tsx','components/studio-response-review.tsx']
for relative in paths:
    dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(front/relative,dest)
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
db=Path(fixture['root'])/'data/catalog.db';shutil.copy2(db,out/'catalog.db')
result={'status':'PASS_SEALED_TEMPLATE_SOURCE_AND_DOWNLOAD_BACKUPS','full_template_final_log_sha256':full['log_sha256'],'source_sha256':{p:hashlib.sha256((front/p).read_bytes()).hexdigest() for p in paths},'clone_database_sha256':hashlib.sha256(db.read_bytes()).hexdigest(),'existing_files_copied':paths,'new_paths':['lib/studio-downloads.ts','app/api/studio-files/[...path]/route.ts','tests/unit/studio-downloads.cjs'],'no_product_changes_yet':True}
with (repo/'.tmp/scholar-material-download-preflight-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2)
print(json.dumps(result))
