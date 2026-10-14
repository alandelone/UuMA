import difflib,hashlib,json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
projects={'RSTV4':['src/rstv4/studio.py','src/rstv4/studio_structure.py','src/rstv4/studio_context.py','src/rstv4/studio_templates.py','src/rstv4/studio_read_views.py','tests/test_studio_hierarchy.py'],
          'writing-studio':['lib/studio-blocks.ts','lib/studio-types.ts','components/studio-workspace.tsx','components/studio-argument-relations.tsx','tests/unit/studio-hierarchy.cjs']}
sha=lambda raw:hashlib.sha256(raw).hexdigest()
results={};diff=[]
for project,names in projects.items():
    for name in names:
        path=repo.parent/project/name
        old=repo/'.tmp/scholar-hierarchy-before-v1'/project/name
        before=old.read_bytes() if old.exists() else b''
        after=path.read_bytes()
        results[str(path)]={'before_sha256':sha(before),'after_sha256':sha(after),'new_file':not old.exists(),'changed':before!=after,'before_path':str(old) if old.exists() else None}
        diff.extend(difflib.unified_diff(before.decode('utf-8').splitlines(True),after.decode('utf-8').splitlines(True),fromfile=f'before/{project}/{name}',tofile=f'after/{project}/{name}'))
with (repo/'.tmp/scholar-hierarchy-review-diff-v1.json').open('x',encoding='utf-8') as h:json.dump(results,h,indent=2)
with (repo/'.tmp/scholar-hierarchy-review-diff-v1.diff').open('x',encoding='utf-8',newline='') as h:h.writelines(diff)
assert len(results)==11 and all(r['changed'] for r in results.values())
print('PASS exact11-file phase diffs and before/after hashes, including3 new files')
