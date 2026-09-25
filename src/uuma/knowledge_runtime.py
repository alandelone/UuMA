"""Profile-bound, fail-closed readiness for the two knowledge graph consumers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .kag_adapter import KagRuntimeManager, KagUnavailableError, OpenSpgKagBackend
from .kag_lifecycle import launch_runtime_process, runtime_lock


def _request(url: str, payload: dict[str, Any] | None = None) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=8) as response:
        return json.load(response)


class ScholarRuntime(KagRuntimeManager):
    source_path: Path

    def _ensure_bridge_process(self) -> None:
        try:
            if _request(self.bridge_url + "/health").get("ready") is True:
                return
        except (OSError, ValueError):
            pass
        if not self.bridge_python or not self.kag_config:
            raise KagUnavailableError("Scholar runtime configuration is missing")
        environment = dict(os.environ)
        environment.update({
            "PYTHONPATH": str(self.source_path),
            "RSTV4_KAG_CONFIG": str(self.kag_config),
            "RSTV4_KAG_BRIDGE_PORT": "8892",
        })
        launch_runtime_process(
            [str(self.bridge_python), "-m", "rstv4.fieldkg_bridge"],
            cwd=self.kag_config.parent, environment=environment,
        )


def _configuration(profile: str) -> tuple[KagRuntimeManager, str, str, str]:
    root = Path(__file__).resolve().parents[2]
    if profile == "wisdom-oldman":
        runtime = OpenSpgKagBackend.from_env().runtime
        return runtime, "Uuma", os.environ.get("UUMA_KAG_PROJECT_ID", "1"), "KnowledgeObject"
    if profile != "scholar":
        raise PermissionError("Graph readiness is restricted to knowledge specialist profiles")
    rst = Path(os.environ.get("RSTV4_ROOT") or root.parent / "RSTV4")
    saved = json.loads((rst / ".rstv4-local/fieldkg/runtime.json").read_text(encoding="utf-8-sig"))
    if saved.get("namespace") != "ScholarFieldKG" or saved.get("bridge_url") != "http://127.0.0.1:8892":
        raise KagUnavailableError("Scholar runtime identity does not match its dedicated graph")
    runtime = ScholarRuntime(
        bridge_url=saved["bridge_url"],
        compose_file=Path(os.environ.get(
            "UUMA_KAG_COMPOSE_FILE", root / ".uuma-local/kag/docker-compose-west.yml"
        )),
        bridge_python=Path(saved["kag_python"]), kag_config=Path(saved["kag_config"]),
    )
    runtime.source_path = rst / "src"
    return runtime, "ScholarFieldKG", str(saved["project_id"]), "FieldKnowledgeObject"


def _probe(runtime: KagRuntimeManager, namespace: str, project_id: str, kind: str) -> None:
    health = _request(runtime.bridge_url + "/health")
    if health.get("ready") is not True or str(health.get("project_id")) != project_id:
        raise KagUnavailableError("The graph bridge is not ready for the expected project")
    host = str(health.get("host_addr", "")).rstrip("/")
    if not host.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise KagUnavailableError("The graph server must be the configured local service")
    api = host + "/public/v1"
    projects = _request(api + "/project")
    if not isinstance(projects, list) or not any(
        str(p.get("id")) == project_id and p.get("namespace") == namespace for p in projects
    ):
        raise KagUnavailableError("The expected knowledge graph project is missing")
    schema = _request(api + "/schema/queryProjectSchema?projectId=" + project_id)
    names = [t.get("basicInfo", {}).get("name", {}) for t in schema.get("spgTypes", [])]
    if not any(n.get("namespace") == namespace and n.get("nameEn") == kind for n in names):
        raise KagUnavailableError("The expected knowledge graph schema is missing")
    # Read an intentionally absent identifier: [] is a healthy empty result, not evidence.
    result = _request(api + "/query/spgType", {
        "projectId": int(project_id), "spgType": namespace + "." + kind,
        "ids": ["__uuma_readiness_probe__"],
    })
    if not isinstance(result, list):
        raise KagUnavailableError("The graph storage read did not return a valid response")


def ensure_knowledge_graph(profile: str, *, recover: bool = True) -> dict[str, Any]:
    """Verify bridge, project, schema and graph read; never create a missing graph."""
    if profile not in {"scholar", "wisdom-oldman"}:
        raise PermissionError("This profile does not own a managed knowledge graph")
    recovered = False
    try:
        runtime, namespace, project_id, kind = _configuration(profile)
        try:
            _probe(runtime, namespace, project_id, kind)
        except (OSError, ValueError, KeyError, TypeError, KagUnavailableError):
            if not recover or not runtime.auto_recover or not runtime.compose_file:
                raise
            # Do not accept the bridges' shallow /health as proof of graph availability.
            with runtime_lock(runtime.compose_file):
                runtime._recover_locked(runtime.compose_file)
            recovered = True
            deadline = time.monotonic() + 45
            while True:
                try:
                    _probe(runtime, namespace, project_id, kind)
                    break
                except (OSError, ValueError, KagUnavailableError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(2)
        return {"ready": True, "graph": namespace, "recovered": recovered}
    except (OSError, ValueError, KeyError, TypeError, TimeoutError, KagUnavailableError) as exc:
        return {
            "ready": False, "status": "BLOCKED", "recovered": recovered,
            "reason": str(exc) if isinstance(exc, KagUnavailableError) else type(exc).__name__,
        }
