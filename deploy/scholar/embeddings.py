"""Authenticated CPU BGE-M3 embeddings for Scholar and its OpenSPG project."""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from uuma.kag_bridge import _OnnxBGEM3Encoder


class EmbeddingInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input: str | list[str]
    model: str = "bge-m3"


def main() -> None:
    import uvicorn

    token = Path(os.environ["SCHOLAR_EMBEDDING_TOKEN_FILE"]).read_text().strip()
    if len(token) < 32:
        raise RuntimeError("A server-local embedding credential is required")
    encoder = None

    @asynccontextmanager
    async def lifespan(_app):
        nonlocal encoder
        encoder = _OnnxBGEM3Encoder(os.environ["UUMA_BGE_M3_PATH"])
        yield

    app = FastAPI(title="Scholar CPU embeddings", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"ready": encoder is not None, "model": "bge-m3", "dimensions": 1024,
                "device": "cpu", "backend": "onnxruntime"}

    @app.post("/v1/embeddings")
    def embeddings(payload: EmbeddingInput, authorization: str = Header(default="")) -> dict:
        if not secrets.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(status_code=401, detail="Invalid embedding credential")
        texts = [payload.input] if isinstance(payload.input, str) else payload.input
        if payload.model != "bge-m3" or not 1 <= len(texts) <= 16:
            raise HTTPException(status_code=422, detail="Unsupported model or batch size")
        if any(len(text) > 100000 for text in texts):
            raise HTTPException(status_code=422, detail="Embedding input is too large")
        vectors = encoder.encode(texts)["dense_vecs"]
        return {"object": "list", "model": "bge-m3", "data": [
            {"object": "embedding", "index": i, "embedding": vector.tolist()}
            for i, vector in enumerate(vectors)
        ], "usage": {"prompt_tokens": 0, "total_tokens": 0}}

    uvicorn.run(app, host=os.environ["SCHOLAR_EMBEDDING_BIND"], port=8893)


if __name__ == "__main__":
    main()
