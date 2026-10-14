import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
findings = (repo / 'repomemory/findings.md').read_text(encoding='utf-8')
mission = json.loads((repo / 'mission_status.json').read_text(encoding='utf-8'))
gate = (repo / mission['gate']['current']).read_text(encoding='utf-8')
assert mission['stage'] == 'verification' and mission['gate']['status'] == 'pending_review'
component = repo.parent / 'writing-studio/components/studio-template-adoption.tsx'
(repo / '.tmp/scholar-source-hierarchy-modal-before-v1.tsx').write_bytes(component.read_bytes())
record = '\n\n### 2026-10-09 source hierarchy native context restart\n\nFull regression v2 PASS: 1015 tests, 20 warnings; 23 checks, source hashes unchanged, log SHA256 82e30366c32968fd5c5025f60ec5e43c96aa2744a3aeb07adab2b34aaa7ddb2d. Native fixture persisted r1 author edit, r2 partial template, r3 Undo, r4 Redo, r5 complete template at nested section, r6 Undo to exact original. Two rapid UI Undo actions coalesced into that single persisted r6; the intermediate partial DOM is not a separate saved revision. Two REPLACE clicks produced no operation and are failed acceptance, not success. Native screenshots show a 1366x607 viewport with template modal/header/footer clipping. Read entire findings/current gate and exact native operation table before further product edits. Preserve failures; correct dialog bounds/scrolling, then type/lint/build and retry from the saved r6. Do not change source/assertion/review/model logic.\n'
with (repo / 'repomemory/findings.md').open('a', encoding='utf-8') as f:
    f.write(record)
with (repo / 'rules/scholar-native-acceptance.md').open('a', encoding='utf-8') as f:
    f.write('\n\nFor rapid Undo/Redo/adoption sequences, require saved-state confirmation before a dependent action and verify actual persisted revisions; multiple optimistic UI steps may coalesce into one save. A successful selector click is not acceptance: require the resulting visible state and durable operation receipt. Keep failed modal/footer interactions when viewport clipping prevents the intended result.\n')
print(json.dumps({'status': 'PASS_NATIVE_CONTEXT_CORRECTED', 'findings_characters': len(findings),
                  'gate_characters': len(gate), 'modal_before_sha256': hashlib.sha256(component.read_bytes()).hexdigest()}))
