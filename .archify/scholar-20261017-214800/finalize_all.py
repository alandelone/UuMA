from pathlib import Path
import json
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
CLI = Path(r"C:/Users/Ling's/.codex/skills/archify/bin/archify.mjs")
NAMES = {'architecture':'scholar-architecture','workflow':'scholar-workflow','sequence':'scholar-sequence','dataflow':'scholar-dataflow','class':'scholar-code'}
results = []
for mode in sys.argv[1:] or list(NAMES):
    folder=BASE/mode
    command=['node',str(CLI),'finalize',mode,str(folder/'candidate.json'),str(folder/(NAMES[mode]+'.html')),'--repo-root',str(ROOT),'--quality','showcase','--json']
    print('FINALIZING '+mode,flush=True)
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (folder/'finalize-command.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    print(result.stdout[-18000:],flush=True)
    if result.stderr: print(result.stderr[-2000:],flush=True)
    results.append({'type':mode,'exit_code':result.returncode})
(BASE/'run-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
raise SystemExit(1 if any(r['exit_code'] for r in results) else 0)
