from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
CLI=Path(r"C:/Users/Ling's/.codex/skills/archify/bin/archify.mjs")
for mode,name in [('sequence','scholar-sequence'),('dataflow','scholar-dataflow')]:
    folder=BASE/mode
    command=['node',str(CLI),'finalize',mode,str(folder/'candidate.json'),str(folder/(name+'.html')),'--repo-root',str(ROOT),'--quality','showcase','--json','--out-dir',str(folder/'review-3')]
    print('FINALIZING '+mode,flush=True)
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (folder/'finalize-environment-retry.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    print(result.stdout,flush=True)
    if result.stderr: print(result.stderr[-2000:],flush=True)
    if result.returncode: raise SystemExit(result.returncode)
raise SystemExit(subprocess.run([sys.executable,'-Xutf8',str(BASE/'package_and_verify.py')],cwd=ROOT).returncode)
