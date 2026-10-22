"""Host the independent RSTV4 FieldKG bridge in the server's pinned KAG environment."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import urlopen

import yaml


def main() -> None:
    config = yaml.safe_load(Path(os.environ["RSTV4_KAG_CONFIG"]).read_text(encoding="utf-8"))
    project = config["project"]
    if project["namespace"] != "ScholarFieldKG" or str(project["id"]) == "1":
        raise RuntimeError("Scholar requires its own ScholarFieldKG project")
    if os.environ.get("UUMA_BGE_BACKEND") != "onnx":
        raise RuntimeError("The server FieldKG host requires the verified CPU ONNX backend")
    if os.environ.get("UUMA_KAG_LLM_MAX_RETRIES") != "0":
        raise RuntimeError("The server FieldKG host requires zero automatic model retries")

    from uuma.kag_bridge import _bge_runtime, _configure_local_bge_runtime
    from uuma.kag_llm_runtime import configure_kag_llm_runtime

    policy = configure_kag_llm_runtime()
    _configure_local_bge_runtime()

    from rstv4 import fieldkg_bridge

    fieldkg_bridge._init()

    from knext.project.client import ProjectClient
    from knext.schema.client import SchemaClient

    actual = ProjectClient(project["host_addr"], project["id"]).get_by_id(project["id"])
    if actual is None or actual.namespace != "ScholarFieldKG":
        raise RuntimeError("The configured OpenSPG project is not ScholarFieldKG")
    schema = SchemaClient(project["host_addr"], project["id"]).load()
    if not {"FieldKnowledgeObject", "Chunk"}.issubset(schema):
        raise RuntimeError("ScholarFieldKG schema is incomplete")

    original_health = fieldkg_bridge.health

    def runtime() -> dict:
        result = {
            **original_health(),
            "embedding": dict(_bge_runtime),
            "llm_policy": policy,
            "schema_verified": True,
        }
        try:
            endpoint = config["vectorize_model"]["base_url"].removesuffix("/v1") + "/health"
            with urlopen(endpoint, timeout=3) as response:
                embedding_health = json.load(response)
            if embedding_health.get("ready") is not True:
                raise RuntimeError("CPU embedding service is unavailable")
        except (OSError, ValueError, RuntimeError) as error:
            result.update(ready=False, error=str(error))
        return result

    fieldkg_bridge.app.router.routes = [
        route for route in fieldkg_bridge.app.router.routes
        if getattr(route, "path", None) != "/health"
    ]
    fieldkg_bridge.app.get("/health")(runtime)
    fieldkg_bridge.app.get("/runtime")(runtime)

    fieldkg_bridge.main()


if __name__ == "__main__":
    main()
