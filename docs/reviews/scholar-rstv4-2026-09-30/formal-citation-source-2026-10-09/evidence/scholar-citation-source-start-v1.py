from pathlib import Path
import hashlib
import json
import re
import subprocess

r=Path.cwd()
out=r/'.tmp/scholar-citation-source-start-v1'
out.mkdir()
def sha(raw):return hashlib.sha256(raw).hexdigest()
for name in ['AGENTS.md','rules/session-lifecycle.md','mission_status.json']:
    print('STARTUP',name,(r/name).read_text(encoding='utf-8'))
mission=json.loads((r/'mission_status.json').read_text(encoding='utf-8'))
records={}
for name in ['active-session/HANDOFF.md',mission['gate']['current']]:
    raw=(r/name).read_bytes()
    text=(r/name).read_text(encoding='utf-8')
    (out/Path(name).name).write_bytes(raw)
    records[name]={'raw_sha256':sha(raw),'logical_chars':len(text)}
    print('READ_ALL',name,records[name]);print(text[:9000] if 'HANDOFF' in name else text[-3800:])
scope=r/'docs/reviews/scholar-rstv4-2026-09-30/ui-requirements-preservation.md'
text=scope.read_text(encoding='utf-8')
rows=[line for line in text.splitlines() if re.match(r'^\|\s*(OV|CA|RV|AC|KG|TR|ST|WF|RE|CH)-\d+',line)]
groups=[line for line in text.splitlines() if re.match(r'^\|\s*G-\d+',line)]
assert len(rows)==118 and len(groups)==11
print('ALL118_REQUIREMENTS')
for row in rows:print(' | '.join(row.split('|')[1:3]))
print('ALL11_GROUPS')
for row in groups:print(row)
records['scope']={'sha256':sha(scope.read_bytes()),'requirements':rows,'groups':groups}
parent=r/'docs/reviews/scholar-rstv4-2026-09-30/formal-generated-materials-2026-10-09'
manifest=json.loads((parent/'manifest.json').read_text(encoding='utf-8'))
assert len(manifest['files'])==240
for name,digest in manifest['files'].items():assert sha((parent/name).read_bytes())==digest,name
drift=[name for name,digest in manifest['current_source_sha256'].items() if sha(Path(name).read_bytes())!=digest]
records['material_parent']={'all240sealed_files_exact':True,'current_material_source_drift':drift}
print('PARENT',records['material_parent'])
for repo in [r,r.parent/'RSTV4',r.parent/'writing-studio']:
    print('REPO',str(repo),'CODEGRAPH',(repo/'.codegraph').exists(),'AGENTS',(repo/'AGENTS.md').exists())
    result=subprocess.run(['git','status','--porcelain=v1'],cwd=repo,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0
    (out/(repo.name+'-git-before.txt')).write_text(result.stdout,encoding='utf-8')
    records[repo.name]={'status_lines':len(result.stdout.splitlines()),'git_before_sha256':sha(result.stdout.encode())}
    print('UNRELATED_STATUS_PRESERVED',repo.name,records[repo.name])
(out/'startup.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
print('PREVIOUS_GOAL_TURN_CLASSIFICATION','PROGRESS: six material outputs and native PDFs/ZIPs plus independent compile/visual proof; all11 remains incomplete.')
