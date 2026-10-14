from pathlib import Path
import json
import shutil
root=Path.cwd()
diff=json.loads((root/'.tmp/scholar-intent-correspondence-runtime-data-diagnostic-v1.json').read_text(encoding='utf-8'))
fixture=json.loads((root/'.tmp/scholar-intent-correspondence-native-v1.json').read_text(encoding='utf-8'))
assert len(diff)==1 and diff[0]['table']=='studio_sample_candidates'
assert diff[0]['removed']==[] and len(diff[0]['added'])==10
assert all(r['manuscript_id']==fixture['manuscript_id'] and r['document_revision']==19 for r in diff[0]['added'])
entry='''

2026-10-09 runtime refresh diagnostics before continuation: workspace has no jobs field; actual
studio_jobs.job_kind/status table was read instead. Verified own8879ancestry/commands before
stopping; original child+root now both authoritative-terminal and port absent. Stopping the
already-exited launch wrapper raised nonzero before relaunch; old3004/3005 remained untouched.
Restore only the expected absent owned service, not on timeout. Prior quiescent snapshot
comparison stopped relaunch: actual difference is10new ownMS/r19sample-candidate rows from
post-audit generated heading/citation UI reads; ALLother109-table records exact, no removed
cache rows, no new operation/model/job. Preserve original audit+screenshots in-v1, clone-v2,
rerun complete independent109table/native-history/generation audit with final reader source,
then require all current records EXACT before/after the service refresh. Keep each failed
attempt; the original immutable snapshots and byte/record guards are never relaxed.
'''
for name in ['repomemory/findings.md','rules/testing-contracts.md','rules/scholar-native-acceptance.md','stage-gates/03-execution-brief.md']:
    with (root/name).open('a',encoding='utf-8') as handle: handle.write(entry)
shutil.copytree(root/'.tmp/scholar-intent-correspondence-native-v1',root/'.tmp/scholar-intent-correspondence-native-v2')
source=(root/'.tmp/scholar-intent-correspondence-native-audit-v2.py').read_text(encoding='utf-8')
source=source.replace("out = repo/'.tmp/scholar-intent-correspondence-native-v1'","out = repo/'.tmp/scholar-intent-correspondence-native-v2'")
(root/'.tmp/scholar-intent-correspondence-native-audit-v3.py').write_text(source,encoding='utf-8')
source=(root/'.tmp/scholar-intent-correspondence-runtime-refresh-v2.py').read_text(encoding='utf-8')
source=source.replace('.tmp/scholar-intent-correspondence-native-v1/after-tables.json','.tmp/scholar-intent-correspondence-native-v2/after-tables.json')
(root/'.tmp/scholar-intent-correspondence-runtime-refresh-v3.py').write_text(source,encoding='utf-8')
print('PASS exact post-UI own-cache context preserved; old audit retained before fresh freeze')
