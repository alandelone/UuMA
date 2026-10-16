from pathlib import Path
import hashlib
import json

repo = Path.cwd()
out = repo / '.tmp/scholar-g11-identity-native-v1'
mission = json.loads((repo / 'mission_status.json').read_text(encoding='utf-8'))
assert mission['stage'] == 'verification' and mission['gate']['status'] == 'pending_review'
api = (repo.parent / 'RSTV4/src/rstv4/catalog_web.py').read_text(encoding='utf-8')
workflow = (repo.parent / 'RSTV4/src/rstv4/catalog_review_workflow.py').read_text(encoding='utf-8')
source_review = (repo.parent / 'RSTV4/src/rstv4/source_review.py').read_text(encoding='utf-8')
assert '@app.post("/api/catalog/review/cases/{case_id}/actions", status_code=201)' in api
assert 'action_kind' in source_review
assert 'old = json.loads(job.get("result_json") or "{}")' in source_review
code = Path('.tmp/scholar-g11-identity-native-v1.py').read_text(encoding='utf-8')
changes = [
    ("json.loads(item['result_json']) == json.loads(old['result_json'])",
     "json.loads(item['result_json']) == json.loads(old['result_json'] or '{}')"),
    ("assert response['status_code'] == 200", "assert response['status_code'] == 201"),
    ("assert value['action'] == action", "assert value['action_kind'] == action"),
    ("'exact_original_rows': True", "'all_protected_rows_and_fields_exact': True"),
]
for old, new in changes:
    assert code.count(old) == 1
    code = code.replace(old, new)
context = '''

2026-10-14 current identity native audit restart from verification/pending_review.
The two original native actions are already durable; do not repeat them. Auditor
v1 assumed old result_json was a JSON string, although a declared nonterminal job
had SQL NULL. source_review.invalidate_source explicitly saves json.loads(value
or {}) as previous_result; approval serializes that object. Only the already
declared two nonterminal job result fields may normalize SQL NULL to JSON {}.
Auditor v2 next assumed HTTP200 and top-level action; the formal Catalog route
declares HTTP201 and the persisted response uses action_kind. Verify exact201,
exact action_kind, action linkage, 105 schemas, 102 unchanged tables, old action
rows, terminal jobs, immutable inputs/attempts, original and copied file bytes.
This corrects the execution/response audit contract; no product/data/model/native
replay or assertion relaxation. v1/v2 failed helpers and responses are retained.
'''
for relative in ['rules/testing-contracts.md', mission['gate']['current']]:
    path = repo / relative
    raw = path.read_bytes()
    backup = out / (path.name + '.before-audit-v3.raw')
    with backup.open('xb') as stream:
        stream.write(raw)
    ending = b'\r\n' if b'\r\n' in raw else b'\n'
    append = context.encode('utf-8').replace(b'\n', ending)
    path.write_bytes(raw + append)
    assert path.read_bytes().startswith(raw)
with (out / 'audit-v3-context.json').open('x', encoding='utf-8') as stream:
    json.dump({'reason': context, 'product_unchanged': True, 'native_replay': False,
               'api_sha256': hashlib.sha256(api.encode()).hexdigest()}, stream, indent=2)
exec(compile(code, __file__, 'exec'))
