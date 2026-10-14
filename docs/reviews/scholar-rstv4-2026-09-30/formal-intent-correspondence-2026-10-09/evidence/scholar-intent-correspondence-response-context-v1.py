from pathlib import Path
import hashlib
root=Path.cwd()
source=root.parent/'writing-studio/tests/unit/studio-response-review.cjs'
raw=source.read_bytes()
with (root/'.tmp/scholar-intent-correspondence-response-test-before-v1.cjs').open('xb') as handle:
    handle.write(raw)
entry='''

2026-10-09 static-v2: all correspondence/type/lint/history/structure checks passed; existing
response-review unit stopped at missing require('@/lib/studio-downloads'), before any behavior
assertion. Actual current component imports only studioFileUrl from that module. Execute the
unchanged shipped helper in the controlled unit loader, retaining every response/async/association
assertion. This is an import dependency fix; do not trigger browser downloads, add download
permissions, mock successful delivery, or run the paused native download test. Old test saved
before repair. Full regression remains required after the narrow response-review check.
'''
for name in ['repomemory/findings.md','rules/testing-contracts.md','stage-gates/03-execution-brief.md']:
    with (root/name).open('a',encoding='utf-8') as handle: handle.write(entry)
print('PASS missing unit loader dependency recorded; before SHA '+hashlib.sha256(raw).hexdigest())
