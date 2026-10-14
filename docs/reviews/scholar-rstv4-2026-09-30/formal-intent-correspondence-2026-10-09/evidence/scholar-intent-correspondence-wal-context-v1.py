from pathlib import Path
import hashlib
import json

root=Path.cwd()
folder=root/'.tmp/scholar-intent-correspondence-rollback-baseline-v4'
current=json.loads((folder/'current.json').read_text(encoding='utf-8'))
checkpoint=json.loads((folder/'checkpoint.json').read_text(encoding='utf-8'))
assert current['rows_equal'] and current['before']['wal_bytes_at_raw_read']==135992
assert current['after']['wal_bytes_at_raw_read']==0 and not current['bytes_equal']
assert current['freelist_leaves_before']==[] and current['freelist_trunks_before']==[]
assert checkpoint['pytest_exit']==0 and checkpoint['bytes_equal'] and checkpoint['rows_equal']
assert checkpoint['before']['checkpoint_before_freeze']==[0,0,0]
assert checkpoint['before']['checkpoint_all_rows_unchanged']
entry='''

2026-10-09 confirmed WAL baseline execution context: diagnostic-v4 preserves actual
current before/after raw DB and WAL, all table records and observed MainThread-only state.
Before rollback test freeze, WAL contained135992 bytes of earlier committed fixture work;
after abort it was0 and mainDB differed4832bytes, while every actual table record remained
exact. Privately frozen before-edit source kept its WAL pending and mainDB unchanged.
The absent free pages disprove the earlier freelist hypothesis. Explicit successful
wal_checkpoint(TRUNCATE) BEFORE freezing the current-source byte baseline gave(0,0,0),
every record unchanged, and original unchanged post-write-fault/full-byte assertion PASS.
No transaction, runtime or physical guard weakened. Primary behavior source:
https://www.sqlite.org/wal.html (checkpoint moves earlier committed WAL into main file;
last-connection close can checkpoint). Optional dbstat probe failure remains preserved.

For a quiescent isolated rollback fixture in WAL mode, require completed pre-freeze
checkpoint with busy0/all frames copied/truncated, verify every table record unchanged,
and explicitly close the checkpoint connection. THEN freeze all raw DB bytes. Retain the
exact post-fault byte and data/history assertions. Never manually delete WAL/SHM, checkpoint
after freezing to make an assertion pass, touch live production databases, or omit earlier
failed logs. This completes missing fixture execution context, not a weaker assertion.
'''
for relative in ['repomemory/findings.md','rules/testing-contracts.md','rules/scholar-native-acceptance.md','stage-gates/03-execution-brief.md']:
    path=root/relative
    previous=path.read_text(encoding='utf-8')
    path.write_text(previous+entry,encoding='utf-8')
    assert previous in path.read_text(encoding='utf-8')
source=root.parent/'RSTV4/tests/test_studio_templates.py'
raw=source.read_bytes()
with (root/'.tmp/scholar-intent-correspondence-test-templates-before-v1.py').open('xb') as stream: stream.write(raw)
(root/'.tmp/scholar-intent-correspondence-test-templates-before-v1.json').write_text(json.dumps({'file':str(source),'sha256':hashlib.sha256(raw).hexdigest()},indent=2),encoding='utf-8')
print('PASS: observed WAL cause/context recorded before test fixture correction; byte assertion retained; original test saved.')
