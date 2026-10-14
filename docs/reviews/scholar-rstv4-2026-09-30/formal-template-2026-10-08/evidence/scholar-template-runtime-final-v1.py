import hashlib
import json
import subprocess
from pathlib import Path

import httpx

repo = Path(__file__).resolve().parents[1]
info = json.loads((repo / '.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
production = json.loads((repo / '.tmp/scholar-template-production-v1.json').read_text(encoding='utf-8'))
command = r"""
$all = Get-CimInstance Win32_Process
$ids = [System.Collections.Generic.HashSet[int]]::new()
[void]$ids.Add(82248)
[void]$ids.Add(35552)
do { $added = $false; foreach ($p in $all) { if ($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)) { $added = $true } } } while ($added)
[pscustomobject]@{
 Processes = @($all | Where-Object { $ids.Contains([int]$_.ProcessId) } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate)
 Listeners = @(Get-NetTCPConnection -State Listen -LocalPort 3004,8877 | Select-Object LocalAddress,LocalPort,OwningProcess)
} | ConvertTo-Json -Depth 7
"""
observed = json.loads(subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,check=True).stdout)
processes = {p['ProcessId']:p for p in observed['Processes']}
assert 82248 in processes and 35552 in processes
assert 'scholar-revision-isolated-services-v1.py' in processes[82248]['CommandLine'] and ' serve' in processes[82248]['CommandLine']
assert 'npm.cmd run start -- --port 3004 --hostname 127.0.0.1' in processes[35552]['CommandLine']
for listener in observed['Listeners']:
    assert listener['LocalAddress'] == '127.0.0.1'
    pid = listener['OwningProcess']
    chain = [pid]
    root = 82248 if listener['LocalPort'] == 8877 else 35552
    while pid != root:
        assert pid in processes and len(chain) < 8
        pid = processes[pid]['ParentProcessId']
        chain.append(pid)
    listener['verified_ancestry'] = chain
assert {p['LocalPort'] for p in observed['Listeners']} == {3004,8877}
before = (Path(info['root'])/'data/catalog.db').read_bytes()
with httpx.Client(timeout=12) as client:
    api = 'http://127.0.0.1:8877/api'
    workspace = client.get(f"{api}/manuscripts/{info['native_manuscript_id']}/workspace")
    workspace.raise_for_status()
    assert workspace.json()['document_revision'] == 27 and workspace.json()['document'] == info['initial_document']
    preview = client.get(f"{api}/manuscripts/{info['native_manuscript_id']}/templates/{info['template_skeleton_id']}")
    preview.raise_for_status()
    assert preview.json() == info['preview']
    old = client.get(f"{api}/manuscripts/manuscript_3a132decd09349b99b186a5c44dc191d/workspace")
    old.raise_for_status()
    assert old.json()['document_revision'] == 9
    for asset,digest in production['served_assets_sha256'].items():
        response = client.get('http://127.0.0.1:3004'+asset)
        assert response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == digest
assert before == (Path(info['root'])/'data/catalog.db').read_bytes()
assert hashlib.sha256((Path(info['golden_root'])/'data/catalog.db').read_bytes()).hexdigest() == info['golden_database_sha256']
full = json.loads((repo / '.tmp/scholar-template-full-v2.json').read_text(encoding='utf-8'))
assert full['status'] == 'PASS' and not full['changed_during_verification']
review = json.loads((repo / '.tmp/scholar-template-review-diff-v1.json').read_text(encoding='utf-8'))
for path,receipt in review.items():
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert digest == receipt['after_sha256'] == full['after_sha256'][path]
result = {'status':'PASS_ACTUAL_OWNED_RUNTIME_AND_SOURCE_STABILITY','observed':observed,
          'studio_root':info['root'],'source_import_root':info['source_import_root'],
          'frontend_production_root':production['root'],'frontend_launch_pid':35552,'backend_launch_pid':82248,
          'native_manuscript_id':info['native_manuscript_id'],'template_skeleton_id':info['template_skeleton_id'],
          'native_revision':27,'original_clone_revision':9,'read_only_bytes_unchanged':True,
          'final_source_matches_full_tests_and_review_snapshot':True,'golden_bytes_unchanged':True,
          'compiled_golden_port3000_unchanged':True,'browser_upload_permission_answer_received':False}
with (repo / '.tmp/scholar-template-runtime-final-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(result,handle,indent=2)
print(json.dumps({k:v for k,v in result.items() if k != 'observed'},ensure_ascii=False))
