import subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1];project=repo.parent/'RSTV4';python=project/'.venv/Scripts/python.exe'
import re
html=(project/'src/rstv4/catalog_web.html').read_text(encoding='utf-8');scripts=re.findall(r'<script>([\s\S]*?)</script>',html);assert len(scripts)==1
inline=repo/'.tmp/scholar-deep-read-inline-v7.js'
with inline.open('x',encoding='utf-8') as h:h.write(scripts[0])
commands=[['node','--check',str(inline)],['node','tests/catalog_deep_read.mjs'],['node','tests/catalog_collection_progress.mjs'],['node','tests/catalog_collections.mjs'],[str(python),'-m','ruff','check','--fix','src/rstv4/acquisition_model_calls.py','src/rstv4/acquisition.py','src/rstv4/acquisition_worker.py','src/rstv4/database.py','src/rstv4/models.py','tests/test_acquisition_deep_read.py','src/rstv4/catalog_web.py','src/rstv4/collection_web.py','src/rstv4/skeleton_audit.py'],[str(python),'-X','utf8','-m','pytest','tests/test_acquisition_deep_read.py','tests/test_native_paperpool.py','tests/test_catalog_paper_selection.py','tests/test_skeleton_quality.py','-q']]
with (repo/'.tmp/scholar-deep-read-check-v7.log').open('x',encoding='utf-8') as log:
 for command in commands:
  result=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT);log.flush();print('Result',result.returncode,flush=True)
  if result.returncode:raise SystemExit(result.returncode)
