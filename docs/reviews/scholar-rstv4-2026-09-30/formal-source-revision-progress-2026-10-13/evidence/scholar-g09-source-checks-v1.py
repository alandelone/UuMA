from pathlib import Path
import json
import subprocess
import sys

repo = Path.cwd()
out = repo / ".tmp/scholar-g09-source-reader-repair-v1/checks-v1"
out.mkdir()
front = repo.parent / "writing-studio"
back = repo.parent / "RSTV4"
python = repo / ".uuma-local/scholar-collection-verification-v1/Scripts/python.exe"
checks = [
    ("source-context-tests", [str(python), "-m", "pytest", "tests/test_studio_live_source_reader.py", "tests/test_studio_source_context.py", "tests/test_studio_discussion_fixed_references.py", "-q"], back),
    ("typecheck", ["cmd.exe", "/c", "node_modules\\.bin\\tsc.cmd", "--noEmit", "--incremental", "false"], front),
    ("lint", ["cmd.exe", "/c", "node_modules\\.bin\\oxlint.cmd", "--type-aware", "components/studio-evidence-source.tsx", "components/studio-source-context.tsx", "components/studio-workspace.tsx", "lib/studio-api.ts", "lib/studio-types.ts", "lib/studio-downloads.ts"], front),
    ("file-proxy", ["node", "tests/unit/studio-downloads.cjs"], front),
    ("response-review", ["node", "tests/unit/studio-response-review.cjs"], front),
]
results = []
for name, command, cwd in checks:
    with (out / (name + ".log")).open("x", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    results.append({"name": name, "exit_code": result.returncode})
    print(json.dumps(results[-1]), flush=True)
    if result.returncode:
        print((out / (name + ".log")).read_text(encoding="utf-8", errors="replace")[-6500:])
        break
(out / "receipt.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
assert len(results) == len(checks) and all(r["exit_code"] == 0 for r in results)
