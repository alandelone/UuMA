from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .database import transaction
from .fieldkg import digest, stable_id


class FieldKGProjectionError(RuntimeError):
    pass


class FieldKGKagClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or os.environ.get("RSTV4_KAG_BRIDGE_URL", "http://127.0.0.1:8892")).rstrip("/")
        self.timeout = timeout

    def request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}", data=body, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8") or "{}")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise FieldKGProjectionError(str(exc)) from exc
        if not isinstance(result, dict):
            raise FieldKGProjectionError("FieldKG bridge returned a non-object response")
        return result

    def health(self) -> dict[str, Any]:
        return self.request("/health")

    def project(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.request("/project", method="POST", payload=job)

    def query(self, field_id: str, query: str, mode: str = "AUTO", cross_field: bool = False) -> dict[str, Any]:
        return self.request(
            "/retrieve", method="POST",
            payload={"field_id": field_id, "query": query, "mode": mode, "cross_field": cross_field},
        )


class FieldKGProjectionWorker:
    def __init__(self, db_path: Any, client: FieldKGKagClient | None = None) -> None:
        self.db_path = db_path
        self.client = client or FieldKGKagClient()

    def health(self) -> dict[str, Any]:
        with transaction(self.db_path) as conn:
            counts = dict(conn.execute(
                """SELECT
                   SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) pending,
                   SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) failed,
                   SUM(CASE WHEN status='APPLIED' THEN 1 ELSE 0 END) applied
                   FROM projection_outbox"""
            ).fetchone())
        try:
            backend = self.client.health()
        except FieldKGProjectionError as exc:
            backend = {"ready": False, "error": str(exc)}
        return {"backend": backend, "outbox": {key: value or 0 for key, value in counts.items()}}

    def sync(self, limit: int = 100) -> dict[str, Any]:
        if self.client.health().get("ready") is not True:
            raise FieldKGProjectionError("Scholar FieldKG bridge is not ready")
        with transaction(self.db_path) as conn:
            jobs = [dict(row) for row in conn.execute(
                "SELECT * FROM projection_outbox WHERE status IN ('PENDING','FAILED') ORDER BY created_at LIMIT ?",
                (limit,),
            )]
        applied = failed = 0
        for job in jobs:
            try:
                payload_json = job.pop("payload_json")
                result = self.client.project({**job, "payload": json.loads(payload_json)})
                if result.get("applied") is not True:
                    raise FieldKGProjectionError(str(result))
                with transaction(self.db_path) as conn:
                    conn.execute(
                        "UPDATE projection_outbox SET status='APPLIED',attempts=attempts+1,last_error=NULL,updated_at=? WHERE job_id=?",
                        (datetime.now(UTC).isoformat(), job["job_id"]),
                    )
                    conn.execute(
                        """INSERT INTO projection_watermarks VALUES('ScholarFieldKG',?,?)
                           ON CONFLICT(projection_name) DO UPDATE SET last_job_id=excluded.last_job_id,
                           updated_at=excluded.updated_at""",
                        (job["job_id"], datetime.now(UTC).isoformat()),
                    )
                applied += 1
            except Exception as exc:  # persist failures for visible retry
                with transaction(self.db_path) as conn:
                    conn.execute(
                        "UPDATE projection_outbox SET status='FAILED',attempts=attempts+1,last_error=?,updated_at=? WHERE job_id=?",
                        (str(exc)[:8000], datetime.now(UTC).isoformat(), job["job_id"]),
                    )
                failed += 1
        return {"processed": len(jobs), "applied": applied, "failed": failed}

    def rebuild_outbox(self) -> dict[str, int]:
        created = 0
        timestamp = datetime.now(UTC).isoformat()
        with transaction(self.db_path) as conn:
            conn.execute("DELETE FROM projection_outbox")
            objects: list[tuple[str, str, str, dict[str, Any]]] = []
            for row in conn.execute("SELECT * FROM evidence WHERE scope_kind='FIELDKG'"):
                objects.append(("Evidence", row["evidence_id"], row["field_id"], dict(row)))
            for row in conn.execute("SELECT * FROM fieldkg_candidate_gaps WHERE status='ACCEPTED'"):
                objects.append(("CandidateGap", row["candidate_gap_id"], row["field_id"], dict(row)))
            for row in conn.execute("SELECT * FROM fieldkg_snapshots WHERE status='SEALED'"):
                objects.append(("FieldKGSnapshot", row["snapshot_id"], row["field_id"], dict(row)))
            for aggregate_type, aggregate_id, field_id, payload in objects:
                job_id = stable_id("projection", aggregate_type, aggregate_id, "UPSERT", digest(payload))
                conn.execute(
                    "INSERT INTO projection_outbox VALUES(?,?,?,?,? ,?,'PENDING',0,NULL,?,?)",
                    (job_id, aggregate_type, aggregate_id, field_id, "UPSERT", json.dumps(payload, ensure_ascii=False), timestamp, timestamp),
                )
                created += 1
        return {"created": created}
