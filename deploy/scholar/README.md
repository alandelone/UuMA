# Scholar graph service host

`run_fieldkg.py` hosts the pinned RSTV4 FieldKG bridge in the existing server KAG
environment. It verifies a separate ScholarFieldKG project and schema before
serving. `/health` and `/runtime` include the embedding service's actual readiness.

`embeddings.py` provides real BGE-M3 CPU ONNX vectors with a server-local bearer
credential. Bind this listener to the Docker gateway address, not the public LAN.
It serves `/v1/embeddings` for the FieldKG bridge and OpenSPG project configuration.
The main graph bridge remains loopback-only and is reached from Windows over SSH.

Required graph-host environment:

- `RSTV4_KAG_CONFIG`: private YAML with namespaceScholarFieldKG and its own project ID.
- `RSTV4_KAG_BRIDGE_PORT=8892`.
- `UUMA_BGE_BACKEND=onnx`, existing model path and bounded CPU settings.
- `UUMA_KAG_LLM_MAX_RETRIES=0`, `UUMA_KAG_LLM_TIMEOUT_SECONDS=60`.
- `PYTHONPATH`: pinned full RSTV4 source followed by pinned UuMA source.

Required embedding-host environment adds `SCHOLAR_EMBEDDING_TOKEN_FILE` and
`SCHOLAR_EMBEDDING_BIND`. Use the same existing ONNX model/tokenizer files; do not
substitute different embeddings or reindex shared graphs during deployment.

Actual placement, immutable source ID, operational receipts and rollback scope:
`docs/operations/scholar-fieldkg-server-20261022.md`.
