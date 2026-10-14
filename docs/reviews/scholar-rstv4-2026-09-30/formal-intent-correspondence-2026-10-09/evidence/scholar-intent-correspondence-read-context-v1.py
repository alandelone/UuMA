from pathlib import Path
import hashlib
import json

root = Path.cwd()
source = root.parent / 'RSTV4/src/rstv4/studio_read_views.py'
raw = source.read_bytes()
backup = root / '.tmp/scholar-intent-correspondence-read-views-before-v1.py'
with backup.open('xb') as handle:
    handle.write(raw)
entry = '''

2026-10-09 correspondence generation execution contract correction BEFORE read-view repair:
generation-v1 retained19passes/two failures. Actual generation+real artifact compiler succeeded,
but immutable generated read compared populated referenced author Intents against raw empty
template slots and rejected the original input. The reader must derive the same deterministic
realization projection from the EXACT frozen author revision, preserving canonical author bank,
fixed target source, original group/full contexts and relation conditions. Retain all original
validated-call/hash/output/mapping guards; add exact original bank/context/formula/asset guards
for mapped output. Tampering with frozen source/context/projection must remain rejected.
The other new check incorrectly assumed a block_ids API field: comment_changes exposes actual
before/after documents. Verify stable IDs by the existing changed-block calculation on those
exact documents, plus unchanged association events through Undo/Redo/archive/restore. No guard
or assertion scope is reduced. No real model, scientific acceptance or native download claim.
'''
for name in ['repomemory/findings.md', 'rules/testing-contracts.md',
             'stage-gates/03-execution-brief.md',
             'docs/reviews/scholar-rstv4-2026-09-30/intent-correspondence-contract-2026-10-09.md']:
    path = root / name
    with path.open('a', encoding='utf-8') as handle:
        handle.write(entry)
receipt = {'source': str(source), 'sha256': hashlib.sha256(raw).hexdigest(),
           'context_recorded_before_fix': True}
(root / '.tmp/scholar-intent-correspondence-read-context-v1.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print('PASS generation read contract and prior bytes preserved before production repair')
