import hashlib,json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
mission=json.loads((repo/'mission_status.json').read_text(encoding='utf-8'))
gate=(repo/mission['gate']['current']).read_text(encoding='utf-8')
previous=(repo/'active-session/HANDOFF.md').read_text(encoding='utf-8')
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
assert 'LATEST HIERARCHY AUTHORITY' in previous
result={'mission':mission,'entire_gate_chars':len(gate),'entire_handoff_chars':len(previous),
        'handoff_raw_sha256':hashlib.sha256((repo/'active-session/HANDOFF.md').read_bytes()).hexdigest(),
        'external_codegraph':{name:(repo.parent/name/'.codegraph').exists() for name in ['RSTV4','writing-studio']}}
with (repo/'.tmp/scholar-template-mapping-startup-v1.json').open('x',encoding='utf-8') as h:json.dump(result,h,indent=2)
print(json.dumps(result))
print(previous[:14500])
