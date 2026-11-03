"""Install, launch, inspect or restore the desktop gateway pilot without UI automation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from urllib.request import urlopen

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent.parent
STATE = ROOT / ".uuma-local/codex-antigravity-ui-20261102"
CONFIG = Path.home() / ".codex/config.toml"
PROVIDER = "uuma-antigravity"
BEGIN = "# BEGIN UUMA ANTIGRAVITY PILOT"
END = "# END UUMA ANTIGRAVITY PILOT"


def settings():
    return json.loads((STATE / "settings.json").read_text(encoding="utf-8"))


def status():
    with urlopen(f"http://127.0.0.1:{settings()['port']}/health", timeout=3) as response:
        return json.load(response)


def start():
    try:
        existing = status()
    except OSError:
        existing = None
    if existing is not None:
        if existing.get("service") != "codex-antigravity":
            raise RuntimeError("Another service owns the selected port")
        print(json.dumps(existing))
        return
    python = (
        Path(sys.executable).with_name("pythonw.exe") if os.name == "nt" else Path(sys.executable)
    )
    env = {**os.environ, "CODEX_AGY_STATE": str(STATE)}
    flags = (
        (
            subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        )
        if os.name == "nt"
        else 0
    )
    with (
        (STATE / "gateway.stdout.log").open("ab") as output,
        (STATE / "gateway.stderr.log").open("ab") as error,
    ):
        process = subprocess.Popen(
            [str(python), str(SOURCE / "gateway.py")],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=error,
            creationflags=flags,
            close_fds=True,
        )
    receipt = {
        "pid": process.pid,
        "executable": str(python),
        "source": str(SOURCE / "gateway.py"),
        "source_sha256": hashlib.sha256((SOURCE / "gateway.py").read_bytes()).hexdigest(),
        "started_at": int(time.time()),
    }
    (STATE / "gateway-process.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    for _ in range(30):
        if process.poll() is not None:
            raise RuntimeError("Gateway exited; inspect the private stderr log")
        try:
            ready = status()
            receipt["runtime_pid"] = ready.get("pid", process.pid)
            (STATE / "gateway-process.json").write_text(
                json.dumps(receipt, indent=2), encoding="utf-8"
            )
            print(json.dumps(ready))
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Gateway startup is pending; inspect the recorded PID before retrying")


def stop():
    current = status()
    if current.get("service") != "codex-antigravity" or current.get("active"):
        raise RuntimeError("Gateway has active requests or a different service owns the port")
    receipt = json.loads((STATE / "gateway-process.json").read_text(encoding="utf-8"))
    runtime_pid = current.get("pid", receipt.get("runtime_pid"))
    if os.name == "nt":
        # Windows venv pythonw.exe is a launcher. Its PID and executable differ
        # from the Python process that actually owns the listening socket.
        if runtime_pid is None:
            prefix = (
                f"$owner = (Get-NetTCPConnection -LocalAddress 127.0.0.1 "
                f"-LocalPort {int(settings()['port'])} -State Listen).OwningProcess; "
            )
            selector = "('ProcessId = ' + $owner)"
        else:
            prefix = ""
            selector = f"'ProcessId = {int(runtime_pid)}'"
        command = (
            prefix + f"Get-CimInstance Win32_Process -Filter {selector} | "
            "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=True,
        )
        process = json.loads(result.stdout)
        expected = {
            Path(receipt["executable"]).resolve(),
            (Path(sys.base_prefix) / "pythonw.exe").resolve(),
        }
        if (
            Path(process["ExecutablePath"]).resolve() not in expected
            or receipt["source"] not in process["CommandLine"]
        ):
            raise RuntimeError("Recorded PID no longer belongs to this gateway")
        runtime_pid = int(process["ProcessId"])
    else:
        runtime_pid = runtime_pid or receipt["pid"]
        command = Path(f"/proc/{runtime_pid}/cmdline").read_bytes().decode()
        if receipt["source"] not in command:
            raise RuntimeError("Recorded PID no longer belongs to this gateway")
    os.kill(runtime_pid, signal.SIGTERM)
    print("Stopped the isolated Antigravity gateway")


def install():
    # Import only the local catalog builder; no inference or provider initialization.
    os.environ["CODEX_AGY_STATE"] = str(STATE)
    spec = importlib.util.spec_from_file_location("_codex_agy_gateway", SOURCE / "gateway.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    catalog = STATE / "models.json"
    catalog.write_text(json.dumps(module.catalog(), indent=2, ensure_ascii=True), encoding="utf-8")
    original = CONFIG.read_bytes()
    text = original.decode("utf-8")
    parsed = tomllib.loads(text)
    backup = STATE / "config.before.toml"
    previous = STATE / "previous-routing.json"
    if BEGIN not in text:
        if PROVIDER in parsed.get("model_providers", {}):
            raise RuntimeError("Provider ID already exists outside this pilot")
        if backup.exists():
            raise RuntimeError("A previous backup exists; inspect it before reinstalling")
        backup.write_bytes(original)
        previous.write_text(
            json.dumps(
                {k: parsed.get(k) for k in ("model_provider", "model_catalog_json")}, indent=2
            ),
            encoding="utf-8",
        )
    else:
        raise RuntimeError("Pilot is already installed; use start or status")
    top, separator, tables = text.partition("\n[")
    top = re.sub(r"(?m)^(model_provider|model_catalog_json)\s*=.*\r?\n?", "", top)
    changes = (
        f'{BEGIN}\nmodel_provider = "{PROVIDER}"\n'
        f"model_catalog_json = {json.dumps(str(catalog))}\n{END}\n"
    )
    content = changes + top + (separator + tables if separator else "")
    provider = (
        f"\n{BEGIN}\n[model_providers.{PROVIDER}]\n"
        'name = "OpenAI + Antigravity"\n'
        f'base_url = "http://127.0.0.1:{settings()["port"]}/v1"\n'
        'wire_api = "responses"\nrequires_openai_auth = true\n'
        "supports_websockets = false\nrequest_max_retries = 0\n"
        "stream_max_retries = 0\nstream_idle_timeout_ms = 360000\n"
        f"{END}\n"
    )
    content += provider
    tomllib.loads(content)
    if CONFIG.read_bytes() != original:
        raise RuntimeError("Configuration changed during preparation; no overwrite performed")
    CONFIG.write_text(content, encoding="utf-8", newline="\n")
    receipt = {
        "config": str(CONFIG),
        "backup": str(backup),
        "catalog": str(catalog),
        "before_sha256": hashlib.sha256(original).hexdigest(),
        "after_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "installed_at": int(time.time()),
    }
    (STATE / "installation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt))


def restore():
    current = CONFIG.read_bytes()
    text = current.decode("utf-8")
    if BEGIN not in text:
        print("Pilot routing is not installed")
        return
    previous = json.loads((STATE / "previous-routing.json").read_text(encoding="utf-8"))
    blocks = re.compile(re.escape(BEGIN) + r"\r?\n.*?" + re.escape(END) + r"\r?\n?", re.DOTALL)
    restored = blocks.sub("", text)
    additions = "".join(
        f"{key} = {json.dumps(value)}\n" for key, value in previous.items() if value is not None
    )
    restored = additions + restored
    tomllib.loads(restored)
    if CONFIG.read_bytes() != current:
        raise RuntimeError("Configuration changed during restore; retry after review")
    (STATE / f"config.before-restore-{int(time.time())}.toml").write_bytes(current)
    CONFIG.write_text(restored, encoding="utf-8", newline="\n")
    shortcut = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft/Windows/Start Menu/Programs"
        / "Startup/UuMA Antigravity Gateway.lnk"
    )
    if shortcut.is_file():
        shortcut.unlink()
    print("Previous routing restored; unrelated settings preserved. Restart the desktop app.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "start", "stop", "status", "restore"])
    args = parser.parse_args()
    if args.action == "status":
        print(json.dumps(status(), indent=2))
    else:
        globals()[args.action]()
