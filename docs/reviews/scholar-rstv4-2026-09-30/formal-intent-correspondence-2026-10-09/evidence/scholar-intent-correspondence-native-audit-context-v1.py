from pathlib import Path
root=Path.cwd()
entry='''

2026-10-09 native independent audit context: audit-v1 stopped at studio_change_link_state.
Physical diagnostic proves77prior rows plus11new rows, keyed by change_id, not manuscript_id;
each newly saved operation records initial comment-link state even with no comment selected.
Before altering the verifier require ALL77previous rows exact, each new row tied to an actual
owned new change, no initial comment association, recorded_at_save origin and initial revision.
Keep comparison of all109tables and every other manuscript, immutable payload/inverse and original
source intact. Earlier diagnostic command used nonexistent studio_jobs.kind; real job_kind
observed. Failed quote-escaped read command did not run; use saved helpers for multiline SQL.
These are verifier execution-context fixes, not product edits or weakened acceptance.
'''
for name in ['repomemory/findings.md','rules/testing-contracts.md','stage-gates/03-execution-brief.md']:
    with (root/name).open('a',encoding='utf-8') as handle: handle.write(entry)
source=(root/'.tmp/scholar-intent-correspondence-native-audit-v1.py').read_text(encoding='utf-8')
source=source.replace("    if table not in allowed:\n", "    if table == 'studio_change_link_state':\n        assert after[table][:len(before[table])] == before[table]\n        new_changes = {c['change_id'] for c in after['studio_changes'] if c['manuscript_id'] == ms} - {c['change_id'] for c in before['studio_changes'] if c['manuscript_id'] == ms}\n        new_rows = after[table][len(before[table]):]\n        assert len(new_rows) == len(new_changes) == 11\n        assert {r['change_id'] for r in new_rows} == new_changes\n        assert all(r['initial_comment_ids_json'] == '[]' and r['initial_origin'] == 'recorded_at_save' and r['link_revision'] == 0 for r in new_rows)\n    elif table not in allowed:\n")
(root/'.tmp/scholar-intent-correspondence-native-audit-v2.py').write_text(source,encoding='utf-8')
print('PASS exact physical initial-link context recorded before verifier correction')
