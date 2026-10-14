import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx

repo=Path(__file__).resolve().parents[1]
previous=json.loads((repo/'.tmp/scholar-template-runtime-final-v1.json').read_text(encoding='utf-8'))
observed=json.loads(subprocess.run(['powershell','-NoProfile','-Command',"Get-CimInstance Win32_Process -Filter 'ProcessId=82248 OR ProcessId=83352 OR ProcessId=35552 OR ProcessId=77500' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json"],capture_output=True,text=True,check=True).stdout)
for p in observed:
    old=next(row for row in previous['observed']['Processes'] if row['ProcessId']==p['ProcessId'])
    assert p['CommandLine']==old['CommandLine'] and p['CreationDate']==old['CreationDate']
assert {p['ProcessId'] for p in observed}=={82248,83352,35552,77500}
with httpx.Client(timeout=12) as client:
    response=client.get(f"http://127.0.0.1:8877/api/manuscripts/{previous['native_manuscript_id']}/workspace")
    response.raise_for_status()
    assert response.json()['document_revision']==27
root=Path(previous['studio_root'])
db=root/'data/catalog.db'
folder=repo/'.tmp/scholar-hierarchy-before-v1'
folder.mkdir(exist_ok=False)
names={'RSTV4':['src/rstv4/studio.py','src/rstv4/studio_structure.py','src/rstv4/studio_context.py','src/rstv4/studio_templates.py'],
       'writing-studio':['lib/studio-blocks.ts','lib/studio-types.ts','components/studio-workspace.tsx','components/studio-template-adoption.tsx']}
hashes={}
for project,paths in names.items():
    for name in paths:
        path=repo.parent/project/name
        raw=path.read_bytes()
        target=folder/project/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        hashes[str(path)]=hashlib.sha256(raw).hexdigest()
raw=db.read_bytes()
with (folder/'catalog.db').open('xb') as handle:handle.write(raw)
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as conn:
    conn.row_factory=sqlite3.Row
    tables={name:[dict(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
receipt={'runtime_prior':previous,'fresh_owners':observed,'database_sha256':hashlib.sha256(raw).hexdigest(),'before_tables':tables,'source_before_sha256':hashes,'workspace':response.json()}
with (repo/'.tmp/scholar-hierarchy-preflight-v1.json').open('x',encoding='utf-8') as handle:json.dump(receipt,handle,indent=2,ensure_ascii=False)
print('PASS fresh owners, r27 workspace, entire clone baseline and 8 source backups preserved')
