from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
repo = Path.cwd()
out = repo / ".tmp/scholar-g09-runtime-restart-v2"
out.mkdir()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fixture = read(repo / ".tmp/scholar-citation-source-native-v1.json")
db = Path(fixture["root"]) / "data/catalog.db"

def tables():
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return {r[0]: [dict(x) for x in conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid')]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

def ps(script):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, encoding="utf-8-sig", check=True)
    assert not result.stderr.strip(), result.stderr
    return json.loads(result.stdout or "null")

def row(pid):
    return ps(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress")

def listeners(port):
    result = ps(f"@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -eq {port} | Select-Object -ExpandProperty OwningProcess) | ConvertTo-Json -Compress")
    return [result] if isinstance(result, int) else result or []

def ready(process, port):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        assert process.poll() is None, ("new owned runtime exited", process.returncode)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    assert process.poll() is None and len(listeners(port)) == 1
    return row(listeners(port)[0])

before = tables()
digest = sha(db)
assert len(before) == 109 and len(before["studio_model_calls"]) == 16
assert all(v["status"] not in {"RUNNING", "QUEUED"} for t in ["studio_jobs", "research_discussion_jobs"] for v in before[t])
assert not listeners(3008) and not listeners(8881)
old_pids = [4508, 109408, 109324, 64400, 76012, 115132]
assert all(row(pid) is None for pid in old_pids)
(out / "before-all-tables.json").write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
seal = read(repo / ".tmp/scholar-g07-seal-v1.json")
manifest = read(Path(seal["directory"]) / "manifest.json")
assert all(sha(p) == h for p, h in manifest["current_source_sha256"].items())
build = read(repo / ".tmp/scholar-g07-build-v1.json")
print(json.dumps({"build_receipt_keys": list(build)}, ensure_ascii=False), flush=True)
front_cwd = Path("C:/Users/ALANDE~1/AppData/Local/Temp/scui-g07-build-2aju2a31/writing-studio").resolve()
assert front_cwd.is_dir() and front_cwd.parent.name == "scui-g07-build-2aju2a31"
assert Path(build["root"]).resolve() == front_cwd
assert all(sha(Path(build["source"]) / p) == h for p, h in build["before"].items())
assert all(sha(front_cwd / p) == h for p, h in build["before"].items() if Path(p).parts[0] != "dist")
assert all(sha(front_cwd / p) == h for p, h in build["dist_files"].items())
assert {str(p.relative_to(front_cwd)) for p in (front_cwd / "dist").rglob("*") if p.is_file()} == set(build["dist_files"])
assert (front_cwd / "package.json").is_file()
assert (front_cwd / "dist").is_dir()
helper = repo / ".tmp/scholar-g09-serve-only-v1.py"
python = repo / ".uuma-local/scholar-collection-verification-v1/Scripts/python.exe"
with (out / "backend.log").open("x", encoding="utf-8") as log:
    back = subprocess.Popen([str(python), str(helper)], cwd=repo, env=os.environ.copy(),
                            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
back_listener = ready(back, 8881)
back_chain = [back_listener]
if back_listener["ProcessId"] != back.pid:
    assert back_listener["ParentProcessId"] == back.pid
    back_chain.append(row(back.pid))
assert all(helper.name in v["CommandLine"] for v in back_chain)
assert tables() == before and sha(db) == digest
env = os.environ.copy()
env["NODE_OPTIONS"] = "--max-old-space-size=512"
env["UV_THREADPOOL_SIZE"] = "1"
with (out / "frontend.log").open("x", encoding="utf-8") as log:
    front = subprocess.Popen(["cmd.exe", "/c", "npm.cmd", "run", "start", "--", "--port", "3008", "--hostname", "127.0.0.1"],
                             cwd=front_cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
front_listener = ready(front, 3008)
chain = [front_listener]
while chain[-1]["ProcessId"] != front.pid:
    parent = row(chain[-1]["ParentProcessId"])
    assert parent is not None and len(chain) < 6
    chain.append(parent)
assert "scui-g07-build-2aju2a31" in front_listener["CommandLine"] and "--port 3008" in front_listener["CommandLine"]
assert all(row(v["ProcessId"]) == v for v in chain + back_chain)
after = tables()
assert after == before and sha(db) == digest
receipt = {"status": "PASS_RESUME_EXISTING_DATA_OWNED_RUNTIME", "stopped_processes": [],
           "old_confirmed_missing_pids": old_pids, "front_cwd": str(front_cwd),
           "frontend_chain": chain, "backend_chain": back_chain, "backend_helper": str(helper),
           "backend_helper_sha256": sha(helper), "all109_tables_exact": True,
           "database_bytes_exact": True, "source17_exact": True, "new_models": 0,
           "all_model_tasks_denied": True, "seed_or_reset": False,
           "database_sha256": digest, "overall11_complete": False}
(out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "after-all-tables.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False), flush=True)
