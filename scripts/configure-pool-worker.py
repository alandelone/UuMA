"""Bind a server profile's existing bounded worker to a reviewed account pool.

SOUL, worker MCP operation name, caller identity, and task packet remain unchanged.
This is an explicit manual deployment step; it does not start or restart services.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

import yaml


def bind(profile: Path, template: Path, source: Path, wrapper: Path,
         pool_root: Path, workspace_root: Path, receipt_root: Path) -> dict:
    for path in (profile, template, source, pool_root, workspace_root):
        if not path.is_dir():
            raise ValueError(f"Required deployment directory is unavailable: {path}")
    if not wrapper.is_absolute() or not wrapper.is_file():
        raise ValueError("A fixed pool wrapper is required")
    if not (pool_root / "pool.json").is_file():
        raise ValueError("Use the existing initialized server pool")
    if not (source / "uuma/gemini_worker.py").is_file():
        raise ValueError("Worker source is not a complete UuMA candidate")
    path = profile / "config.yaml"
    before = path.read_bytes()
    original = yaml.safe_load(before)
    baseline = yaml.safe_load((template / "config.yaml").read_text(encoding="utf-8"))
    worker = copy.deepcopy(baseline["mcp_servers"]["gemini-worker"])
    identity = worker["env"].get("UUMA_AGENT_ID")
    if identity != profile.name:
        raise ValueError("Worker template identity does not match its profile")
    if worker["env"].get("GEMINI_WORKER_APPROVAL_MODE") != "plan":
        raise ValueError("A mode change requires a separate reviewed contract")
    executable = Path(worker["command"])
    if not executable.is_absolute() or not executable.is_file():
        raise ValueError("Worker Python must be a fixed server executable")
    wrapper_hash = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    worker["env"].update({
        "PYTHONPATH": str(source), "GEMINI_WORKER_BACKEND": "account_pool",
        "GEMINI_WORKER_EXECUTABLE": str(wrapper), "UUMA_AGY_POOL_ROOT": str(pool_root),
        "GEMINI_WORKER_WRAPPER_SHA256": wrapper_hash,
        "GEMINI_WORKER_ALLOWED_ROOTS": str(workspace_root),
        "GEMINI_WORKER_LOG_DIR": str(receipt_root),
        "GEMINI_WORKER_MODEL": "gemini-3.8-flash-medium",
        "GEMINI_WORKER_REASONING_EFFORT": "medium",
    })
    config = copy.deepcopy(original)
    config.setdefault("mcp_servers", {})["gemini-worker"] = worker
    output = yaml.safe_dump(config, allow_unicode=True).encode("utf-8")
    receipt = {
        "schema_version": 1, "agent_id": identity, "backend": "account_pool",
        "approval_mode": "plan", "wrapper_sha256": wrapper_hash,
        "source": str(source), "workspace_root": str(workspace_root),
        "before_config_sha256": hashlib.sha256(before).hexdigest(),
        "after_config_sha256": hashlib.sha256(output).hexdigest(),
        "services_restarted": False, "new_login_required": False,
    }
    backup = profile / ("config.before-pool-worker-" + receipt["before_config_sha256"][:12] + ".yaml")
    if backup.exists() and backup.read_bytes() != before:
        raise ValueError("Existing profile backup does not match the expected bytes")
    if not backup.exists():
        with backup.open("xb") as stream:
            stream.write(before)
    temporary = path.with_suffix(".pool-worker.tmp")
    with temporary.open("xb") as stream:
        stream.write(output)
    temporary.replace(path)
    (profile / "pool-worker-binding.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "template", "source", "wrapper", "pool-root",
                 "workspace-root", "receipt-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("Bind only a server candidate; workstation profiles retain their backend")
    os.umask(0o077)
    print(json.dumps(bind(**vars(args))))
