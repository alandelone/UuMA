from pathlib import Path
import json,hashlib
repo=Path(__file__).resolve().parents[1];here=repo/'.tmp/scholar-legacy-origins-v1'
name='RSTV4/src/rstv4/studio_revision_mapping.py';p=repo.parent/name
dest=here/'before'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
path=here/'before.json';before=json.loads(path.read_text(encoding='utf8'));before[name]=hashlib.sha256(p.read_bytes()).hexdigest();path.write_text(json.dumps(before,indent=2),encoding='utf8')
