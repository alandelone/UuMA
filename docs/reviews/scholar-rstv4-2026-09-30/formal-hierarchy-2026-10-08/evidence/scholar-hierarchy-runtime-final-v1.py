import ast,hashlib,json,subprocess
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
refresh=json.loads((repo/'.tmp/scholar-hierarchy-refresh-v4.json').read_text(encoding='utf-8'))
build=json.loads((repo/'.tmp/scholar-hierarchy-build-v2.json').read_text(encoding='utf-8'))
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
native=json.loads((repo/'.tmp/scholar-hierarchy-native-final-v2.json').read_text(encoding='utf-8'))
full=json.loads((repo/'.tmp/scholar-hierarchy-full-v2.json').read_text(encoding='utf-8'))
assert full['status']=='PASS' and not full['changed_during_verification']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
review=json.loads((repo/'.tmp/scholar-hierarchy-review-diff-v1.json').read_text(encoding='utf-8'))
for path,receipt in review.items():assert sha(Path(path))==receipt['after_sha256']==full['after_sha256'][path]
for path,digest in build['dist_files'].items():assert sha(Path(build['root'])/path)==digest
for path in review:
    p=Path(path)
    if p.is_relative_to(repo.parent/'writing-studio'):
        assert sha(p)==sha(Path(build['root'])/p.relative_to(repo.parent/'writing-studio'))
query=f'''
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
[void]$ids.Add({refresh['backend_launch_pid']})
[void]$ids.Add({refresh['frontend_launch_pid']})
do {{ $added=$false; foreach ($p in $all) {{ if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) {{ $added=$true }} }} }} while ($added)
[pscustomobject]@{{Processes=@($all | Where-Object {{ $ids.Contains([int]$_.ProcessId) }} | Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,CreationDate);Listeners=@(Get-NetTCPConnection -State Listen -LocalPort 3004,8877 | Select-Object LocalAddress,LocalPort,OwningProcess)}} | ConvertTo-Json -Depth 5
'''
observed=json.loads(subprocess.run(['powershell','-NoProfile','-Command',query],capture_output=True,text=True,encoding='utf-8',check=True).stdout)
processes={p['ProcessId']:p for p in observed['Processes']}
for listener in observed['Listeners']:
    assert listener['LocalAddress']=='127.0.0.1'
    root=refresh['backend_launch_pid'] if listener['LocalPort']==8877 else refresh['frontend_launch_pid']
    pid=listener['OwningProcess'];chain=[pid]
    while pid!=root:
        assert pid in processes and len(chain)<8
        pid=processes[pid]['ParentProcessId'];chain.append(pid)
    listener['verified_ancestry']=chain
    owner=processes[listener['OwningProcess']]
    if listener['LocalPort']==3004:
        assert str(Path(refresh['production_root'])) in owner['CommandLine'] and owner['ExecutablePath'].lower().endswith('node.exe')
    else:assert 'scholar-revision-isolated-services-v1.py serve' in owner['CommandLine']
assert {p['LocalPort'] for p in observed['Listeners']}=={3004,8877}
db=Path(fixture['root'])/'data/catalog.db';before=db.read_bytes()
with httpx.Client(timeout=12) as client:
    response=client.get(f"http://127.0.0.1:8877/api/manuscripts/{fixture['native_manuscript_id']}/workspace");response.raise_for_status()
    assert response.json()['document_revision']==49 and response.json()['document']==native['current_document']
    response=client.get('http://127.0.0.1:8877/api/manuscripts/manuscript_3a132decd09349b99b186a5c44dc191d/workspace');response.raise_for_status()
    assert response.json()['document_revision']==9
    for asset,digest in refresh['served_assets_sha256'].items():
        response=client.get('http://127.0.0.1:3004'+asset)
        assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==digest
assert db.read_bytes()==before
assert sha(Path(fixture['golden_root'])/'data/catalog.db')==fixture['golden_database_sha256']
result={'status':'PASS_FINAL_SOURCE_BUILD_AND_OWNED_RUNTIME','observed':observed,'production_root':refresh['production_root'],
        'backend_launch_pid':refresh['backend_launch_pid'],'frontend_launch_pid':refresh['frontend_launch_pid'],
        'native_revision':49,'original_clone_revision':9,'final_source_matches_full_tests_and_build':True,
        'read_only_database_bytes_unchanged':True,'original_database_and_dist_unchanged':True,
        'browser_upload_permission_answer_received':False,'overall_11_groups_complete':False}
with (repo/'.tmp/scholar-hierarchy-runtime-final-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2)
print(json.dumps({k:v for k,v in result.items() if k!='observed'},ensure_ascii=False))
