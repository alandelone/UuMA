#!/usr/bin/env python3
"""Prepare an isolated KAG CPU candidate; never start services or run inference.

Downloads are resumable in a persistent wheelhouse. Each pip process has a finite
deadline and its entire process group is reaped on timeout. Re-run the same job
directory to reuse completed artifacts, while retaining every attempt's logs.
"""

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CPU_REQUIREMENTS = (
    "onnxruntime==1.23.2",
    "transformers==4.52.4",
    "tokenizers==0.21.4",
    "sentencepiece==0.2.2",
    "numpy==2.4.6",
)


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def blocked(name: str) -> bool:
    name = normalized(name)
    return name.startswith(("nvidia-", "cuda-", "cupy")) or name in {
        "torch", "torchvision", "torchaudio", "onnxruntime-gpu", "triton"
    }


def execute(command: list[str], log: Path, timeout: int, env: dict[str, str]) -> int:
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            command, stdout=output, stderr=subprocess.STDOUT,
            env=env, start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--venv", required=True, type=Path)
    parser.add_argument("--constraints", required=True, type=Path)
    parser.add_argument("--job", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    venv = args.venv.resolve(strict=True)
    job = args.job.resolve()
    job.mkdir(parents=True, exist_ok=True)
    # A second invocation must not race pip installation in the same candidate.
    with (job / "install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return prepare(source, venv, args.constraints.resolve(strict=True), job)


def prepare(source: Path, venv: Path, constraints: Path, job: Path) -> int:
    python = str(venv / "bin/python")
    assert (source / "KAG_VERSION").read_text().strip() == "0.8.0"
    assert (venv / "pyvenv.cfg").is_file(), "A dedicated candidate venv is required"
    assert not any(venv.glob("lib/python*/site-packages/torch")), "GPU environment rejected"
    attempt = job / f"attempt-{time.time_ns()}"
    attempt.mkdir()
    wheelhouse = job / "wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    state = {"pid": os.getpid(), "attempt": str(attempt), "no_model_inference": True}

    def status(phase: str, **details: object) -> None:
        value = {**state, "phase": phase, "updated_at": time.time(), **details}
        temporary = job / "status.tmp"
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(job / "status.json")

    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "PIP_PROGRESS_BAR": "off",
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "USE_TORCH": "0", "USE_TF": "0", "PYTHONUNBUFFERED": "1"}
    pip = [python, "-m", "pip", "--disable-pip-version-check"]
    network = ["--no-input", "--timeout", "30", "--retries", "1"]
    roots = [line.strip() for line in (source / "requirements.txt").read_text().splitlines()
             if line.strip() and not line.strip().startswith("#")]
    roots.extend(CPU_REQUIREMENTS)
    # Build tools are recorded in the resolved manifest, not inherited from the host.
    roots.extend(["setuptools>=68", "wheel"])
    for requirement in roots:
        name = re.match(r"[A-Za-z0-9_.-]+", requirement)
        assert name and not blocked(name.group()), f"GPU dependency rejected: {requirement}"
    requirement_file = job / "requirements.cpu.txt"
    requirement_file.write_text("\n".join(roots) + "\n", encoding="utf-8")
    try:
        status("DOWNLOADING_ROOT_ARTIFACTS")

        def download(item: tuple[int, str]) -> dict[str, object]:
            index, requirement = item
            command = pip + ["download", *network, "--no-deps", "--prefer-binary",
                             "--dest", str(wheelhouse), "--find-links", str(wheelhouse),
                             "--constraint", str(constraints), requirement]
            try:
                code = execute(command, attempt / f"root-{index:03d}.log", 300, env)
                return {"requirement": requirement, "exit_code": code}
            except subprocess.TimeoutExpired:
                return {"requirement": requirement, "timed_out": True}

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(download, enumerate(roots)))
        (attempt / "root-results.json").write_text(json.dumps(results, indent=2))
        if any(item.get("exit_code") != 0 for item in results):
            status("ROOT_DOWNLOAD_INCOMPLETE", retry_same_job=True)
            return 1
        status("RESOLVING_DEPENDENCY_CLOSURE")
        command = pip + ["download", *network, "--prefer-binary", "--dest", str(wheelhouse),
                         "--find-links", str(wheelhouse), "--constraint", str(constraints),
                         "--requirement", str(requirement_file)]
        if execute(command, attempt / "resolve.log", 1200, env):
            status("DEPENDENCY_DOWNLOAD_INCOMPLETE", retry_same_job=True)
            return 1
        # Artifact names cannot prove compatibility, but reject forbidden packages
        # before any installation. pip check and real imports run afterwards.
        for artifact in wheelhouse.iterdir():
            package_name = artifact.name.split("-")[0]
            assert not blocked(package_name), f"GPU artifact rejected: {artifact.name}"
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(wheelhouse.iterdir()) if path.is_file()}
        (attempt / "artifact-sha256.json").write_text(json.dumps(hashes, indent=2))
        status("INSTALLING_OFFLINE")
        offline = ["--no-input", "--no-index", "--find-links", str(wheelhouse)]
        if execute(pip + ["install", *offline, "setuptools>=68", "wheel"],
                   attempt / "build-tools.log", 120, env):
            status("FAILED_BUILD_TOOLS")
            return 1
        command = pip + ["install", *offline, "--no-build-isolation", "--constraint",
                         str(constraints), "--requirement", str(requirement_file), str(source)]
        if execute(command, attempt / "install.log", 600, env):
            status("FAILED_INSTALL")
            return 1
        status("VERIFYING_IMPORTS")
        if execute(pip + ["check"], attempt / "pip-check.log", 90, env):
            status("FAILED_DEPENDENCY_CHECK")
            return 1
        verification = """
import importlib.metadata as md
import json
import onnxruntime as ort
from transformers import AutoTokenizer
import kag
import knext
from kag.common.vectorize_model.local_bge_model import LocalBGEM3VectorizeModel
from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
from kag.builder.component.writer.kg_writer import KGWriter
packages = {d.metadata['Name']: d.version for d in md.distributions()}
assert md.version('openspg-kag') == '0.8.0'
assert md.version('onnxruntime') == '1.23.2'
assert md.version('transformers') == '4.52.4'
assert md.version('tokenizers') == '0.21.4'
assert md.version('numpy') == '2.4.6'
assert md.version('sentencepiece') == '0.2.2'
assert 'CPUExecutionProvider' in ort.get_available_providers()
assert not any(n.lower().replace('_','-') in
               {'torch','torchvision','torchaudio','onnxruntime-gpu','triton'}
               or n.lower().startswith(('nvidia-','cuda-','cupy')) for n in packages)
print(json.dumps({'providers': ort.get_available_providers(), 'packages': packages,
                  'no_model_inference': True}, indent=2))
"""
        # KAG's generated schema classes construct REST Configuration on import.
        # Give that constructor explicit metadata rather than searching the SSH
        # working directory for a production config. Port 1 is intentionally not
        # the shared OpenSPG or a model endpoint; this probe must only import.
        verification_env = {
            **env, "KAG_PROJECT_HOST_ADDR": "http://127.0.0.1:1", "KAG_PROJECT_ID": "1"
        }
        if execute([python, "-c", verification], attempt / "import-verification.json",
                   120, verification_env):
            status("FAILED_IMPORT")
            return 1
        status("READY_FOR_CPU_WIRING", cpu_provider=True, artifacts=len(hashes))
        return 0
    except BaseException as error:
        status("FAILED_TIMEOUT" if isinstance(error, subprocess.TimeoutExpired)
               else "FAILED_EXCEPTION", error_type=type(error).__name__, retry_same_job=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
