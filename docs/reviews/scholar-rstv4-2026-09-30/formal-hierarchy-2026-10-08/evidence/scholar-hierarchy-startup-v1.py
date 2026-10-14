import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
mission = json.loads((repo / 'mission_status.json').read_text(encoding='utf-8'))
gate = (repo / mission['gate']['current']).read_text(encoding='utf-8')
previous = (repo / 'active-session/HANDOFF.md').read_text(encoding='utf-8')
assert mission['stage']=='verification' and mission['gate']['status']=='pending_review'
assert 'LATEST TEMPLATE AUTHORITY' in previous and 'Entire preceding context follows unabridged' in previous
receipt={'stage':mission['stage'],'gate':mission['gate'],'entire_handoff_chars':len(previous),
         'handoff_raw_sha256':hashlib.sha256((repo/'active-session/HANDOFF.md').read_bytes()).hexdigest(),
         'entire_gate_chars':len(gate),'prior_context_preserved':True,
         'external_codegraph':{name:(repo.parent/name/'.codegraph').exists() for name in ['RSTV4','writing-studio']}}
with (repo / '.tmp/scholar-hierarchy-startup-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(receipt,handle,indent=2)
print(json.dumps(receipt))
print(previous[:13500])
