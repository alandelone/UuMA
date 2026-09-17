from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import threading
from hashlib import sha256
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .kag_lifecycle import KagIdleTracker, runtime_lock

app = FastAPI(title="UuMA OpenSPG KAG bridge", version="0.1.0")
_init_lock = threading.Lock()
_initialized = False
_idle_tracker: KagIdleTracker | None = None
_bge_runtime: dict[str, Any] = {
    "backend": "unconfigured",
    "device": "unconfigured",
    "precision": "unknown",
}


@app.middleware("http")
async def track_kag_activity(request: Request, call_next: Any) -> Any:
    tracker = _idle_tracker
    if tracker is None or request.url.path not in {"/project", "/retrieve", "/extract"}:
        return await call_next(request)
    if not tracker.begin():
        return JSONResponse({"detail": "KAG is stopping after its idle timeout."}, status_code=503)
    try:
        return await call_next(request)
    finally:
        tracker.end()


def _stop_when_idle(
    tracker: KagIdleTracker,
    compose_file: Path,
    server: Any,
    stopped: threading.Event,
    *,
    poll_seconds: float = 5,
) -> None:
    while not stopped.wait(poll_seconds):
        if not tracker.idle_due():
            continue
        try:
            with runtime_lock(compose_file):
                if not tracker.claim_idle_shutdown():
                    continue
                server.should_exit = True
                stopped.wait()
                command = [
                    "docker", "compose", "-p", "uuma-wisdom-kag", "-f", str(compose_file),
                    "stop",
                ]
                for attempt in range(2):
                    try:
                        result = subprocess.run(
                            command, capture_output=True, text=True, timeout=90, check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        if result.returncode == 0:
                            return
                        detail = (result.stderr or result.stdout).strip()[-500:]
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        detail = str(exc)
                    logging.getLogger(__name__).error(
                        "KAG idle stop attempt %s failed: %s", attempt + 1, detail
                    )
                return
        except TimeoutError:
            logging.getLogger(__name__).warning("KAG idle stop deferred: runtime lock is busy")


class _OnnxBGEM3Encoder:
    """Small compatibility adapter for KAG's ``BGEM3FlagModel.encode`` call.

    The official BGE-M3 ONNX export already returns normalized 1024-dimensional
    ``sentence_embedding`` values. Keeping the session CPU-only avoids competing
    with user workloads already occupying the local GPU and has a much smaller
    native-memory footprint than loading the complete FlagEmbedding stack.
    """

    def __init__(self, model_path: str) -> None:
        import onnxruntime as ort
        from transformers import AutoTokenizer

        self._model_path = Path(model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(
            str(self._model_path), local_files_only=True
        )
        options = ort.SessionOptions()
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = max(
            1, int(os.environ.get("UUMA_BGE_ONNX_THREADS", "2"))
        )
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(self._model_path / "onnx" / "model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._max_length = max(
            8, int(os.environ.get("UUMA_BGE_MAX_LENGTH", "2048"))
        )

    def encode(self, texts: Any) -> dict[str, Any]:
        import numpy as np

        scalar = isinstance(texts, str)
        batch = [texts] if scalar else list(texts)
        encoded = self._tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=self._max_length,
            return_tensors="np",
        )
        dense = self._session.run(
            ["sentence_embedding"],
            {
                "input_ids": encoded["input_ids"].astype(np.int64, copy=False),
                "attention_mask": encoded["attention_mask"].astype(
                    np.int64, copy=False
                ),
            },
        )[0]
        return {"dense_vecs": dense[0] if scalar else dense}


def _configure_local_bge_runtime() -> None:
    """Fit KAG v0.8's BGE-M3 loader to the available local resources.

    KAG v0.8 hard-codes ``use_fp16=False``. That exceeds the memory of common
    12 GiB local GPUs when another local model is active. Prefer BGE-M3's official
    ONNX export on CPU, while retaining an explicit FlagEmbedding/GPU option.
    Keep the upstream class/registry and change only its loader in this bridge.
    """
    import logging

    from kag.common.vectorize_model.local_bge_model import LocalBGEM3VectorizeModel

    configured_path = os.environ.get("UUMA_BGE_M3_PATH", "")
    onnx_path = Path(configured_path) / "onnx" / "model.onnx"
    requested_backend = os.environ.get("UUMA_BGE_BACKEND", "auto").lower()
    if requested_backend not in {"auto", "onnx", "flagembedding"}:
        raise RuntimeError(
            "UUMA_BGE_BACKEND must be auto, onnx, or flagembedding."
        )
    backend = (
        "onnx"
        if requested_backend == "onnx"
        or (requested_backend == "auto" and onnx_path.is_file())
        else "flagembedding"
    )
    if backend == "onnx":
        if not onnx_path.is_file():
            raise RuntimeError(f"BGE-M3 ONNX model is missing at {onnx_path}.")
        _bge_runtime.update(
            {
                "backend": "onnxruntime",
                "device": "cpu",
                "precision": "fp32",
                "max_length": max(
                    8, int(os.environ.get("UUMA_BGE_MAX_LENGTH", "2048"))
                ),
                "threads": max(
                    1, int(os.environ.get("UUMA_BGE_ONNX_THREADS", "2"))
                ),
            }
        )

        def load_onnx_model(_self: Any, path: str) -> _OnnxBGEM3Encoder:
            logging.getLogger(__name__).info(
                "Loading BGE-M3 ONNX export from %r on CPU", path
            )
            return _OnnxBGEM3Encoder(path)

        LocalBGEM3VectorizeModel._load_model = load_onnx_model
        return

    import torch
    from FlagEmbedding import BGEM3FlagModel

    requested_device = os.environ.get("UUMA_BGE_DEVICE", "auto").lower()
    minimum_free_gib = float(os.environ.get("UUMA_BGE_MIN_FREE_GIB", "8"))
    cuda_available = torch.cuda.is_available()
    free_gib = 0.0
    if cuda_available:
        free_bytes, _total_bytes = torch.cuda.mem_get_info()
        free_gib = free_bytes / (1024**3)
    if requested_device == "cpu":
        device = "cpu"
    elif requested_device.startswith("cuda"):
        if not cuda_available:
            raise RuntimeError("UUMA_BGE_DEVICE requests CUDA, but CUDA is unavailable.")
        device = requested_device if ":" in requested_device else "cuda:0"
    else:
        device = "cuda:0" if cuda_available and free_gib >= minimum_free_gib else "cpu"
    use_fp16 = device.startswith("cuda") and os.environ.get(
        "UUMA_BGE_USE_FP16", "true"
    ).lower() not in {"0", "false", "no"}
    _bge_runtime.update(
        {
            "backend": "flagembedding",
            "device": device,
            "precision": "fp16" if use_fp16 else "fp32",
            "cuda_available": cuda_available,
            "cuda_free_gib_at_start": round(free_gib, 2),
        }
    )

    def load_flag_model(_self: Any, path: str) -> BGEM3FlagModel:
        logging.getLogger(__name__).info(
            "Loading BGE-M3 from %r on %s with FP16=%s (CUDA free %.2f GiB)",
            path,
            device,
            use_fp16,
            free_gib,
        )
        return BGEM3FlagModel(path, use_fp16=use_fp16, devices=device)

    LocalBGEM3VectorizeModel._load_model = load_flag_model


class ProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projection_job_id: str
    event_sequence: int
    aggregate_type: str
    aggregate_id: str
    operation: str
    payload: dict[str, Any]
    status: str | None = None
    attempts: int | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    mode: str = "SIMPLE"


class ExtractChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    name: str
    text: str


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks: list[ExtractChunk]


def _init_kag() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        try:
            if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENROUTER_API_KEY"):
                os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
            from kag.common.conf import init_env

            _configure_local_bge_runtime()
            config_file = os.environ.get("UUMA_KAG_CONFIG")
            init_env(config_file=config_file)
        except Exception as exc:
            raise RuntimeError(f"KAG v0.8 initialization failed: {exc}") from exc
        _initialized = True


def _record_name(record: dict[str, Any], aggregate_id: str) -> str:
    for field in ("canonical_name", "title", "statement", "text", "excerpt", "name"):
        value = record.get(field)
        if value:
            return str(value)[:1000]
    return aggregate_id


def _record_content(record: dict[str, Any]) -> str:
    for field in ("text", "statement", "excerpt", "description", "title"):
        value = record.get(field)
        if value:
            return str(value)[:100000]
    return json.dumps(record, ensure_ascii=False, sort_keys=True)[:100000]


def _node(node_id: str, name: str, kind: str, record: dict[str, Any] | None = None):
    from kag.builder.model.sub_graph import Node

    record = record or {}
    properties = {
        "kind": kind,
        "content": _record_content(record),
        "canonicalStatus": str(record.get("status", "")),
        "canonicalRevision": str(record.get("revision", "")),
        "recordJson": json.dumps(record, ensure_ascii=False, sort_keys=True),
    }
    return Node(_id=node_id, name=name, label="KnowledgeObject", properties=properties)


def _chunk_node(node_id: str, record: dict[str, Any]):
    """Project canonical chunks into KAG's native retrievable Chunk type."""
    from kag.builder.model.sub_graph import Node

    ordinal = record.get("ordinal", "")
    return Node(
        _id=node_id,
        name=f"canonical chunk {ordinal}".strip(),
        label="Chunk",
        properties={"content": str(record.get("text", ""))[:100000]},
    )


def _edge(
    edge_id: str,
    source_id: str,
    target_id: str,
    predicate: str,
    record: dict[str, Any],
    *,
    source_label: str = "KnowledgeObject",
    target_label: str = "KnowledgeObject",
):
    from kag.builder.model.sub_graph import Edge, Node

    source = Node(_id=source_id, name=source_id, label=source_label, properties={})
    target = Node(_id=target_id, name=target_id, label=target_label, properties={})
    return Edge(
        _id=edge_id,
        from_node=source,
        to_node=target,
        label="linkedTo",
        properties={
            "predicate": predicate,
            "recordJson": json.dumps(record, ensure_ascii=False, sort_keys=True),
        },
    )


def _to_subgraph(request: ProjectRequest):
    from kag.builder.model.sub_graph import SubGraph

    record = request.payload.get("record", {})
    aggregate_type = request.aggregate_type
    nodes = []
    edges = []
    link_types = {"claim_evidence_link", "chunk_knowledge_link", "relation"}
    if aggregate_type == "chunk":
        nodes.append(_chunk_node(request.aggregate_id, record))
    elif aggregate_type not in link_types:
        nodes.append(
            _node(
                request.aggregate_id,
                _record_name(record, request.aggregate_id),
                aggregate_type,
                record,
            )
        )
    if aggregate_type == "document":
        edges.append(
            _edge(request.aggregate_id, request.aggregate_id, record["source_id"], "derivedFrom", record)
        )
    elif aggregate_type == "chunk":
        edges.append(
            _edge(
                request.aggregate_id,
                request.aggregate_id,
                record["document_id"],
                "partOf",
                record,
                source_label="Chunk",
            )
        )
    elif aggregate_type == "evidence":
        edges.append(
            _edge(request.aggregate_id, request.aggregate_id, record["source_id"], "fromSource", record)
        )
    elif aggregate_type == "claim_evidence_link":
        edges.append(
            _edge(
                request.aggregate_id,
                record["claim_id"],
                record["evidence_id"],
                str(record["stance"]).lower(),
                record,
            )
        )
    elif aggregate_type == "chunk_knowledge_link":
        edges.append(
            _edge(
                request.aggregate_id,
                record["chunk_id"],
                record["target_id"],
                str(record["link_type"]).lower(),
                record,
                source_label="Chunk",
            )
        )
    elif aggregate_type == "relation":
        target_id = record.get("object_entity_id")
        if not target_id:
            literal_json = json.dumps(record.get("literal_value"), ensure_ascii=False, sort_keys=True)
            target_id = f"literal_{sha256(literal_json.encode('utf-8')).hexdigest()}"
            nodes.append(
                _node(
                    target_id,
                    str(record.get("literal_value")),
                    "literal",
                    {"literal_value": record.get("literal_value")},
                )
            )
        edges.append(
            _edge(
                request.aggregate_id,
                record["subject_entity_id"],
                target_id,
                record["predicate"],
                record,
            )
        )
    return SubGraph(nodes=nodes, edges=edges)


def _component_data(output: Any) -> Any:
    return getattr(output, "data", output)


@app.get("/health")
def health() -> dict[str, Any]:
    if _idle_tracker is not None and _idle_tracker.closing:
        return {"ready": False, "runtime": "OpenSPG/KAG", "error": "Idle shutdown in progress"}
    try:
        _init_kag()
        from kag.common.conf import KAG_PROJECT_CONF

        ready = bool(KAG_PROJECT_CONF.project_id and KAG_PROJECT_CONF.host_addr)
        if ready:
            from urllib.parse import urlparse

            try:
                parsed = urlparse(str(KAG_PROJECT_CONF.host_addr))
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                with socket.create_connection((parsed.hostname, port), timeout=3):
                    pass
            except (OSError, ValueError) as exc:
                return {
                    "ready": False,
                    "runtime": "OpenSPG/KAG",
                    "version": "0.8.0",
                    "error": f"OpenSPG server is unreachable: {exc}",
                }
        return {
            "ready": ready,
            "runtime": "OpenSPG/KAG",
            "version": "0.8.0",
            "project_id": KAG_PROJECT_CONF.project_id,
            "host_addr": KAG_PROJECT_CONF.host_addr,
            "embedding": dict(_bge_runtime),
        }
    except Exception as exc:  # noqa: BLE001 -- Health reports optional KAG initialization failures.
        return {"ready": False, "runtime": "OpenSPG/KAG", "error": str(exc)}


@app.post("/project")
def project(request: ProjectRequest) -> dict[str, Any]:
    try:
        _init_kag()
        from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
        from kag.builder.component.writer.kg_writer import KGWriter
        from kag.common.conf import KAG_CONFIG
        from kag.interface import VectorizeModelABC

        graph = _to_subgraph(request)
        delete = request.operation == "DELETE"
        if not delete and graph.nodes:
            vector_config = KAG_CONFIG.all_config.get("vectorize_model") or KAG_CONFIG.all_config.get(
                "vectorizer"
            )
            if not vector_config:
                raise RuntimeError("KAG vectorize_model is not configured.")
            vector_model = VectorizeModelABC.from_config(vector_config)
            vectorizer = BatchVectorizer(vectorize_model=vector_model)
            outputs = vectorizer.invoke(graph, write_ckpt=False)
            graph = _component_data(outputs[0]) if outputs else graph
        writer = KGWriter(delete=delete)
        if delete:
            graph = writer.standarlize_graph(graph)
        writer.invoke(graph, write_ckpt=False)
        return {
            "applied": True,
            "projection_job_id": request.projection_job_id,
            "event_sequence": request.event_sequence,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _canonical_refs(value: Any) -> list[str]:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    prefixes = (
        "src|ev|doc|chunk|claim|entity|relation|schema|freshness|link|cklink"
    )
    return sorted(set(re.findall(rf"(?:{prefixes})_[0-9a-f]{{32}}", serialized)))


@app.post("/retrieve")
async def retrieve(request: RetrieveRequest) -> dict[str, Any]:
    try:
        _init_kag()
        if request.mode.upper() == "DEEP":
            from kag.open_benchmark.utils.eval_qa import EvalQa

            qa = EvalQa(task_name="qa", solver_pipeline_name="kag_solver_pipeline")
            answer, trace = await qa.qa(query=request.query, gold="")
            return {
                "answer": answer,
                "result_refs": _canonical_refs(trace),
                "steps": [
                    {
                        "step": 1,
                        "operator": "SEMANTIC",
                        "query": request.query,
                        "result_refs": _canonical_refs(trace),
                        "summary": "KAG logic-form planning, hybrid retrieval, deduction, and generation.",
                    }
                ],
            }
        from kag.common.conf import KAG_CONFIG
        from kag.interface import Context, ExecutorABC, Task

        executor = ExecutorABC.from_config(KAG_CONFIG.all_config["kag_hybrid_executor"])
        task = Task(executor=executor.schema()["name"], arguments={"query": request.query})
        context = Context()
        await executor.ainvoke(query=request.query, task=task, context=context)
        references = task.result.to_dict()
        return {
            "answer": task.result.summary,
            "references": references,
            "result_refs": _canonical_refs(references),
            "steps": [
                {
                    "step": 1,
                    "operator": "SEMANTIC",
                    "query": request.query,
                    "result_refs": _canonical_refs(references),
                    "summary": "KAG exact graph, fuzzy graph, and chunk-vector hybrid retrieval.",
                }
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/extract")
async def extract(request: ExtractRequest) -> dict[str, Any]:
    try:
        _init_kag()
        from kag.builder.component.extractor.schema_free_extractor import SchemaFreeExtractor
        from kag.builder.model.chunk import Chunk
        from kag.common.conf import KAG_CONFIG
        from kag.interface import LLMClient

        llm_config = KAG_CONFIG.all_config.get("openie_llm")
        if not llm_config:
            raise RuntimeError("KAG openie_llm is not configured.")
        llm = LLMClient.from_config(llm_config)
        extractor = SchemaFreeExtractor(llm=llm)
        results: list[dict[str, Any]] = []
        for item in request.chunks:
            chunk = Chunk(id=item.chunk_id, name=item.name, content=item.text)
            outputs = await extractor.ainvoke(chunk, write_ckpt=False)
            graph = _component_data(outputs[0]) if outputs else None
            if graph is None:
                results.append({"chunk_id": item.chunk_id, "entities": [], "relations": []})
                continue
            entities = [
                {
                    "source_ref": node.id,
                    "name": node.name,
                    "entity_type": node.label,
                    "properties": node.properties,
                }
                for node in graph.nodes
                if node.id != item.chunk_id and node.label != "Chunk"
            ]
            relations = [
                {
                    "source_ref": edge.from_id,
                    "predicate": edge.label,
                    "target_ref": edge.to_id,
                    "properties": edge.properties,
                }
                for edge in graph.edges
                if edge.label not in {"source", "OfficialName"}
                and edge.from_id != item.chunk_id
                and edge.to_id != item.chunk_id
            ]
            results.append(
                {"chunk_id": item.chunk_id, "entities": entities, "relations": relations}
            )
        return {"chunks": results, "extractor": "OpenSPG/KAG v0.8 schema_free_extractor"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    global _idle_tracker
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=int(os.environ.get("UUMA_KAG_BRIDGE_PORT", "8891")))
    )
    compose_value = os.environ.get("UUMA_KAG_COMPOSE_FILE")
    idle_seconds = float(os.environ.get("UUMA_KAG_IDLE_SECONDS", "1800"))
    stopped = threading.Event()
    monitor: threading.Thread | None = None
    if compose_value and idle_seconds > 0:
        compose_file = Path(compose_value).expanduser().resolve()
        if compose_file.is_file():
            lifecycle_log = RotatingFileHandler(
                compose_file.parent / "bridge-lifecycle.log",
                maxBytes=1_000_000,
                backupCount=2,
                encoding="utf-8",
            )
            lifecycle_log.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logging.getLogger(__name__).addHandler(lifecycle_log)
            _idle_tracker = KagIdleTracker(idle_seconds)
            monitor = threading.Thread(
                target=_stop_when_idle,
                args=(_idle_tracker, compose_file, server, stopped),
                name="uuma-kag-idle",
                daemon=True,
            )
            monitor.start()
    try:
        server.run()
    finally:
        stopped.set()
        if monitor is not None:
            monitor.join(timeout=200)


if __name__ == "__main__":
    main()
