import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
findings = (repo / 'repomemory/findings.md').read_text(encoding='utf-8')
mission = json.loads((repo / 'mission_status.json').read_text(encoding='utf-8'))
gate = (repo / mission['gate']['current']).read_text(encoding='utf-8')
assert mission['stage'] == 'verification' and mission['gate']['status'] == 'pending_review'
context = '\n\n### 2026-10-09 source hierarchy focused retry context\n\nRead the entire findings and current verification gate after the second failed focused run. First failure was corrected canonical page-column mapping; the second retained log is `.tmp/scholar-source-hierarchy-focused-v2.log` (64 passed, one KeyError). Missing context: `model_calls` in acquisition API is a computed view, not an `acquisition_model_calls` table. Its physical append-only source is `acquisition_model_call_events`, including STARTED/RETURNED/FAILED receipts. Preserve the no-new-model-calls assertion on that actual ledger and retain separate studio model-call/job/approval ledgers; do not create a phantom table or weaken the safety requirement. Existing diff preserved, no reset or gate transition.\n'
with (repo / 'repomemory/findings.md').open('a', encoding='utf-8') as f:
    f.write(context)
with (repo / 'rules/scholar-native-acceptance.md').open('a', encoding='utf-8') as f:
    f.write('\n\nAcquisition `model_calls` is a computed API view of `acquisition_model_call_events`; inspect SCHEMA and assert the actual append-only ledger (STARTED/RETURNED/FAILED), never assume a similarly named physical table. Preserve no-new-call and no-new-approval assertions.\n')
test = repo.parent / 'RSTV4/tests/test_skeleton_source_outline.py'
(repo / '.tmp/scholar-source-hierarchy-test-before-context-v2.py').write_bytes(test.read_bytes())
source = test.read_text(encoding='utf-8')
test.write_text(source.replace('"acquisition_model_calls", "acquisition_model_call_events"',
                               '"acquisition_model_call_events"'), encoding='utf-8')
runner = (repo / '.tmp/scholar-source-hierarchy-focused-v1.py').read_text(encoding='utf-8')
(repo / '.tmp/scholar-source-hierarchy-focused-v3.py').write_text(runner.replace('focused-v1', 'focused-v3'), encoding='utf-8')
print(json.dumps({'status': 'PASS_CONTEXT_RESTART_FROM_VERIFICATION', 'findings_characters': len(findings),
                  'gate_characters': len(gate), 'gate_sha256': hashlib.sha256(gate.encode()).hexdigest(),
                  'assertion': 'same no-new-calls contract on actual event ledger'}))
