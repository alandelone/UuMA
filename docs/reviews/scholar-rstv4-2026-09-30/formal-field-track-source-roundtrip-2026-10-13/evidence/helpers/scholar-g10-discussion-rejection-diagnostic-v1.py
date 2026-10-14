"""Run the unchanged failed rejection contract once, retaining full failure state."""
from pathlib import Path
import hashlib,json,os,subprocess,time
repo=Path.cwd();out=repo/'.tmp/scholar-g10-discussion-rejection-diagnostic-v1';out.mkdir()
source=repo.parent/'RSTV4'
for name in ['repomemory/findings.md','rules/testing-contracts.md']:
    p=repo/name;(out/(p.name+'.prior.raw')).write_bytes(p.read_bytes())
    with p.open('a',encoding='utf-8',newline='') as stream:stream.write('''

2026-10-13 current-default-endpoint regression: current-full-tests-v2 terminal
1077PASS/1FAIL/20warnings; unknown-or-other-scope parent returned404 but rawDB
bytes differed at change counter byte27 after preceding legitimate discussion.
Earlier full G10 suite1078PASS. Exactly two shared source edits are default URL
literals; all175 remaining backend files exact. No causal claim connects URL to
this rejection failure. Retain full failed log/source context; run the unchanged
single rejection test once with diagnostic exception-state capture. Existing
assertions404/rawbytes/callcount1 remain unchanged. Do not count a narrow pass as
full current-suite completion, ignore the failure, or rerun any native/model job.
''')
(out/'original-failed-full-suite.log').write_bytes((repo/'.tmp/scholar-g10-current-full-tests-v2/pytest.log').read_bytes())
for name in ['tests/test_research_conversation.py','tests/test_research_discussions.py','src/rstv4/research_discussions.py']:
    p=source/name;dest=out/'unchanged-source'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
plugin=out/'rejection_state_capture.py'
plugin.write_text('''from pathlib import Path
import hashlib,json,sqlite3
OUT=Path(__file__).parent
def pytest_exception_interact(node,call,report):
    if not call.excinfo:return
    records=[]
    for entry in call.excinfo.traceback:
        data=entry.frame.f_locals
        if not isinstance(data.get('before'),bytes) or 'db' not in data:continue
        db=Path(data['db']);before=data['before'];after=db.read_bytes()
        (OUT/'failed-before.db.raw').write_bytes(before)
        (OUT/'failed-after.db.raw').write_bytes(after)
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
            conn.row_factory=sqlite3.Row
            tables={r[0]:[dict(row) for row in conn.execute('SELECT * FROM "'+r[0]+'"')] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
        (OUT/'failed-all-current-tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf-8')
        records.append({'db':str(db),'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest(),'parent':data.get('parent'),'before_change_counter':int.from_bytes(before[24:28],'big'),'after_change_counter':int.from_bytes(after[24:28],'big')})
    (OUT/'exception-state.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
''',encoding='utf-8')
env=os.environ.copy();env['PYTHONPATH']=str(out)+os.pathsep+env.get('PYTHONPATH','')
before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'src/rstv4').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
(out/'source-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
started=time.monotonic()
with (out/'pytest.log').open('x',encoding='utf-8') as log:
    result=subprocess.run([str(repo/'.uuma-local/scholar-collection-verification-v1/Scripts/python.exe'),'-m','pytest','tests/test_research_conversation.py::test_unknown_or_other_scope_parent_rolls_back_before_model','-q','-p','rejection_state_capture'],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in before.items())
receipt={'status':'FOCUSED_UNCHANGED_CONTRACT_PASS' if not result.returncode else 'FOCUSED_UNCHANGED_CONTRACT_FAILED','exit_code':result.returncode,'seconds':round(time.monotonic()-started,2),'production_and_assertions_unchanged':True,'full_current_suite_complete':False,'summary':(out/'pytest.log').read_text(encoding='utf-8')[-4000:]}
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False),flush=True)
raise SystemExit(result.returncode)
