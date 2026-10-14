import subprocess, sys, time
from pathlib import Path
root=Path(r'C:\Users\Alandelone\CodeSpace_Local\RSTV4')
commands=[[str(root/'.venv/Scripts/python.exe'),'-m','ruff','check','--fix','src/rstv4/experiment.py','src/rstv4/track_first.py','src/rstv4/catalog_web.py','tests/test_experiment_artifact_trace.py'],[str(root/'.venv/Scripts/python.exe'),'-m','pytest','-q','tests/test_experiment_artifact_trace.py','tests/test_track_first_fieldkg.py','tests/test_experiment.py'],['node','--check','src/rstv4/catalog_research_workspaces.js'],['node','tests/catalog_research_workspaces.mjs']]
start=time.monotonic()
with open(Path(__file__).with_suffix('.log'),'w',encoding='utf-8') as log:
 for command in commands:
  result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
  log.write('COMMAND '+repr(command)+'\n'+result.stdout+result.stderr+'\nEXIT '+str(result.returncode)+'\n');log.flush()
  print(result.stdout+result.stderr,flush=True)
  if result.returncode:sys.exit(result.returncode)
print('PASS elapsed',time.monotonic()-start,flush=True)
