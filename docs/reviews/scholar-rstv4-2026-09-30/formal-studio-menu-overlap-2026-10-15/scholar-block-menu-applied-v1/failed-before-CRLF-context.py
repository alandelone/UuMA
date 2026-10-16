from pathlib import Path
import hashlib,json,shutil,subprocess

repo=Path(__file__).resolve().parents[1]
front=repo.parent/'writing-studio'
here=repo/'.tmp/scholar-block-menu-applied-v1'
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=read(repo/'.tmp/scholar-complex-native-runtime-v1/receipt.json')
expected=read(repo/'.tmp/scholar-block-menu-overlap-proposal-v1/receipt.json')
assert read(repo/'.tmp/scholar-complex-native-runtime-v1/owned-stop-terminal.json')['status']=='EXACT_OWNED_FRONTEND_AND_BACKEND_STOPPED_PORTS_FREE'
assert all(sha(front/n)==h for n,h in old['frontend_product_vector'].items())
assert all(sha(repo.parent/'RSTV4'/n)==h for n,h in old['backend_source_vector'].items())
patch=repo/'.tmp/scholar-block-menu-overlap-proposal-v1.patch'
assert sha(patch)==expected['patch_sha256']=='04a6a317a9a183090d8bec85bc99ab774a94257986340687749d313477c7221a'
names=['components/studio-workspace.tsx','app/globals.css']
here.mkdir(exist_ok=False)
for name in names:
    assert sha(front/name)==expected[name]['before_sha256']
    backup=here/'before'/name;backup.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(front/name,backup)
args=['git','-C',str(front),'apply','-p2']
subprocess.run([*args,'--check',str(patch)],check=True)
subprocess.run([*args,str(patch)],check=True)
for name in names:assert sha(front/name)==expected[name]['candidate_sha256']
assert all(sha(front/n)==h for n,h in old['frontend_product_vector'].items() if n not in names)
assert all(sha(repo.parent/'RSTV4'/n)==h for n,h in old['backend_source_vector'].items())
receipt={'status':'APPLIED_TWO_FRONTEND_FILES_ONLY','files':{n:{'before':expected[n]['before_sha256'],'after':sha(front/n)} for n in names},'other89_frontend_files_exact':True,'all311_backend_files_exact':True,'old_build_untouched':True,'patch_sha256':sha(patch),'native_geometry_still_pending':True,'all11_complete':False}
(here/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
print(json.dumps(receipt))
