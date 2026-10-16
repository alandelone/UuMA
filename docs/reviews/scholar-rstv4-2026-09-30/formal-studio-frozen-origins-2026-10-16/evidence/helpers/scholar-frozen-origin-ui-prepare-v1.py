from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parent / 'scholar-frozen-origin-ui-proposal-v1'
LIVE = ROOT.parents[2] / 'writing-studio'
ROOT.mkdir(exist_ok=False)
FILES = ['components/studio-response-review.tsx', 'lib/studio-types.ts']
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
before = {}
for name in FILES:
    raw = (LIVE / name).read_bytes()
    before[name] = {'bytes': len(raw), 'sha256': sha(raw)}
    for branch in ('baseline', 'candidate'):
        dest = ROOT / branch / 'writing-studio' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
(ROOT / 'live-source-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
print(ROOT)
