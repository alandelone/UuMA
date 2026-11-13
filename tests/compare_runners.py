import os
import sys
import json
import time
import subprocess
from pathlib import Path

def test_dev():
    env = {
        **os.environ,
        "RSTV4_ROOT": r"C:\Users\Alandelone\CodeSpace_Local\RSTV4",
        "RSTV4_CATALOG_GLOBAL_TOOLS": "1",
        "PYTHONPATH": r"C:\Users\Alandelone\CodeSpace_Local\RSTV4\src",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "rstv4.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=env,
    )
    # Handshake
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}) + "\n")
    proc.stdin.flush()
    proc.stdout.readline()
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

def test_runner():
    cmd = [
        str(sys.executable),
        r"C:\Users\Alandelone\CodeSpace_Local\UuMA\scripts\run-scholar-catalog-mcp.py",
        "--project-root", r"C:\Users\Alandelone\CodeSpace_Local\UuMA",
        "--data-root", r"C:\Users\Alandelone\CodeSpace_Local\RSTV4",
        "--manifest", r"C:\Users\Alandelone\CodeSpace_Local\UuMA\.uuma-local\scholar-catalog-runtime\active-release.json",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    # Handshake
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}) + "\n")
    proc.stdin.flush()
    proc.stdout.readline()
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    for i in range(2):
        t0 = time.perf_counter()
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2 + i, "method": "tools/call", "params": {"name": "get_catalog_theme_candidates", "arguments": {"query_json": json.dumps({"limit": 2})}}}) + "\n")
        proc.stdin.flush()
        resp = json.loads(proc.stdout.readline())
        t_run = time.perf_counter() - t0
        print(f"Runner run-scholar-catalog-mcp.py call {i+1} latency: {t_run:.3f}s")
    proc.terminate()
    proc.wait()

test_dev()
test_runner()
