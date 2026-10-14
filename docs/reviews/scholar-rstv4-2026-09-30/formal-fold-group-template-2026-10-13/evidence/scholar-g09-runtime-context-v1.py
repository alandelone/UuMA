"""Preserve failed recovery and add missing build-receipt execution context first."""
from pathlib import Path
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
repo = Path.cwd()
out = repo / ".tmp/scholar-g09-runtime-restart-v1/context-v1"
out.mkdir()
original = repo / ".tmp/scholar-g09-runtime-restart-v1.py"
(out / "failed-runtime-restart-v1.py").write_bytes(original.read_bytes())
notes = {
    "repomemory/findings.md": """

## 2026-10-13: G09 existing-preview restart build-receipt context

Failure class MISSING_CONTEXT: restart-v1 compared the isolated compiled preview
against build receipt `before`, whose defined purpose is the ORIGINAL workspace
and its ORIGINAL production dist snapshot. AssertionError at line70 occurred
BEFORE either Popen. The following diagnostic also attempted to read an original
old BUILD_ID manifest path in the separately rebuilt preview and raised
FileNotFoundError for dist/client/_next/static/10a9165e-99e4-46d7-bcf9-5d44b37a0bef/_buildManifest.js.
Neither attempt started/stopped a process, seeded/reset data, or modified product code.
Original sources, failure helper and all109-table snapshot are retained in
.tmp/scholar-g09-runtime-restart-v1 and its context-v1 subdirectory.

Actual declared build receipt: status PASS, source root writing-studio, target
scui-g07-build-2aju2a31/writing-studio, api http://127.0.0.1:8881/api.
Freshly proved ALL180 original workspace+original-dist hashes exact, ALL copied
non-dist source hashes exact, and ALL76 ACTUAL compiled preview dist_files hashes
exact. The mismatches in the incorrect comparison were exclusively dist files.
Require these separate complete authorities BEFORE recovery: original180 unchanged,
copied non-dist source exact, complete actual76-dist hash AND membership equality,
current17 acceptance sources exact, no running owned jobs, old PIDs truly missing,
both target ports absent, no seed/remote model fallback. After start retain exact
all109-table and database-byte comparisons plus fresh PID/creation/parent/command
identities. This adds receipt interpretation; no valid guard is weakened.
Use a fresh exclusive v2 helper/output, run the narrow restart, then complete
the affected full deterministic RSTV4 suite. Original118/all11 remain active;
G08 native evidence is independently PASS but full11 is incomplete.
""",
    "rules/testing-contracts.md": """

2026-10-13 isolated preview restart receipt context BEFORE recovery-v2:
Build receipt `before` fingerprints the ORIGINAL source workspace, including
its original dist, to prove that isolated building did not mutate user work.
It is NOT the isolated compiled output fingerprint. `dist_files` is the complete
ACTUAL isolated output hash map. Require every original before hash unchanged,
every copied non-dist source hash exact, every actual dist_files hash exact AND
actual dist membership exact, plus current acceptance source vector before start.
Do not omit either authority or reuse original BUILD_ID paths for the new dist.
Preserve original failed helper/diagnostics. On confirmed absent owned runtime,
start only the verified existing isolated preview and serve-only backend; no
seeding/reset, old scientific/model rerun, remote fallback or broad process kill.
Retain every raw database-byte/all-table/job/ownership assertion after recovery.
Run narrow recovery then full affected deterministic suite after this context fix.
""",
}
for name, text in notes.items():
    target = repo / name
    previous = target.read_bytes()
    backup = out / (target.name + ".previous.raw")
    backup.write_bytes(previous)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(text)
    assert target.read_bytes().startswith(previous)
    assert backup.read_bytes() == previous

code = original.read_text(encoding="utf-8")
old = 'assert all(sha(front_cwd / p) == h for p, h in build["before"].items())'
assert code.count(old) == 1
new = '''assert all(sha(Path(build["source"]) / p) == h for p, h in build["before"].items())
assert all(sha(front_cwd / p) == h for p, h in build["before"].items() if Path(p).parts[0] != "dist")
assert all(sha(front_cwd / p) == h for p, h in build["dist_files"].items())
assert {str(p.relative_to(front_cwd)) for p in (front_cwd / "dist").rglob("*") if p.is_file()} == set(build["dist_files"])'''
code = code.replace(old, new).replace('".tmp/scholar-g09-runtime-restart-v1"', '".tmp/scholar-g09-runtime-restart-v2"')
new_helper = repo / ".tmp/scholar-g09-runtime-restart-v2.py"
with new_helper.open("x", encoding="utf-8") as stream:
    stream.write(code)
result = {"status": "MISSING_CONTEXT_RECORDED_BEFORE_V2", "no_product_change": True,
          "failed_source_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
          "new_helper_sha256": hashlib.sha256(new_helper.read_bytes()).hexdigest(),
          "all_original_source_and_actual_dist_guards_required": True,
          "original118_all11_scope_retained": True}
(out / "receipt.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result), flush=True)
