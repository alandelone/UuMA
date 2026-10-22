"""Manual, immutable release previews with component and dependency fingerprints."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .node_journal import digest


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        __import__("os").fsync(handle.fileno())
    temporary.replace(path)


def preview(
    root: Path, revision: str, actual: dict, *, manifest_path="deploy/components.json",
    deployment: dict | None = None,
) -> dict:
    revision = git(root, "rev-parse", "--verify", revision + "^{commit}")
    manifest = json.loads(git(root, "show", f"{revision}:{manifest_path}"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported component manifest")
    components = manifest["components"]
    tree = {}
    for line in git(root, "ls-tree", "-rz", revision).split("\0"):
        if not line:
            continue
        metadata, path = line.split("\t", 1)
        tree[path] = metadata.split()[2]
    fingerprints = {}
    visiting = set()

    def fingerprint(name):
        if name in fingerprints:
            return fingerprints[name]
        if name in visiting:
            raise ValueError("Component dependencies contain a cycle")
        visiting.add(name)
        component = components[name]
        if any(
            engine not in manifest.get("engine_versions", {})
            for engine in component.get("engines", [])
        ):
            raise ValueError(f"Component {name} has an unpinned external engine")
        files = {
            path: blob
            for path, blob in tree.items()
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in component["paths"])
        }
        if not files:
            raise ValueError(f"Component {name} matches no versioned inputs")
        dependencies = {dep: fingerprint(dep) for dep in component.get("depends_on", [])}
        fingerprints[name] = digest(
            {
                "files": files,
                "dependencies": dependencies,
                "definition": component,
                "engine_versions": {
                    engine: manifest.get("engine_versions", {}).get(engine)
                    for engine in component.get("engines", [])
                },
            }
        )
        visiting.remove(name)
        return fingerprints[name]

    entries = {}
    for name, component in components.items():
        current = actual.get("components", {}).get(name, {})
        target_digest = fingerprint(name)
        entries[name] = {
            "node": component["node"],
            "fingerprint": target_digest,
            "actual_revision": current.get("revision"),
            "status": (
                "INPUT"
                if component["node"] == "dependency"
                else "CURRENT"
                if current.get("fingerprint") == target_digest
                else "UPDATE"
            ),
            "depends_on": component.get("depends_on", []),
            "restart_group": component.get("restart_group"),
        }
    groups = {
        entry["restart_group"]
        for entry in entries.values()
        if entry["status"] == "UPDATE" and entry["restart_group"]
    }
    affected = sorted(
        {
            name
            for name, entry in entries.items()
            if entry["status"] == "UPDATE" or entry["restart_group"] in groups
        }
    )
    affected = sorted(
        set(affected).union(
            *(set(manifest.get("gateway_members", {}).get(group, [])) for group in groups)
        )
    )
    plan = {
        "schema_version": 1,
        "target_revision": revision,
        "components": entries,
        "affected_components": affected,
        "actual_digest": digest(actual),
        "manifest_path": manifest_path,
        "engine_versions": manifest.get("engine_versions", {}),
    }
    if deployment is not None:
        plan["deployment_digest"] = digest(deployment)
        mappings = deployment.get("components", {})
        local = [name for name in affected if entries[name]["node"] == deployment.get("node")]
        if any(name not in mappings for name in local):
            raise ValueError("Every affected component requires an explicit OS mapping")
        plan["deployment_impact"] = {
            "node": deployment.get("node"),
            "agents": sorted({a for name in local for a in mappings[name].get("agents", [])}),
            "services": sorted({s for name in local for s in mappings[name].get("services", [])}),
        }
    return {**plan, "plan_id": digest(plan)}


def validate_preview(root: Path, plan: dict, actual: dict, *, deployment=None) -> None:
    expected = preview(
        root, plan["target_revision"], actual, manifest_path=plan["manifest_path"],
        deployment=deployment,
    )
    if expected != plan:
        raise ValueError("Preview is stale or changed; generate a new preview")


class ReleaseManager:
    """Activation hooks are trusted operator adapters, never Agent-supplied shell commands."""

    def __init__(self, root: Path, state: Path, backend):
        self.root, self.state, self.backend = root, state, backend

    def apply(self, plan: dict, node: str) -> dict:
        self.state.parent.mkdir(parents=True, exist_ok=True)
        lock = self.state.parent / ".release-apply.lock"
        try:
            with lock.open("x", encoding="utf-8") as handle:
                json.dump({"plan_id": plan["plan_id"], "node": node}, handle)
        except FileExistsError as exc:
            raise RuntimeError(
                "Another activation or interrupted release requires reconciliation"
            ) from exc
        try:
            return self._apply(plan, node)
        finally:
            lock.unlink()

    def _apply(self, plan: dict, node: str) -> dict:
        actual = (
            json.loads(self.state.read_text(encoding="utf-8"))
            if self.state.exists() else {"components": {}}
        )
        validate_preview(
            self.root, plan, actual,
            deployment=getattr(self.backend, "deployment", None),
        )
        selected = [
            name for name in plan["affected_components"] if plan["components"][name]["node"] == node
        ]
        if not selected:
            return {"status": "NO_CHANGE", "plan_id": plan["plan_id"]}
        if hasattr(self.backend, "bind"):
            self.backend.bind(plan, selected)
        # Backend must atomically close admission and report both governed Runs and runtime work.
        self.backend.pause_intake(selected)
        if self.backend.active_work(selected):
            return {
                "status": "WAITING_FOR_TASKS",
                "components": selected,
                "plan_id": plan["plan_id"],
            }
        for name in selected:
            self.backend.check_paused_compatibility(name, plan["target_revision"])
        prepared = self.backend.prepare(plan, selected)
        previous = {name: actual.get("components", {}).get(name) for name in selected}
        # Persist intent before switching; an interrupted activation remains explicitly uncertain.
        receipt_path = self.state.parent / "receipts" / (plan["plan_id"] + f"-{node}.json")
        receipt = {
            "status": "ACTIVATING",
            "plan_id": plan["plan_id"],
            "components": selected,
            "previous": previous,
            "prepared": prepared,
        }
        if receipt_path.exists():
            raise RuntimeError(
                "Existing activation receipt must be reconciled before another apply"
            )
        atomic_json(receipt_path, receipt)
        try:
            self.backend.activate(plan, selected, prepared)
            self.backend.verify(plan, selected)
        except BaseException:
            atomic_json(receipt_path, {**receipt, "status": "RECONCILIATION_REQUIRED"})
            raise
        for name in selected:
            if plan["components"][name]["status"] == "UPDATE":
                actual.setdefault("components", {})[name] = {
                    "revision": plan["target_revision"],
                    "fingerprint": plan["components"][name]["fingerprint"],
                }
        try:
            atomic_json(self.state, actual)
            # Keep the persisted receipt uncertain until admission has also been restored.
            self.backend.resume_intake(selected)
            receipt = {
                **receipt, "status": "VERIFIED", "completed_at": datetime.now(UTC).isoformat()
            }
            atomic_json(receipt_path, receipt)
        except BaseException:
            atomic_json(receipt_path, {**receipt, "status": "RECONCILIATION_REQUIRED"})
            raise
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("preview")
    command.add_argument("--root", type=Path, default=Path.cwd())
    command.add_argument("--target", required=True)
    command.add_argument("--actual", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--deployment", type=Path)
    command = sub.add_parser("apply")
    command.add_argument("--root", type=Path, default=Path.cwd())
    command.add_argument("--plan", type=Path, required=True)
    command.add_argument("--actual", type=Path, required=True)
    command.add_argument("--deployment", type=Path, required=True)
    command = sub.add_parser("receipt")
    command.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "preview":
        actual = (
            json.loads(args.actual.read_text(encoding="utf-8"))
            if args.actual.exists() else {"components": {}}
        )
        deployment = (
            json.loads(args.deployment.read_text(encoding="utf-8")) if args.deployment else None
        )
        plan = preview(args.root, args.target, actual, deployment=deployment)
        atomic_json(args.output, plan)
        print(json.dumps(plan, indent=2))
    elif args.action == "apply":
        from .release_backend import CommandReleaseBackend
        deployment = json.loads(args.deployment.read_text(encoding="utf-8"))
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        backend = CommandReleaseBackend(args.root, deployment)
        print(json.dumps(ReleaseManager(args.root, args.actual, backend).apply(
            plan, deployment["node"]
        ), indent=2))
    else:
        print(args.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
