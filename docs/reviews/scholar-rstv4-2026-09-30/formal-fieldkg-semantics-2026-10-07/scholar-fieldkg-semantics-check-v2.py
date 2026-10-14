import subprocess,sys,time
from pathlib import Path
project=Path(r'C:\Users\Alandelone\CodeSpace_Local\RSTV4')
python=project/'.venv/Scripts/python.exe'
commands=[[str(python),'-m','ruff','check','--fix','src/rstv4/fieldkg_semantics.py','src/rstv4/catalog_web.py','src/rstv4/research_context.py','src/rstv4/fieldkg_workspace.py','src/rstv4/research_views.py'],['node','--check','src/rstv4/catalog_research_workspaces.js'],[str(python),'-m','pytest','-q','tests/test_fieldkg_workspace.py','tests/test_track_scientific_workspace.py','tests/test_research_discussions.py','tests/test_skeleton_intent.py'],['node','tests/catalog_research_workspaces.mjs']]
with Path(__file__).with_suffix('.log').open('w',encoding='utf-8') as log:
 for command in commands:
  result=subprocess.run(command,cwd=project,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace');log.write(repr(command)+'\n'+result.stdout);log.flush();print(result.stdout,flush=True)
  if result.returncode:sys.exit(result.returncode)
