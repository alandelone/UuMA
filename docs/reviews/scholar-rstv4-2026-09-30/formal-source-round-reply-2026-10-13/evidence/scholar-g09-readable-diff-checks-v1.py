from pathlib import Path
import subprocess
import json

repo = Path.cwd()
out = repo / ".tmp/scholar-g09-readable-diff-v1/checks-v1"
out.mkdir()
front = repo.parent / "writing-studio"
checks = [
    ("ruff", [str(repo / ".venv/Scripts/python.exe"),"-m","ruff","check",str(repo.parent / "RSTV4/src/rstv4/studio.py"),str(repo.parent / "RSTV4/tests/test_studio_response_citation_display.py")], repo),
    ("typecheck", ["cmd.exe","/c","node_modules\\.bin\\tsc.cmd","--noEmit","--incremental","false"], front),
    ("lint", ["cmd.exe","/c","node_modules\\.bin\\oxlint.cmd","--type-aware","components/studio-response-review.tsx","components/studio-workspace.tsx","lib/studio-types.ts"], front),
    ("response-review", ["node","tests/unit/studio-response-review.cjs"], front),
]
results = []
for name, command, cwd in checks:
    with (out / (name + ".log")).open("x", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    results.append({"name":name,"exit_code":result.returncode})
    print(json.dumps(results[-1]), flush=True)
    if result.returncode:
        print((out / (name + ".log")).read_text(encoding="utf-8",errors="replace")[-6500:])
        break
(out / "receipt.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
assert len(results) == len(checks) and all(v["exit_code"] == 0 for v in results)
