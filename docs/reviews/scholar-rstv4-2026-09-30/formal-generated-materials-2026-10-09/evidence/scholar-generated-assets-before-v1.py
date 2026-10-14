from pathlib import Path
import hashlib
import json
import subprocess

root=Path.cwd()
out=root/'.tmp/scholar-generated-assets-before-v1'
assert not out.exists()
out.mkdir()
sources=['RSTV4/src/rstv4/studio.py','RSTV4/src/rstv4/studio_context.py',
         'RSTV4/src/rstv4/studio_read_views.py','RSTV4/src/rstv4/studio_delivery.py',
         'RSTV4/pyproject.toml','writing-studio/components/studio-workspace.tsx',
         'writing-studio/lib/studio-types.ts']
hashes={}
for name in sources:
    target=out/name
    target.parent.mkdir(parents=True,exist_ok=True)
    raw=(root.parent/name).read_bytes()
    target.write_bytes(raw)
    hashes[name]=hashlib.sha256(raw).hexdigest()
status={}
for project in [root,root.parent/'RSTV4',root.parent/'writing-studio']:
    result=subprocess.run(['git','status','--short'],cwd=project,capture_output=True,text=True,encoding='utf-8',check=True)
    (out/(project.name+'-status.txt')).write_text(result.stdout,encoding='utf-8')
    status[project.name]=len(result.stdout.splitlines())
(out/'baseline.json').write_text(json.dumps({'source_sha256':hashes,'unrelated_git_status_preserved':status,
    'all118_all11_scope_retained':True,'downloads_resumed':True,'overall_complete':False},indent=2),encoding='utf-8')
entry='''

2026-10-09 next full-scope batch: ST-19/WF-03/WF-06/ST-16/ST-28/RE-14/G05/G09 require
original supported PNG/JPEG/SVG/CSV/XLSX/Markdown materials in actual generated view and real
PDF/TeX/Markdown/package, not only author-editor previews or asset_id retention. Inspection
shows current realization omits normal asset_ids; compiler/read_view do not render any assets.
Before implementation retain old sources/status and demonstrate actual six-format missing
material output with the real compiler and declared software-only model. Source bytes, original
asset IDs/order/paragraph/group/context, fixed source SHA/version and all author claims remain.
Snapshot must freeze complete table data (not six-row preview) and verified image representation;
explicit failure for missing/corrupt/foreign/unsupported sources rather than silently discarding.
Frozen versions cannot switch to changed live asset bytes. TeX, PDF, view, Markdown and package
must use the same fixed assets; all source/image files needed for independent compilation stay
in the package with exact integrity records. No migration of prior generated artifacts.
No real science approval, new real model, upload/permission changes, old DONE reruns or deleting
previous artifacts. Final scope all118/all11 still requires actual qualified-source/full workflow.
'''
for name in ['repomemory/findings.md','rules/scholar-native-acceptance.md','stage-gates/03-execution-brief.md']:
    with (root/name).open('a',encoding='utf-8') as handle: handle.write(entry)
contract=root/'docs/reviews/scholar-rstv4-2026-09-30/generated-materials-contract-2026-10-09.md'
with contract.open('x',encoding='utf-8') as handle: handle.write('# 原素材进入固定成文与实际编译稿\n'+entry)
print('PASS original7sources/diffs preserved and full material-output contract recorded before edits')
