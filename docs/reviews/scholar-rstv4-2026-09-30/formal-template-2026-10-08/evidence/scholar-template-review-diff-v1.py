import difflib
import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
paths = [repo.parent/'RSTV4/src/rstv4/studio.py',repo.parent/'RSTV4/src/rstv4/studio_api.py',
         repo.parent/'writing-studio/components/studio-workspace.tsx',
         repo.parent/'writing-studio/lib/studio-types.ts',repo.parent/'writing-studio/lib/studio-api.ts']
files = {}
with (repo / '.tmp/scholar-template-review-diff-v1.diff').open('x',encoding='utf-8') as handle:
    for path in paths:
        old = repo / '.tmp/scholar-template-before-v1' / path.name
        before = old.read_text(encoding='utf-8').splitlines(keepends=True)
        after = path.read_text(encoding='utf-8').splitlines(keepends=True)
        handle.writelines(difflib.unified_diff(before,after,fromfile='before/'+path.name,tofile=str(path),n=4))
        files[str(path)] = {'before_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    for path in [repo.parent/'RSTV4/src/rstv4/studio_templates.py',repo.parent/'RSTV4/tests/test_studio_templates.py',repo.parent/'writing-studio/components/studio-template-adoption.tsx']:
        handle.writelines(difflib.unified_diff([],path.read_text(encoding='utf-8').splitlines(keepends=True),fromfile='/dev/null',tofile=str(path),n=4))
        files[str(path)] = {'new_this_phase':True,'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
with (repo / '.tmp/scholar-template-review-diff-v1.json').open('x',encoding='utf-8') as handle:
    json.dump(files,handle,indent=2)
print('Retained exact 5 before/after diffs and 3 new files')
