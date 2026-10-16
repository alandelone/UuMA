from pathlib import Path
import hashlib,json
repo=Path(__file__).resolve().parents[1]
here=repo/'.tmp/scholar-presentation-review-v1';here.mkdir()
names=['RSTV4/src/rstv4/studio_response_checks.py','RSTV4/src/rstv4/studio_api.py',
       'writing-studio/components/studio-response-review.tsx','writing-studio/lib/studio-types.ts',
       'writing-studio/tests/unit/studio-response-review.cjs']
for name in names:
    dest=here/'before'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((repo.parent/name).read_bytes())
(here/'before.json').write_text(json.dumps({n:hashlib.sha256((repo.parent/n).read_bytes()).hexdigest() for n in names},indent=2),encoding='utf8')
