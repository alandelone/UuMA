from pathlib import Path
root = Path.cwd()
entry = '''

2026-10-09 generation-v2 retained41passes/two fixture inspection failures. The actual
generated read succeeded, including the unchanged validated-output guard. Physical schema
PRAGMA proves studio_model_calls has started_at/completed_at, not created_at. list_comments
returns studio_changes raw before_json/after_json, not before/after or block_ids. Prepare
the added checks from these observed current fields, parse exact JSON and calculate stable
changed endpoints. Preserve both failed logs, all original assertions and all118/all11 scope.
'''
for name in ['repomemory/findings.md', 'rules/testing-contracts.md', 'stage-gates/03-execution-brief.md']:
    with (root/name).open('a', encoding='utf-8') as handle:
        handle.write(entry)
print('PASS actual schema and response contract recorded before fixture correction')
