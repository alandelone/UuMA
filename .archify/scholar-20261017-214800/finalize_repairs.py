from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
CLI=Path(r"C:/Users/Ling's/.codex/skills/archify/bin/archify.mjs")
failed=False
for mode,name,review in [('architecture','scholar-architecture','review-2'),('workflow','scholar-workflow',None)]:
    folder=BASE/mode
    command=['node',str(CLI),'finalize',mode,str(folder/'candidate.json'),str(folder/(name+'.html')),'--repo-root',str(ROOT),'--quality','showcase','--json']
    if review: command+=['--out-dir',str(folder/review)]
    print('FINALIZING '+mode,flush=True)
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (folder/'finalize-repair-1.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    print(result.stdout,flush=True)
    if result.stderr: print(result.stderr[-2000:],flush=True)
    failed=failed or result.returncode!=0
raise SystemExit(1 if failed else 0)
