import re,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1];project=repo.parent/'RSTV4';python=project/'.venv/Scripts/python.exe'
html=(project/'src/rstv4/catalog_web.html').read_text(encoding='utf-8');scripts=re.findall(r'<script>([\s\S]*?)</script>',html);assert len(scripts)==1
inline=repo/'.tmp/scholar-frontier-inline-v6.js'
with inline.open('x',encoding='utf-8') as h:h.write(scripts[0])
commands=[['node','--check',str(inline)],['node','tests/catalog_collection_progress.mjs'],['node','tests/catalog_collections.mjs'],['node','tests/catalog_existing_papers.mjs'],[str(python),'-m','ruff','check','src/rstv4/collection_runtime.py','src/rstv4/acquisition.py','src/rstv4/models.py','src/rstv4/acquisition_worker.py','src/rstv4/collection_web.py','tests/test_collection_runtime.py'],[str(python),'-X','utf8','-m','pytest','tests/test_collection_runtime.py','tests/test_collection_workspace.py','tests/test_catalog_paper_selection.py','tests/test_native_paperpool.py','-q']]
with (repo/'.tmp/scholar-frontier-ui-check-v6.log').open('x',encoding='utf-8') as log:
 for command in commands:
  log.write('RUN '+repr(command)+'\n');log.flush();result=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT);log.flush();print('Result',result.returncode,flush=True)
  if result.returncode:raise SystemExit(result.returncode)
