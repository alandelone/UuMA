"""Unexecuted source421 G11 runtime; separate from immutable prepared-copy helper.

Operator commands, each through the managed session wrapper:
  ... scholar-all11-g11-runtime-v2.py launch success
  ... scholar-all11-g11-runtime-v2.py stop success
  ... scholar-all11-g11-runtime-v2.py launch identity
  ... scholar-all11-g11-runtime-v2.py stop identity
  ... scholar-all11-g11-runtime-v2.py launch upstream
  ... scholar-all11-g11-runtime-v2.py stop upstream

No auto-copy/migration/build, worker, model, identity action, budget save or Method
execution. Stage POSTs are limited to exact four prepared zero-version refusals.
Private environment values are never logged. Failed startup is never relaunched.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

import psutil


REPO = Path(__file__).resolve().parents[1]
HERE = REPO / ".tmp/scholar-all11-g11-runtime-v2"
BASE_PATH = REPO / ".tmp/scholar-all11-g11-current-v2.py"
PREPARED = REPO / ".tmp/scholar-all11-g11-current-v2"
CONTEXT = REPO / ".tmp/scholar-all11-context-v2"
PORTS = {"catalog": 8875, "studio": 8877, "frontend": 3000}
ROLES = ("success", "identity", "upstream")
REASON = "G11 explicit zero-version software guard only"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(part)
    return result.hexdigest()


def put(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def load_base():
    receipt = read(PREPARED / "receipt.json")
    assert sha(BASE_PATH) == receipt["source421"]["helper_sha256"], "Prepared helper changed"
    spec = importlib.util.spec_from_file_location("immutable_g11_preparation", BASE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, receipt


def identity(pid):
    process = psutil.Process(pid)
    with process.oneshot():
        return {"pid": pid, "create_time": process.create_time(), "cmdline": process.cmdline(),
                "cwd": process.cwd(), "parent_pid": process.ppid()}


def exact(saved):
    try:
        actual = identity(saved["pid"])
    except psutil.NoSuchProcess:
        return None
    assert all(actual[key] == saved[key] for key in ("pid", "create_time", "cmdline", "cwd")), "PID identity changed; do not signal"
    return psutil.Process(saved["pid"])


def absent(saved):
    # A reused PID is not our process; never inspect or signal its descendants.
    try:
        process = psutil.Process(saved["pid"])
        if process.create_time() != saved["create_time"]:
            return True
        assert identity(saved["pid"])["cmdline"] == saved["cmdline"], "Same birth but argv changed"
        return False
    except psutil.NoSuchProcess:
        return True


def port_free(port):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def front_guard(base):
    context = read(CONTEXT / "receipt.json")
    build = Path(context["frontend_root"]).resolve()
    assert len(context["frontend_product_vector"]) == 93
    assert len(context["frontend_dist_vector"]) == 77
    for name, digest in context["frontend_product_vector"].items():
        assert sha(REPO.parent / "writing-studio" / name) == digest, name
        assert sha(build / name) == digest, name
    for name, digest in context["frontend_dist_vector"].items():
        assert sha(build / name) == digest, name
    assert {str(p.relative_to(build)) for p in (build / "dist").rglob("*") if p.is_file()} == set(context["frontend_dist_vector"])
    return context


def guard(base, receipt):
    base.guard_originals(receipt)
    for role, value in receipt["copies"].items():
        root = Path(value["root"])
        assert base.snapshot(root / "data/catalog.db") == read(PREPARED / f"{role}-baseline110.json"), "Full copied110/schema changed: " + role
        assert base.filemap(root) == read(PREPARED / f"{role}-baseline-files.json"), "Copied non-sidecar bytes changed: " + role
    front_guard(base)


def plan_guard(role, base, receipt):
    plan = read(HERE / role / "plan.json")
    assert plan["role"] == role and plan["runtime_sha256"] == sha(Path(__file__))
    assert plan["receipt_sha256"] == sha(PREPARED / "receipt.json")
    assert plan["root"] == receipt["copies"][role]["root"]
    guard(base, receipt)
    return plan


class Deny:
    def analyze(self, *args, **kwargs):
        raise RuntimeError("G11 current read-only runtime denies all model operations")

    operation_id = analyze
    analyze_for_operation = analyze


def launch(role):
    base, receipt = load_base()
    guard(base, receipt)
    HERE.mkdir(exist_ok=True)
    for prior in ROLES[:ROLES.index(role)]:
        stopped = read(HERE / prior / "owned-stop-terminal.json")
        assert stopped["all110_and_files_exact"] and stopped["all_owned_identities_absent"]
    # Do not allow a concurrent role or launch after a partially failed startup.
    for other in ROLES:
        folder = HERE / other
        if folder.exists() and other != role:
            assert (folder / "owned-stop-terminal.json").exists(), "Another role has no terminal stop receipt"
    folder = HERE / role
    folder.mkdir(exist_ok=False)
    components = ["catalog"] + (["studio", "frontend"] if role == "upstream" else [])
    for component in components:
        port_free(PORTS[component])
    context = front_guard(base)
    plan = {"role": role, "root": receipt["copies"][role]["root"], "components": components,
            "runtime_sha256": sha(Path(__file__)), "receipt_sha256": sha(PREPARED / "receipt.json"),
            "nonce": uuid.uuid4().hex, "ports": {name: PORTS[name] for name in components},
            "models_workers_started": 0, "zero_refusals_only": role == "upstream",
            "source421": receipt["source421"], "frontend_root": context["frontend_root"]}
    put(folder / "plan.json", plan)
    for component in components:
        if component == "frontend":
            prior = read(CONTEXT / "frontend-launched.json")["argv"]
            assert len(prior) == 7 and prior[2] == "start" and prior[3] == "--port" and prior[5:] == ["--hostname", "127.0.0.1"]
            argv = [prior[0], prior[1], "start", "--port", "3000", "--hostname", "127.0.0.1"]
            cwd = Path(context["frontend_root"])
            env = os.environ.copy()
            env["NODE_OPTIONS"] = "--max-old-space-size=512"
            env["RSTV4_API"] = "http://127.0.0.1:8877/api"
            env["NEXT_PUBLIC_RSTV4_API"] = "http://127.0.0.1:8877/api"
        else:
            argv = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "serve", role, "--component", component]
            cwd = REPO
            env = os.environ.copy()
        with (folder / f"{component}.log").open("x", encoding="utf-8") as log:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        saved = identity(child.pid)
        put(folder / f"{component}-launched.json", {"identity": saved, "argv": argv,
            "port": PORTS[component], "node_heap_mib": 512 if component == "frontend" else None})
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"{component} exited; preserve logs/identity, do not relaunch")
            if component == "frontend":
                try:
                    with urllib.request.urlopen("http://127.0.0.1:3000/", timeout=1) as response:
                        assert response.status == 200
                    put(folder / "frontend-ready.json", {"identity": saved, "port": 3000,
                        "owned_console_children": [identity(p.pid) for p in psutil.Process(child.pid).children(recursive=True)
                            if p.name().lower() == "conhost.exe"],
                        "production_build_reused": True, "node_heap_mib": 512,
                        "url": "http://127.0.0.1:3000/"})
                    break
                except (OSError, TimeoutError):
                    pass
            elif (folder / f"{component}-ready.json").exists():
                serving = read(folder / f"{component}-ready.json")["identity"]
                if serving != saved:
                    exact(saved)
                    assert any(p.pid == saved["pid"] and p.create_time() == saved["create_time"]
                               for p in psutil.Process(serving["pid"]).parents()), "Serving PID is not our launch descendant"
                put(folder / f"{component}-ownership.json", {"launcher": saved, "serving": serving})
                break
            time.sleep(0.1)
        assert (folder / f"{component}-ready.json").exists(), "Keep launched identity; never relaunch after observation timeout"
    plan_guard(role, base, receipt)
    put(folder / "launch-complete.json", {"status": "OWNED_ROLE_READY_NO_BUSINESS_REPLAY", "role": role,
        "catalog_url": "http://127.0.0.1:8875/?view=all",
        "studio_url": "http://127.0.0.1:3000/" if role == "upstream" else None})
    print(json.dumps(read(folder / "launch-complete.json")), flush=True)


def serve(role, component):
    assert component in {"catalog", "studio"} and (component == "catalog" or role == "upstream")
    base, receipt = load_base()
    plan = plan_guard(role, base, receipt)
    folder = HERE / role
    root = Path(plan["root"])
    baseline = read(PREPARED / f"{role}-baseline110.json")
    sys.path.insert(0, str(base.RST / "src"))
    import uvicorn
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    if component == "catalog":
        from rstv4.catalog_web import create_app
    else:
        from rstv4.studio_api import create_app
    app = create_app(root)
    if component == "catalog":
        app.state.discussions.gateway = Deny()
        app.state.fieldkg_semantics.gateway = Deny()
    else:
        app.state.studio.gateway = Deny()
        app.state.discussions.gateway = Deny()
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3000"],
            allow_credentials=False, allow_methods=["GET", "HEAD", "OPTIONS", "POST"],
            allow_headers=["Content-Type", "If-Match", "X-Operation-Id"])
    assert base.snapshot(root / "data/catalog.db") == baseline, "Constructor changed full110/schema"
    assert base.filemap(root) == read(PREPARED / f"{role}-baseline-files.json"), "Constructor changed payload files"
    serial = 0
    audit_lock = asyncio.Lock()

    class Boundary:
        async def __call__(self, scope, receive, send):
            nonlocal serial
            if scope["type"] != "http":
                return await app(scope, receive, send)
            serial += 1
            number = serial
            method, path = scope["method"], scope["path"]
            body = bytearray()
            request_messages = []
            if method == "POST":
                while True:
                    message = await receive()
                    request_messages.append(message)
                    if message["type"] == "http.disconnect":
                        break
                    body.extend(message.get("body", b""))
                    if len(body) > 1024 * 1024:
                        raise RuntimeError("Unexpected oversized request; no product dispatch")
                    if not message.get("more_body", False):
                        break
            async def replay_receive():
                if request_messages:
                    return request_messages.pop(0)
                return await receive()
            read_posts = ({"/api/catalog/papers/query", "/api/catalog/discussion/context", "/api/catalog/discussion/history"}
                          if component == "catalog" else {"/api/research/discussion/context", "/api/research/discussion/history"})
            allowed = method in {"GET", "HEAD", "OPTIONS"} or (method == "POST" and path in read_posts)
            zero = None
            if component == "studio" and method == "POST":
                for ms, (_, target) in base.ZERO.items():
                    if path == f"/api/manuscripts/{ms}/stage":
                        try:
                            payload = json.loads(body)
                        except (ValueError, UnicodeDecodeError):
                            payload = None
                        if payload == {"stage": target, "expected_revision": 1, "reason": REASON}:
                            zero = ms
                            allowed = True
            # PNG endpoints may write caches beside historical absolute source
            # paths; excluded from this immutable readback, not silently allowed.
            if "/pages/" in path and path.endswith(".png"):
                allowed = False
            event = {"serial": number, "component": component, "role": role,
                "at_utc": datetime.now(timezone.utc).isoformat(), "method": method, "path": path,
                "query": scope.get("query_string", b"").decode("utf-8"), "allowed": allowed,
                "zero_version_manuscript": zero, "request_body_utf8": body.decode("utf-8") if body else None,
                "response_body_bytes": 0, "response_complete": False}
            response_hash = hashlib.sha256()
            error_body = bytearray()
            async def observed_send(message):
                if message["type"] == "http.response.start":
                    event["status"] = message["status"]
                await send(message)
                if message["type"] == "http.response.body":
                    data = message.get("body", b"")
                    response_hash.update(data)
                    event["response_body_bytes"] += len(data)
                    if zero:
                        assert len(error_body) + len(data) <= 65536, "Unexpected large refusal"
                        error_body.extend(data)
                    if not message.get("more_body", False):
                        event["response_complete"] = True
            try:
                if zero:
                    async with audit_lock:
                        assert base.snapshot(root / "data/catalog.db") == baseline
                        await app(scope, replay_receive, observed_send)  # Real product guard, never synthesized422.
                        assert event.get("status") == 422
                        response_json = json.loads(error_body)
                        assert "successful generated version" in response_json["detail"]
                        assert base.snapshot(root / "data/catalog.db") == baseline
                        assert base.filemap(root) == read(PREPARED / f"{role}-baseline-files.json")
                        event["actual_refusal_body"] = response_json
                        event["all110_and_files_exact_after_refusal"] = True
                elif allowed:
                    await app(scope, replay_receive, observed_send)
                else:
                    await JSONResponse({"detail": "G11 immutable readback: mutation/model/job/worker/cache write denied"}, status_code=403)(scope, replay_receive, observed_send)
            except BaseException as exc:
                event["exception_type"] = type(exc).__name__
                raise
            finally:
                event["response_body_sha256"] = response_hash.hexdigest()
                put(folder / f"{component}-http-{number:04d}.json", event)

    sock = socket.socket()
    sock.bind(("127.0.0.1", PORTS[component]))
    sock.listen(128)
    saved = identity(os.getpid())
    ready = {"identity": saved, "role": role, "component": component, "root": str(root),
        "port": PORTS[component], "all110_exact_on_startup": True, "lifespan": "off",
        "models_workers_started": 0, "stop_nonce": plan["nonce"]}
    put(folder / f"{component}-ready.json", ready)
    server = uvicorn.Server(uvicorn.Config(Boundary(), log_level="warning", lifespan="off"))
    done = threading.Event()
    def monitor():
        while not done.wait(0.15):
            stop_file = folder / "stop.request.json"
            if stop_file.exists() and read(stop_file).get("nonce") == plan["nonce"]:
                server.should_exit = True
                return
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        server.run(sockets=[sock])
    finally:
        done.set()
        watcher.join(timeout=2)
        app.state.discussions.shutdown()
        if component == "studio":
            app.state.studio._executor.shutdown(wait=True)
        sock.close()
        plan_guard(role, base, receipt)
        put(folder / f"{component}-terminal.json", {"status": "OWNED_ASGI_STOPPED_ALL110_AND_FILES_EXACT",
            "identity": saved, "role": role, "component": component, "port": PORTS[component],
            "stop_nonce": plan["nonce"], "all110_and_files_exact": True,
            "models_workers_jobs_approval_mutations": 0, "http_observations": serial})


def stop(role):
    base, receipt = load_base()
    plan = plan_guard(role, base, receipt)
    folder = HERE / role
    assert not (folder / "owned-stop-terminal.json").exists(), "Already stopped; do not replay"
    saved = {}
    launchers = {}
    for component in plan["components"]:
        launched = read(folder / f"{component}-launched.json")
        launchers[component] = launched["identity"]
        ready_file = folder / f"{component}-ready.json"
        assert ready_file.exists(), "Startup incomplete: inspect retained identity/log; no generic cleanup"
        saved[component] = read(ready_file)["identity"]
        if component != "frontend":
            ownership = read(folder / f"{component}-ownership.json")
            assert ownership == {"launcher": launchers[component], "serving": saved[component]}
        else:
            assert saved[component] == launchers[component]
    stop_file = folder / "stop.request.json"
    if stop_file.exists():
        assert read(stop_file)["nonce"] == plan["nonce"]
    else:
        put(stop_file, {"nonce": plan["nonce"], "role": role})
    for component in [name for name in plan["components"] if name != "frontend"]:
        terminal_file = folder / f"{component}-terminal.json"
        if absent(saved[component]):
            assert terminal_file.exists(), "Exited without terminal; preserve evidence and diagnose"
        else:
            process = exact(saved[component])
            if process is not None:
                try:
                    process.wait(timeout=35)
                except psutil.NoSuchProcess:
                    pass  # Simultaneous normal exit: require terminal and absence below.
        assert terminal_file.exists()
        terminal = read(terminal_file)
        assert terminal["identity"] == saved[component] and terminal["stop_nonce"] == plan["nonce"]
        assert terminal["all110_and_files_exact"] and absent(saved[component])
    if "frontend" in saved:
        frontend = saved["frontend"]
        if not absent(frontend):
            process = exact(frontend)
            if process is not None:
                consoles = read(folder / "frontend-ready.json")["owned_console_children"]
                descendants = [identity(p.pid) for p in process.children(recursive=True)]
                assert all(value in consoles for value in descendants), "Unexpected descendants; do not broadly stop"
                try:
                    process.terminate()
                    process.wait(timeout=20)
                except psutil.NoSuchProcess:
                    pass
        assert absent(frontend)
        for console in read(folder / "frontend-ready.json")["owned_console_children"]:
            if not absent(console):
                child = exact(console)
                try:
                    child.wait(timeout=10)
                except psutil.NoSuchProcess:
                    pass
            assert absent(console)
        front_guard(base)
        put(folder / "frontend-terminal.json", {"identity": frontend, "all_owned_identity_absent": True,
            "build_vectors93_77_exact": True, "explicit_owned_termination_or_prior_absence": True})
    plan_guard(role, base, receipt)
    for port in plan["ports"].values():
        port_free(port)
    assert all(absent(value) for value in saved.values())
    for value in launchers.values():
        if not absent(value):
            process = exact(value)
            try:
                process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
        assert absent(value)
    put(folder / "owned-stop-terminal.json", {"status": "EXACT_OWNED_ROLE_STOPPED_PORTS_FREE",
        "role": role, "identities": saved, "ports": plan["ports"], "all_owned_identities_absent": True,
        "all110_and_files_exact": True, "source421_and_originals_exact": True,
        "no_other_processes_stopped": True, "native_group_complete": False})
    print("EXACT_OWNED_" + role.upper() + "_STOPPED_PORTS_FREE_ALL110_EXACT", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["launch", "serve", "stop"])
    parser.add_argument("role", choices=ROLES)
    parser.add_argument("--component", choices=["catalog", "studio"], default="catalog")
    args = parser.parse_args()
    if args.mode == "serve":
        serve(args.role, args.component)
    else:
        {"launch": launch, "stop": stop}[args.mode](args.role)
