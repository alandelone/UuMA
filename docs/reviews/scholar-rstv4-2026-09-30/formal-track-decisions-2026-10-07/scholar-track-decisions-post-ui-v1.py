import subprocess, sys, time, json, hashlib
from pathlib import Path
root=Path(r'C:\Users\Alandelone\CodeSpace_Local\RSTV4')
commands=[[str(root/'.venv/Scripts/python.exe'),'-m','ruff','check','src/rstv4/track_first.py','src/rstv4/track_scientific_workspace.py','src/rstv4/catalog_web.py','tests/test_track_scientific_workspace.py'],[str(root/'.venv/Scripts/python.exe'),'-m','pytest','-q','tests/test_track_scientific_workspace.py','tests/test_track_first_fieldkg.py','tests/test_fieldkg_workspace.py']]
commands.extend([['node','tests/catalog_track_decisions.mjs'],['node','tests/catalog_research_workspaces.mjs'],['node','tests/catalog_scope_literature.mjs']])
baseline=json.loads((Path(__file__).parent/'scholar-track-decisions-full-v1.json').read_text(encoding='utf-8'))
assert baseline['status']=='PASS' and not baseline['changed_during_verification']
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def snapshot():return {str(p):sha(p.read_bytes()) for base in ['src','tests'] for p in (root/base).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.mjs','.html'}}
before=snapshot()
allowed={str(root/'src/rstv4/catalog_track_decisions.js'),str(root/'tests/catalog_track_decisions.mjs')}
assert {p for p in before.keys()|baseline['after_sha256'].keys() if before.get(p)!=baseline['after_sha256'].get(p)}==allowed
start=time.monotonic()
with open(Path(__file__).with_suffix('.log'),'w',encoding='utf-8') as log:
 for command in commands:
  result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
  log.write('COMMAND '+repr(command)+'\n'+result.stdout+result.stderr+'\nEXIT '+str(result.returncode)+'\n');log.flush()
  print(result.stdout+result.stderr,flush=True)
  if result.returncode:sys.exit(result.returncode)
print('PASS elapsed',time.monotonic()-start,flush=True)

after=snapshot()
assert before==after
proof={'status':'PASS_CURRENT_UI_AND_IDENTICAL_FULL_TESTED_BACKEND','seconds':time.monotonic()-start,'full_receipt_sha256':sha((Path(__file__).parent/'scholar-track-decisions-full-v1.json').read_bytes()),'before_sha256':before,'after_sha256':after,'declared_ui_changed_after_backend':sorted(allowed),'log_sha256':sha(Path(__file__).with_suffix('.log').read_bytes())}
Path(__file__).with_suffix('.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
