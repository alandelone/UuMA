from pathlib import Path

root=Path.cwd()
previous=(root/'.tmp/scholar-intent-correspondence-rollback-baseline-v2.py').read_text(encoding='utf-8')
successor=previous.replace('rollback-baseline-v2','rollback-baseline-v3')
successor=successor.replace("['page_size','page_count','freelist_count','schema_version']", "['page_size','page_count','freelist_count','schema_version','auto_vacuum']")
old='        page4 = [tuple(row) for row in conn.execute("SELECT name,pageno,pagetype,ncell FROM dbstat WHERE pageno=4")]'
assert successor.count(old)==1
successor=successor.replace(old,"        page4 = 'DBSTAT_UNAVAILABLE_IN_OBSERVED_BUILD'")
successor=successor.replace("result = {'pytest_exit':int(status)", """page_size = before_state['params']['page_size']
trunk = int.from_bytes(before_raw[32:36], 'big')
trunks = []
leaves = []
while trunk:
    assert trunk not in trunks
    trunks.append(trunk)
    at = (trunk-1)*page_size
    count = int.from_bytes(before_raw[at+4:at+8], 'big')
    assert count <= page_size//4-2
    leaves.extend(int.from_bytes(before_raw[at+8+n*4:at+12+n*4], 'big') for n in range(count))
    trunk = int.from_bytes(before_raw[at:at+4], 'big')
assert len(trunks)+len(leaves)==before_state['params']['freelist_count']
changed_pages=sorted({i//page_size+1 for i in diffs})
result = {'freelist_trunks_before':trunks,'freelist_leaves_before':leaves,
          'changed_pages':changed_pages,'only_before_free_leaf_pages_changed':bool(diffs) and set(changed_pages).issubset(set(leaves)),
          'pytest_exit':int(status)""")
with (root/'.tmp/scholar-intent-correspondence-rollback-baseline-v3.py').open('x',encoding='utf-8') as stream:
    stream.write(successor)
entry='''

2026-10-09 rollback diagnostic-v2 failure retained: observed Python SQLite3.53.4 has
no SQLITE_ENABLE_DBSTAT_VTAB compile flag, so the optional dbstat query failed BEFORE
the original rollback assertion ran, for both current and privately frozen prior source.
Do not label those instrumented invocations as product rollback failures. Do not assume
optional SQLite introspection extensions or install/change the runtime. Keep raw before
image; successor parses only standard file-format freelist pages and reads every real row
through the unchanged driver. Primary docs: https://www.sqlite.org/dbstat.html and
https://www.sqlite.org/atomiccommit.html section7.3 explain optional DBSTAT and unjournaled
free leaf pages. Whether that explains this actual failure remains pending exact images.
The uninstrumented original focused-v2 and unchanged narrow original test really failed
byte equality; short standalone exact save/rollback passed every row and byte, MainThread
only. Assertions and product transactions remain intact. Full findings freshly read.
Shared lifecycle was closed/restarted by concurrent scientific work between commands;
no-child No-active-session error retained, fresh whole handoff/mission/gate reread and
resume succeeded. Preserve scientific authority and all ongoing workers; no engine edits.
'''
for name in ['repomemory/findings.md','rules/scholar-native-acceptance.md']:
    path=root/name
    prior=path.read_text(encoding='utf-8')
    path.write_text(prior+entry,encoding='utf-8')
    assert prior in path.read_text(encoding='utf-8')
print('PASS context: optional module failure retained; assertions unchanged; v3 prepared.')
