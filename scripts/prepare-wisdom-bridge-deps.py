#!/usr/bin/env python3
"""Add only the HTTP bridge dependencies after isolated KAG CPU preparation."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

REQUIREMENTS = ("fastapi==0.141.1", "uvicorn==0.52.4")


def run(command: list[str], log: Path, timeout: int, env: dict[str, str]) -> int:
    with log.open("w", encoding="utf-8") as output:
        child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                 env=env, start_new_session=True)
        try:
            return child.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=10)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=10)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", required=True, type=Path)
    parser.add_argument("--cpu-job", required=True, type=Path)
    parser.add_argument("--uuma-source", required=True, type=Path)
    parser.add_argument("--job", required=True, type=Path)
    args = parser.parse_args()
    venv = args.venv.resolve(strict=True)
    cpu_job = args.cpu_job.resolve(strict=True)
    source = args.uuma_source.resolve(strict=True)
    assert (venv / "pyvenv.cfg").is_file(), "Dedicated venv required"
    assert (source / "src/uuma/kag_bridge.py").is_file(), "Pinned bridge source required"
    args.job.mkdir(parents=True, exist_ok=True)
    job = args.job.resolve()
    # Share the original install lock: the CPU installer and this followup cannot race.
    with (cpu_job / "install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert json.loads((cpu_job / "status.json").read_text())["phase"] == (
            "READY_FOR_CPU_WIRING"
        ), "CPU preparation has not passed"
        return prepare(venv, cpu_job, source, job)


def prepare(venv: Path, cpu_job: Path, source: Path, job: Path) -> int:
    python = str(venv / "bin/python")
    attempt = job / f"attempt-{time.time_ns()}"
    attempt.mkdir()
    wheelhouse = cpu_job / "wheelhouse"
    assert wheelhouse.is_dir()
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "PIP_PROGRESS_BAR": "off",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "USE_TORCH": "0",
           "USE_TF": "0", "PYTHONPATH": str(source / "src")}
    pip = [python, "-m", "pip", "--disable-pip-version-check"]

    def status(phase: str, **details: object) -> None:
        value = {"phase": phase, "attempt": str(attempt), "pid": os.getpid(),
                 "no_model_inference": True, "updated_at": time.time(), **details}
        temporary = job / "status.tmp"
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(job / "status.json")

    try:
        status("LOCKING_EXISTING_DEPENDENCIES")
        package_file = attempt / "packages.before.json"
        if run(pip + ["list", "--format=json"], package_file, 60, env):
            status("FAILED_INVENTORY")
            return 1
        packages = json.loads(package_file.read_text())
        constraints = attempt / "constraints.txt"
        pins = []
        for package in packages:
            assert re.fullmatch(r"[A-Za-z0-9_.-]+", package["name"])
            assert re.fullmatch(r"[A-Za-z0-9_.+!-]+", package["version"])
            pins.append(f"{package['name']}=={package['version']}")
        constraints.write_text("\n".join(pins) + "\n", encoding="utf-8")
        status("DOWNLOADING_BRIDGE_DEPENDENCIES")
        command = pip + ["download", "--no-input", "--timeout", "30", "--retries", "1",
                         "--prefer-binary", "--dest", str(wheelhouse), "--find-links",
                         str(wheelhouse), "--constraint", str(constraints), *REQUIREMENTS]
        if run(command, attempt / "download.log", 600, env):
            status("FAILED_DOWNLOAD", retry_same_job=True)
            return 1
        status("INSTALLING_BRIDGE_DEPENDENCIES_OFFLINE")
        command = pip + ["install", "--no-input", "--no-index", "--no-build-isolation",
                         "--find-links", str(wheelhouse), "--constraint", str(constraints),
                         *REQUIREMENTS]
        if run(command, attempt / "install.log", 300, env):
            status("FAILED_INSTALL")
            return 1
        if run(pip + ["check"], attempt / "pip-check.log", 60, env):
            status("FAILED_DEPENDENCY_CHECK")
            return 1
        # Importing the real bridge creates no model session, listener or knowledge writer.
        code = """
import importlib.metadata as md
import json
import onnxruntime as ort
import uuma.kag_bridge as bridge
assert md.version('mcp') == '1.6.0'
assert md.version('openspg-kag') == '0.8.0'
assert md.version('fastapi') == '0.141.1'
assert md.version('uvicorn') == '0.52.4'
assert 'CPUExecutionProvider' in ort.get_available_providers()
packages = {d.metadata['Name']: d.version for d in md.distributions()}
assert not any(n.lower().replace('_', '-') in
               {'torch','torchvision','torchaudio','onnxruntime-gpu','triton'}
               or n.lower().startswith(('nvidia-','cuda-','cupy')) for n in packages)
assert bridge._initialized is False
assert bridge._bge_runtime['backend'] == 'unconfigured'
print(json.dumps({'packages': packages, 'providers': ort.get_available_providers(),
                  'bridge_source': bridge.__file__, 'no_model_inference': True}, indent=2))
"""
        if run([python, "-c", code], attempt / "import-verification.json", 120, env):
            status("FAILED_BRIDGE_IMPORT")
            return 1
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(wheelhouse.iterdir()) if path.is_file()}
        (attempt / "artifact-sha256.json").write_text(json.dumps(hashes, indent=2))
        status("READY_FOR_BRIDGE_CONFIGURATION", artifacts=len(hashes))
        return 0
    except BaseException as error:
        status("FAILED_TIMEOUT" if isinstance(error, subprocess.TimeoutExpired)
               else "FAILED_EXCEPTION", error_type=type(error).__name__)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
