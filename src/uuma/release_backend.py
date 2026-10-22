"""Operator-owned OS hooks for explicit manual release application.

Hook argv is sealed into the preview. No hook is supplied by an Agent request or
executed through a shell. Hooks must implement actual runtime draining and report
running versions; a source checkout alone is never considered a healthy runtime.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from .control_client import ControlClient
from .node_journal import digest
from .release import atomic_json


class CommandReleaseBackend:
    def __init__(self, root: Path, deployment: dict, *, control=None, runner=None):
        self.root, self.deployment = root.resolve(), deployment
        if deployment.get("schema_version") != 1:
            raise ValueError("Unsupported OS deployment configuration")
        if deployment.get("node") not in {"server", "workstation"}:
            raise ValueError("Unknown deployment node")
        self.directory = Path(deployment["release_root"]).expanduser().resolve()
        if self.directory == self.root or self.directory in self.root.parents:
            raise ValueError("Release directories must not contain the development checkout")
        for key in deployment.get("components", {}):
            if not re.fullmatch(r"[a-z][a-z0-9-]*", key):
                raise ValueError("Invalid component identifier")
        self.control = control
        self.runner = runner or subprocess.run
        self.snapshots = {}

    def bind(self, plan: dict, selected: list[str]):
        if plan.get("deployment_digest") != digest(self.deployment):
            raise ValueError("OS configuration changed; generate a new preview")
        self.plan, self.selected = plan, selected
        components = self.deployment["components"]
        if any(name not in components for name in selected):
            raise ValueError("Every affected component requires an explicit OS mapping")
        self.agents = sorted({a for name in selected for a in components[name]["agents"]})
        self.services = sorted({s for name in selected for s in components[name]["services"]})
        if not self.agents or not self.services:
            raise ValueError("A release requires governed Agents and runtime maintenance hooks")
        for service in self.services:
            definition = self.deployment["services"][service]
            for phase in ["pause", "snapshot", "activate", "verify", "resume"]:
                argv = definition.get(phase)
                if not isinstance(argv, list) or not argv or not all(
                    isinstance(arg, str) and arg for arg in argv
                ):
                    raise ValueError(f"Service {service} requires a fixed {phase} argv")
        if self.control is None:
            self.control = ControlClient.from_env()
        if getattr(self.control, "identity", "orchestrator") != "orchestrator":
            raise PermissionError("Manual deployment requires the control identity")

    def hook(self, service: str, phase: str) -> dict:
        context = {
            "plan_id": self.plan["plan_id"], "revision": self.plan["target_revision"],
            "release_root": str(self.directory),
            "source": str(self.directory / "sources" / self.plan["target_revision"]),
            "components": self.selected, "agents": self.agents,
            "fingerprints": {
                name: self.plan["components"][name]["fingerprint"] for name in self.selected
            },
        }
        result = self.runner(
            self.deployment["services"][service][phase],
            env={**os.environ, "UUMA_DEPLOYMENT_CONTEXT": json.dumps(context)},
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60,
            shell=False,
        )
        if result.returncode:
            # Hook output may contain credentials; keep it out of public exceptions.
            raise RuntimeError(f"Runtime maintenance hook failed: {service}/{phase}")
        try:
            payload = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"Runtime hook returned invalid evidence: {service}/{phase}") from exc
        if not isinstance(payload, dict) or payload.get("plan_id") != self.plan["plan_id"]:
            raise RuntimeError("Runtime evidence belongs to another release")
        return payload

    def pause_intake(self, _selected):
        self.control.request("POST", "/control/deployment/intake", {
            "agents": self.agents, "plan_id": self.plan["plan_id"], "paused": True,
        })
        for service in self.services:
            if self.hook(service, "pause").get("intake_paused") is not True:
                raise RuntimeError("Runtime did not confirm closing admission")

    def active_work(self, _selected):
        active = []
        for agent in self.agents:
            for run in self.control.list_runs(agent_id=agent):
                if run["status"] in {"PENDING", "RUNNING", "BLOCKED", "CANCEL_REQUESTED"}:
                    active.append({"agent_id": agent, "run_id": run["run_id"]})
        for service in self.services:
            snapshot = self.hook(service, "snapshot")
            if (
                snapshot.get("intake_paused") is not True
                or not isinstance(snapshot.get("active"), list)
                or not isinstance(snapshot.get("paused"), list)
            ):
                raise RuntimeError("Runtime did not provide a complete drain snapshot")
            self.snapshots[service] = snapshot
            active.extend(snapshot["active"])
        return active

    def check_paused_compatibility(self, _component, _revision):
        for service, snapshot in self.snapshots.items():
            for paused in snapshot["paused"]:
                environment = Path(paused.get("environment", ""))
                if (
                    not paused.get("resume_ref") or paused.get("retained") is not True
                    or not environment.is_absolute() or not environment.is_dir()
                ):
                    raise RuntimeError(f"Paused execution environment is not retained: {service}")
        for agent in self.agents:
            for run in self.control.list_runs(agent_id=agent, status="PAUSED"):
                if not any(
                    item.get("run_id") == run["run_id"]
                    for snapshot in self.snapshots.values() for item in snapshot["paused"]
                ):
                    raise RuntimeError("A paused governed Run has no retained runtime environment")

    def prepare(self, plan, _selected):
        source = self.directory / "sources" / plan["target_revision"]
        marker = source / "release-source.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        if source.exists():
            raise RuntimeError("Existing source candidate must be reconciled before another apply")
        source.mkdir(parents=True)
        archive = subprocess.check_output([
            "git", "-C", str(self.root), "archive", "--format=tar", plan["target_revision"],
        ])
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            for member in bundle.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts or "\\" in member.name:
                    raise ValueError("Release archive contains an unsafe path")
                target = (source / member.name).resolve()
                if not target.is_relative_to(source.resolve()):
                    raise ValueError("Release archive leaves its version directory")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.extractfile(member) as incoming, target.open("xb") as outgoing:
                        outgoing.write(incoming.read())
                    if os.name != "nt":
                        target.chmod(member.mode & 0o755)
                else:
                    raise ValueError("Release archive may not contain symlinks or special files")
        atomic_json(marker, {"revision": plan["target_revision"], "plan_id": plan["plan_id"]})
        return {"source": str(source), "previous_environments_retained": True}

    def activate(self, plan, selected, prepared):
        for name in selected:
            if plan["components"][name]["status"] != "UPDATE":
                continue
            atomic_json(self.directory / "current" / (name + ".json"), {
                "revision": plan["target_revision"], "source": prepared["source"],
                "fingerprint": plan["components"][name]["fingerprint"],
                "plan_id": plan["plan_id"],
            })
        for service in self.services:
            self.hook(service, "activate")

    def verify(self, plan, _selected):
        verified = set()
        for service in self.services:
            evidence = self.hook(service, "verify")
            if evidence.get("healthy") is not True:
                raise RuntimeError(f"Updated runtime is not healthy: {service}")
            for name, version in evidence.get("components", {}).items():
                if name not in self.selected:
                    continue
                if (
                    version.get("revision") != (
                        plan["target_revision"] if plan["components"][name]["status"] == "UPDATE"
                        else plan["components"][name]["actual_revision"]
                    )
                    or version.get("fingerprint") != plan["components"][name]["fingerprint"]
                ):
                    raise RuntimeError(f"Runtime reports an unexpected version: {name}")
                verified.add(name)
        if verified != set(self.selected):
            raise RuntimeError("Some affected components did not report their running version")

    def resume_intake(self, _selected):
        for service in self.services:
            if self.hook(service, "resume").get("intake_paused") is not False:
                raise RuntimeError("Runtime admission restoration is not confirmed")
        self.control.request("POST", "/control/deployment/intake", {
            "agents": self.agents, "plan_id": self.plan["plan_id"], "paused": False,
        })
