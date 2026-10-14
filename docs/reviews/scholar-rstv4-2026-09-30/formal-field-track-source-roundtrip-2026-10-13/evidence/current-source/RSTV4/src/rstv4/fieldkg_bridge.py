from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="RSTV4 Scholar FieldKG Bridge")
_initialized = False


class ProjectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    job_id: str
    aggregate_type: str
    aggregate_id: str
    field_id: str
    operation: str
    payload: dict[str, Any]


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str
    query: str
    mode: str = "AUTO"
    cross_field: bool = False


def _init() -> None:
    global _initialized
    if _initialized:
        return
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENROUTER_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
    from kag.common.conf import init_env

    init_env(config_file=os.environ.get("RSTV4_KAG_CONFIG"))
    _initialized = True


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        _init()
        from kag.common.conf import KAG_PROJECT_CONF

        return {
            "ready": bool(KAG_PROJECT_CONF.project_id and KAG_PROJECT_CONF.host_addr),
            "runtime": "OpenSPG/KAG",
            "namespace": "ScholarFieldKG",
            "project_id": KAG_PROJECT_CONF.project_id,
            "host_addr": KAG_PROJECT_CONF.host_addr,
        }
    except Exception as exc:  # bridge health must expose initialization failures
        return {"ready": False, "runtime": "OpenSPG/KAG", "error": str(exc)}


@app.post("/project")
def project(request: ProjectionRequest) -> dict[str, Any]:
    try:
        _init()
        from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
        from kag.builder.component.writer.kg_writer import KGWriter
        from kag.builder.model.sub_graph import Node, SubGraph
        from kag.common.conf import KAG_CONFIG
        from kag.interface import VectorizeModelABC

        content = request.payload.get("statement") or request.payload.get("content")
        if not content:
            content = json.dumps(request.payload, ensure_ascii=False, sort_keys=True)
        node = Node(
            _id=request.aggregate_id,
            name=str(content)[:1000],
            label="FieldKnowledgeObject",
            properties={
                "fieldId": request.field_id,
                "kind": request.aggregate_type,
                "content": str(content)[:100000],
                "canonicalId": request.aggregate_id,
                "recordJson": json.dumps(request.payload, ensure_ascii=False, sort_keys=True)[:100000],
            },
        )
        graph = SubGraph(nodes=[node], edges=[])
        writer = KGWriter(delete=request.operation == "DELETE")
        if request.operation != "DELETE":
            config = KAG_CONFIG.all_config.get("vectorize_model") or KAG_CONFIG.all_config.get("vectorizer")
            vectorizer = BatchVectorizer(vectorize_model=VectorizeModelABC.from_config(config))
            outputs = vectorizer.invoke(graph, write_ckpt=False)
            if outputs:
                graph = getattr(outputs[0], "data", outputs[0])
        writer.invoke(graph, write_ckpt=False)
        return {"applied": True, "job_id": request.job_id}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/retrieve")
async def retrieve(request: RetrieveRequest) -> dict[str, Any]:
    try:
        _init()
        from kag.common.conf import KAG_CONFIG
        from kag.interface import Context, ExecutorABC, Task

        scoped_query = request.query if request.cross_field else f"[fieldId={request.field_id}] {request.query}"
        executor = ExecutorABC.from_config(KAG_CONFIG.all_config["kag_hybrid_executor"])
        task = Task(executor=executor.schema()["name"], arguments={"query": scoped_query})
        await executor.ainvoke(query=scoped_query, task=task, context=Context())
        references = task.result.to_dict()
        return {
            "answer": task.result.summary,
            "references": references,
            "field_id": request.field_id,
            "cross_field": request.cross_field,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("RSTV4_KAG_BRIDGE_PORT", "8892")))


if __name__ == "__main__":
    main()
