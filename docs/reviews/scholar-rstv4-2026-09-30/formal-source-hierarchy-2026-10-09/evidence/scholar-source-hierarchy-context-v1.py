import hashlib,json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
findings=repo/'repomemory/findings.md';prior=findings.read_text(encoding='utf-8')
note='''

## 2026-10-09 source hierarchy execution context

Source-hierarchy discovery repeated an invalid Windows rg path wildcard (parse*/skeleton*),
before product edits. Use exact filenames or rg --files DIR -g PATTERN, then rg against the
returned paths; do not give unexpanded glob path arguments. No semantic assertion changed.
Two separate session run writers launched concurrently caused OSError22 projecting progress.md,
before the second child search executed. Serialize lifecycle writer calls. Batch independent
reads inside one child script instead of parallelizing two session wrappers; do not patch or
truncate unrelated shared session history. Original failed outputs remain preserved.
'''
with findings.open('a',encoding='utf-8') as h:h.write(note)
assert findings.read_text(encoding='utf-8').startswith(prior)
rules=repo/'rules/scholar-native-acceptance.md';old=rules.read_text(encoding='utf-8')
with rules.open('a',encoding='utf-8') as h:h.write('''

2026-10-09 discovery execution: Windows rg receives exact file paths, or directory plus -g
patterns; shell wildcard path arguments are not expanded reliably. Only one UuMA session CLI
writer call runs at a time. A child inspection script can batch independent operations without
two wrappers racing to regenerate progress.md. Retain any pre-child wrapper failure and retry
the narrow read after this correction, with lifecycle checks intact.
''')
assert rules.read_text(encoding='utf-8').startswith(old)
print(json.dumps({'status':'EXECUTION_CONTEXT_CORRECTED','entire_findings_read':len(prior),'old_findings_sha256':hashlib.sha256(prior.encode()).hexdigest(),'no_product_changes':True}))
