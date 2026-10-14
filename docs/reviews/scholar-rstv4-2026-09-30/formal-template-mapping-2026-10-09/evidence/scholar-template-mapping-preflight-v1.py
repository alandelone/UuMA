import hashlib,json,sqlite3,subprocess
from pathlib import Path
import httpx
repo=Path(__file__).resolve().parents[1]
prior=json.loads((repo/'.tmp/scholar-hierarchy-runtime-final-v1.json').read_text(encoding='utf-8'))
fixture=json.loads((repo/'.tmp/scholar-template-native-fixture-v1.json').read_text(encoding='utf-8'))
query="Get-CimInstance Win32_Process -Filter 'ProcessId=32792 OR ProcessId=84340 OR ProcessId=83900 OR ProcessId=65640' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json"
observed=json.loads(subprocess.run(['powershell','-NoProfile','-Command',query],capture_output=True,text=True,check=True).stdout)
assert {p['ProcessId'] for p in observed}=={32792,84340,83900,65640}
for p in observed:
    old=next(row for row in prior['observed']['Processes'] if row['ProcessId']==p['ProcessId'])
    assert p['CreationDate']==old['CreationDate'] and p['CommandLine']==old['CommandLine']
response=httpx.get(f"http://127.0.0.1:8877/api/manuscripts/{fixture['native_manuscript_id']}/workspace",timeout=12)
response.raise_for_status();assert response.json()['document_revision']==49
folder=repo/'.tmp/scholar-template-mapping-before-v1';folder.mkdir(exist_ok=False)
names={'RSTV4':['src/rstv4/studio_templates.py','src/rstv4/studio.py','src/rstv4/studio_api.py','src/rstv4/research_views.py','src/rstv4/models.py','src/rstv4/database.py'],
       'writing-studio':['components/studio-workspace.tsx','components/studio-template-adoption.tsx','components/studio-block-controls.tsx','lib/studio-blocks.ts','lib/studio-types.ts','lib/studio-api.ts']}
hashes={}
for project,paths in names.items():
    for name in paths:
        path=repo.parent/project/name;target=folder/project/name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
db=Path(fixture['root'])/'data/catalog.db'
raw=db.read_bytes()
with (folder/'catalog.db').open('xb') as h:h.write(raw)
with sqlite3.connect(f'{db.as_uri()}?mode=ro',uri=True) as c:
    c.row_factory=sqlite3.Row
    tables={name:[dict(row) for row in c.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
review=json.loads((repo/'.tmp/scholar-hierarchy-review-diff-v1.json').read_text(encoding='utf-8'))
changes=[p for p,r in review.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=r['after_sha256']]
receipt={'prior_runtime':prior,'observed':observed,'workspace':response.json(),'source_before_sha256':hashes,
         'prior_phase_source_changes':changes,'before_tables':tables,'database_sha256':hashlib.sha256(raw).hexdigest(),
         'external_agents':{name:(repo.parent/name/'AGENTS.md').exists() for name in names}}
with (repo/'.tmp/scholar-template-mapping-preflight-v1.json').open('x',encoding='utf-8') as h:json.dump(receipt,h,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in receipt.items() if k in {'prior_phase_source_changes','database_sha256','external_agents'}},ensure_ascii=False))
