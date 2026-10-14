"""Fix the quiescent physical WAL baseline; preserve every rejection assertion."""
from pathlib import Path
import hashlib,json
repo=Path.cwd();out=repo/'.tmp/scholar-g10-rejection-baseline-v1';out.mkdir()
p=repo.parent/'RSTV4/tests/test_research_conversation.py'
original=repo/'.tmp/scholar-g10-discussion-rejection-diagnostic-v1/unchanged-source/tests/test_research_conversation.py'
assert p.read_bytes()==original.read_bytes(),'Concurrent test changes must be reviewed first'
(out/'test_research_conversation.py.before.raw').write_bytes(p.read_bytes())
for name in ['repomemory/findings.md','rules/testing-contracts.md']:
    item=repo/name;(out/(item.name+'.prior.raw')).write_bytes(item.read_bytes())
    with item.open('a',encoding='utf-8',newline='') as f:f.write('''

2026-10-13 rejection physical-baseline execution contract: unchanged isolated
test passes1/1. Full-suite failure remains retained1077/1. Database connect enables
WAL; discussion shutdown drains threads but does not establish a checkpointed
physical .db baseline while other fixture SQLite connections can remain open.
Before comparing rejected requests against main-file bytes, explicitly checkpoint
the completed legitimate writes and require wal_checkpoint(TRUNCATE)==(0,0,0).
This strengthens setup: no outstanding committed WAL frames may be hidden by the
physical baseline. Preserve every404/rawDB-equality/modelcall-count1 assertion;
no product mutation or fixture removal/rewritten expected response. Exact original
test raw backup retained. Deferred checkpoint is a supported failure mechanism;
the original full failure's specific connection owner remains unproved. Run the
affected source-bound discussion suites, then full current suite under frozen
source AND tests hashes; neither a narrowpass nor new setup erases originalfailure.
''')
text=p.read_text(encoding='utf-8')
assert text.count('from __future__ import annotations')==1
text=text.replace('from __future__ import annotations','from __future__ import annotations\n\nfrom contextlib import closing',1)
old='''    client.app.state.discussions.shutdown()
    for owner, parent in [(bound, "missing-message"), (other, first["messages"][-1]["message_id"])]:'''
assert text.count(old)==1
new='''    client.app.state.discussions.shutdown()
    # Main-file bytes must include all preceding committed WAL frames. A stopped
    # executor alone does not checkpoint an otherwise open fixture connection.
    with closing(sqlite3.connect(db)) as checkpoint:
        assert checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
    for owner, parent in [(bound, "missing-message"), (other, first["messages"][-1]["message_id"])]:'''
text=text.replace(old,new)
assert text.count('assert db.read_bytes() == before')==p.read_text(encoding='utf-8').count('assert db.read_bytes() == before')
p.write_text(text,encoding='utf-8')
(out/'receipt.json').write_text(json.dumps({'status':'EXECUTION_BASELINE_CHECKPOINT_ADDED_NOT_VERIFIED','product_changed':False,'all_original_rejection_assertions_preserved':True,'original_test_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'current_test_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'full_current_suite_complete':False},indent=2),encoding='utf-8')
print('Preserved exact original rejection assertions; added explicit fully drained WAL baseline.')
