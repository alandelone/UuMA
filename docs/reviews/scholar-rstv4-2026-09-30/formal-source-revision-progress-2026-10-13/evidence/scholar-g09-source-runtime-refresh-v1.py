from pathlib import Path

base = Path(".tmp/scholar-g09-runtime-restart-v2.py").read_text(encoding="utf-8")
prefix = base[:base.index("before = tables()")].replace("scholar-g09-runtime-restart-v2", "scholar-g09-source-runtime-refresh-v1")
exec(compile(prefix, __file__, "exec"))
before = tables()
digest = sha(db)
assert len(before) == 109 and len(before["review_comments"]) == 206
assert len(before["studio_model_calls"]) == 16
assert all(v["status"] not in {"QUEUED", "RUNNING"} for name in ["studio_jobs", "research_discussion_jobs"] for v in before[name])
old = read(repo / ".tmp/scholar-g09-runtime-restart-v2/receipt.json")
owned = old["frontend_chain"] + old["backend_chain"]
assert all(row(v["ProcessId"]) == v for v in owned)
assert listeners(3008) == [old["frontend_chain"][0]["ProcessId"]]
assert listeners(8881) == [old["backend_chain"][0]["ProcessId"]]
build = read(repo / ".tmp/scholar-g09-source-build-v1.json")
assert build["status"] == "PASS" and build["api"] == "http://127.0.0.1:8881/api"
front_cwd = Path(build["root"]).resolve()
assert front_cwd.parent.name.startswith("scui-g09-source-build-")
assert all(sha(Path(build["source"]) / p) == h for p,h in build["before"].items())
assert all(sha(front_cwd / p) == h for p,h in build["before"].items() if Path(p).parts[0] != "dist")
assert all(sha(front_cwd / p) == h for p,h in build["dist_files"].items())
assert {str(p.relative_to(front_cwd)) for p in (front_cwd / "dist").rglob("*") if p.is_file()} == set(build["dist_files"])
backend_sources = {str(p):sha(p) for p in (repo.parent / "RSTV4/src/rstv4").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
helper = repo / ".tmp/scholar-g09-serve-only-v1.py"
assert sha(helper) == old["backend_helper_sha256"]
(out / "before-all-tables.json").write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "verified-prior-owned-processes.json").write_text(json.dumps(owned, indent=2), encoding="utf-8")
for process in owned:
    assert row(process["ProcessId"]) == process
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    f"Stop-Process -Id {process['ProcessId']} -Force -ErrorAction Stop"], check=True,
                   capture_output=True)
assert not listeners(3008) and not listeners(8881)
assert all(row(p["ProcessId"]) is None for p in owned)
assert tables() == before and sha(db) == digest
python = repo / ".uuma-local/scholar-collection-verification-v1/Scripts/python.exe"
with (out / "backend.log").open("x", encoding="utf-8") as log:
    back = subprocess.Popen([str(python),str(helper)], cwd=repo, env=os.environ.copy(), stdout=log,
                            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
back_listener = ready(back, 8881)
back_chain = [back_listener]
if back_listener["ProcessId"] != back.pid:
    assert back_listener["ParentProcessId"] == back.pid
    back_chain.append(row(back.pid))
assert all(helper.name in v["CommandLine"] for v in back_chain)
assert tables() == before and sha(db) == digest
env = os.environ.copy()
env.update(NODE_OPTIONS="--max-old-space-size=512", UV_THREADPOOL_SIZE="1")
with (out / "frontend.log").open("x", encoding="utf-8") as log:
    front = subprocess.Popen(["cmd.exe","/c","npm.cmd","run","start","--","--port","3008","--hostname","127.0.0.1"],
                             cwd=front_cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
front_listener = ready(front, 3008)
chain = [front_listener]
while chain[-1]["ProcessId"] != front.pid:
    parent = row(chain[-1]["ParentProcessId"])
    assert parent is not None and len(chain) < 6
    chain.append(parent)
assert front_cwd.parent.name in front_listener["CommandLine"] and "--port 3008" in front_listener["CommandLine"]
assert all(row(v["ProcessId"]) == v for v in chain + back_chain)
after = tables()
assert after == before and sha(db) == digest
assert all(sha(Path(p)) == h for p,h in backend_sources.items())
receipt = {"status":"PASS_G09_NEW_SOURCE_READER_OWNED_RUNTIME", "frontend_chain":chain,
           "backend_chain":back_chain, "front_cwd":str(front_cwd), "backend_helper":str(helper),
           "backend_helper_sha256":sha(helper), "stopped_verified_owned_processes":owned,
           "all109_tables_exact":True, "database_bytes_exact":True, "database_sha256":digest,
           "all_model_tasks_denied":True, "seed_or_reset":False, "source_build_original_and_copy_exact":True,
           "backend_source_sha256":backend_sources, "overall11_complete":False}
(out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "after-all-tables.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in receipt.items() if k != "backend_source_sha256"}), flush=True)
