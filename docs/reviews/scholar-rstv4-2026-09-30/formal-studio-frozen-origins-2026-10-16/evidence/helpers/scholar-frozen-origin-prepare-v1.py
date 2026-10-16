import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
here = repo / '.tmp/scholar-frozen-origin-v1'
here.mkdir()
roots = [repo.parent / 'RSTV4', repo.parent / 'writing-studio']
files = [p for root in roots for folder in ['src', 'tests', 'app', 'components', 'lib']
         for p in (root / folder).rglob('*')
         if p.is_file() and p.suffix in {'.py', '.js', '.ts', '.tsx', '.css', '.cjs'}]
vector = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(here / 'source-before.json').write_text(json.dumps(vector, indent=2), encoding='utf8')
for name in ['RSTV4/src/rstv4/studio_revision_mapping.py',
             'writing-studio/components/studio-response-review.tsx',
             'writing-studio/lib/studio-types.ts']:
    p = repo.parent / name
    dest = here / 'before' / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(p.read_bytes())
print(json.dumps({'status': 'FROZEN_BEFORE_EDITS', 'files': len(vector)}))
