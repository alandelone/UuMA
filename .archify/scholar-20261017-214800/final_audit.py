from pathlib import Path
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
source_paths=set()
for mode in ['architecture','workflow','sequence','dataflow','class']:
    c=json.loads((BASE/mode/'candidate.json').read_text(encoding='utf-8'))
    for node in c.get('components',c.get('nodes',c.get('participants',c.get('types',[])))):
        source_paths.update(s['path'] for s in node.get('sources',[]))
r=subprocess.run(['git','diff','--name-only','HEAD','--',*sorted(source_paths)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
assert r.returncode==0 and not r.stdout.strip(),r.stdout
print('All 17 diagram source files match pinned HEAD; no product source changes.',flush=True)
r=subprocess.run(['git','status','--short'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
print(r.stdout,flush=True)
raise SystemExit(subprocess.run([sys.executable,'-Xutf8',str(BASE/'package_and_verify.py')],cwd=ROOT).returncode)
