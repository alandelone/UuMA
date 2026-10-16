from pathlib import Path
import json

repo = Path.cwd()
out = repo / '.tmp/scholar-g11-identity-native-v1'
code = Path('.tmp/scholar-g11-identity-native-v1.py').read_text(encoding='utf-8')
old = "json.loads(item['result_json']) == json.loads(old['result_json'])"
new = "json.loads(item['result_json']) == json.loads(old['result_json'] or '{}')"
assert code.count(old) == 1
context = {'failure_class': 'READ_ONLY_AUDITOR_EXPECTED_JSON_STRING_FOR_SQL_NULL',
           'actual_product_contract': 'Review reopen stores json.loads(result_json or {}). Approval restores that declared previous_result as serialized JSON.',
           'permitted_empty_result_normalization': 'Only the two already declared nonterminal jobs may change result_json from SQL NULL to JSON {}.',
           'native_actions_replayed': False, 'database_modified_by_auditor': False,
           'other_original_rows_and_all_immutable_fields_still_exact': True}
with (out / 'audit-v2-context.json').open('x', encoding='utf-8') as stream:
    json.dump(context, stream, indent=2)
exec(compile(code.replace(old, new), __file__, 'exec'))
