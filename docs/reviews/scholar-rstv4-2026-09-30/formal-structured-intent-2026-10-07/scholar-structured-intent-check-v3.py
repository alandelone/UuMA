import subprocess, sys, time
from pathlib import Path
root=Path(r'C:\Users\Alandelone\CodeSpace_Local\RSTV4')
commands=[[str(root/'.venv/Scripts/python.exe'),'-m','ruff','check','src/rstv4/model_gateway.py','src/rstv4/skeleton_intent.py','src/rstv4/acquisition_worker.py','src/rstv4/fieldkg_workspace.py','src/rstv4/research_views.py','src/rstv4/skeleton_audit.py','tests/test_skeleton_intent.py'],[str(root/'.venv/Scripts/python.exe'),'-m','pytest','-q','tests/test_skeleton_quality.py','tests/test_skeleton_intent.py','tests/test_acquisition_deep_read.py','tests/test_track_scientific_workspace.py','tests/test_fieldkg_workspace.py']]
commands.insert(0,[str(root/'.venv/Scripts/python.exe'),'-m','ruff','check','--fix','src/rstv4/skeleton_intent.py','tests/test_skeleton_intent.py'])
commands.append(['node','tests/catalog_research_workspaces.mjs'])
start=time.monotonic()
with open(Path(__file__).with_suffix('.log'),'w',encoding='utf-8') as log:
 for command in commands:
  result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace')
  log.write('COMMAND '+repr(command)+'\n'+result.stdout+result.stderr+'\nEXIT '+str(result.returncode)+'\n');log.flush()
  print(result.stdout+result.stderr,flush=True)
  if result.returncode:sys.exit(result.returncode)
print('PASS elapsed',time.monotonic()-start,flush=True)
