from pathlib import Path
repo=Path(__file__).resolve().parents[1]
context='''

2026-10-16 legacy origin first focused run:32 backend checks passed; the new real
template fixture failed at its first generation because it assumed paragraph_id
in the paragraph-realization payload. Actual failed job73387abf... records KeyError
paragraph_id; stable first Thought ID is present through actual payload.intents.
Use that recorded identity for unique software wording, retain SUCCEEDED assertions
and include full job diagnostics. No original successful model/native/job is replayed.
All controlled frontend checks passed, but TypeScript correctly rejected a failed
type-predicate branch narrowing an already-typed value to never. Treat transport
result as unknown before unchanged runtime validation; no identity guard weakened.
Remove the unused fixture unpacked variable; preserve all first logs.
Historical reads use pure revision reader and raw serialized SHA, avoiding
get_workspace initialization. Projected generated slot and raw author-bank paragraph
can differ: bind through verified Thought mappings, never identical text or current
editor and never accept ambiguous placements.
'''
for name in ['rules/testing-contracts.md','repomemory/findings.md']:
    with (repo/name).open('a',encoding='utf8') as f:f.write(context)
source=(repo/'.tmp/scholar-legacy-origins-run-v1.py').read_text(encoding='utf8')
source=source.replace("f'focused-{i}.log'","f'focused-v2-{i}.log'").replace("'focused-receipt.json'","'focused-v2-receipt.json'")
(repo/'.tmp/scholar-legacy-origins-run-v2.py').write_text(source,encoding='utf8')
