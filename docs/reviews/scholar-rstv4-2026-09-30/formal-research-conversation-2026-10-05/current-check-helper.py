import os
import shutil
import subprocess
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
backend,front=repo.parent/'RSTV4',repo.parent/'writing-studio'
os.environ.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
node=shutil.which('node')
commands=[
 ([node,'tests/unit/catalog-research-chat.mjs'],front),
 ([node,'tests/catalog_research_workspaces.mjs'],backend),
 ([node,'tests/catalog_research_overview.mjs'],backend),
 ([node,'tests/unit/catalog-return.mjs'],front),
 ([node,'--check','src/rstv4/catalog_research_chat.js'],backend),
 ([node,'-e',"const fs=require('fs'),vm=require('vm');for(const m of fs.readFileSync('src/rstv4/catalog_web.html','utf8').matchAll(/<script(?:\\s[^>]*)?>([\\s\\S]*?)<\\/script>/g)){new vm.Script(m[1]);}console.log('Shipped Catalog inline scripts parse');"],backend),
 ([str(backend/'.venv/Scripts/python.exe'),'-m','ruff','check','src/rstv4/research_context.py','src/rstv4/research_discussions.py','src/rstv4/model_gateway.py','src/rstv4/catalog_web.py','tests/test_research_discussions.py','tests/test_research_conversation.py'],backend),
 ([node,str(front/'node_modules/oxlint/bin/oxlint'),'--disable-nested-config',str(backend/'src/rstv4/catalog_research_chat.js'),str(backend/'src/rstv4/catalog_research_workspaces.js'),str(front/'tests/unit/catalog-research-chat.mjs')],front),
 ([str(backend/'.venv/Scripts/python.exe'),'-m','pytest','tests/test_research_discussions.py','tests/test_research_conversation.py','tests/test_fieldkg_workspace.py','tests/test_research_workspace.py','tests/test_catalog_web.py','-q'],backend),
 (['git','diff','--check','--','src/rstv4/catalog_web.py','src/rstv4/catalog_web.html','src/rstv4/catalog_research_workspaces.js','src/rstv4/model_gateway.py'],backend),
]
path=repo/'.tmp/scholar-conversation-check-v6.log'
with path.open('x',encoding='utf-8') as log:
 for command,cwd in commands:
  log.write(f'CHECK {command[1:]}\n');log.flush()
  result=subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
  log.write(f'Exit: {result.returncode}\n');log.flush()
  if result.returncode:
   print(path.read_text(encoding='utf-8'));raise SystemExit(result.returncode)
print(path.read_text(encoding='utf-8'))
