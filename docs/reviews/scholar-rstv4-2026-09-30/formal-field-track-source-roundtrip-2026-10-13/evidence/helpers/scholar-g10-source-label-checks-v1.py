from pathlib import Path
import json
import subprocess

repo=Path.cwd()
front=repo.parent / "writing-studio"
out=repo / ".tmp/scholar-g10-native-v1/source-label-checks-v1"
out.mkdir()
checks=[("typecheck",["cmd.exe","/c","node_modules\\.bin\\tsc.cmd","--noEmit","--incremental","false"]),
        ("lint",["cmd.exe","/c","node_modules\\.bin\\oxlint.cmd","--type-aware","components/studio-source-context.tsx"])]
checks.extend((p.stem,["node",str(p.relative_to(front))]) for p in sorted((front / "tests/unit").glob("*.cjs")))
results=[]
for name,args in checks:
    with (out / (name+".log")).open("x",encoding="utf-8") as f:
        result=subprocess.run(args,cwd=front,stdout=f,stderr=subprocess.STDOUT)
    results.append({"name":name,"exit_code":result.returncode})
    print(json.dumps(results[-1]),flush=True)
    if result.returncode:
        print((out / (name+".log")).read_text(encoding="utf-8",errors="replace")[-4500:])
        break
(out / "receipt.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
assert len(results)==len(checks) and all(v["exit_code"]==0 for v in results)
