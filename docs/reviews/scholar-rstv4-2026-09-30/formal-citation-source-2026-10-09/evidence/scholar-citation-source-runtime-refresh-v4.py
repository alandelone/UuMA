from pathlib import Path
import json,hashlib
failed=Path('.tmp/scholar-citation-source-failed-discussion-v1/original-records.json')
assert hashlib.sha256(failed.read_bytes()).hexdigest()=='441ec13fe7bf45de704fe38a174a7c121f75c6c9fb70692807797d58971cacb1'
source=Path('.tmp/scholar-citation-source-runtime-refresh-v3.py').read_text(encoding='utf-8')
source=source.replace("'runtime-refresh-v3'","'runtime-refresh-v4'").replace("'backend-runtime-v4'","'backend-runtime-v5'").replace("'93264'","'103096'")
assert "'103096'" in source
exec(compile(source,__file__,'exec'))
with Path('.tmp/scholar-citation-source-failed-discussion-v1/context.md').open('a',encoding='utf-8') as handle:
 handle.write('\nAdditional source-contract diagnosis: the saved Gemini response evidence IDs are exactly the two original generated-v1 reference IDs. Those references were supplied under generated_version.references, but retrieved_evidence was empty because the question matched no live search result. The unchanged validator inspected only retrieved_evidence. The product fix supplies verified immutable generated references to that existing allowlist, with original metadata taking precedence over live retrieval; the validator itself is unchanged. Regression before fix: 3 expected failures and 2 passing rejection guards. Focused after fix: 65 passed. No original failed database record was edited or promoted.\n')
