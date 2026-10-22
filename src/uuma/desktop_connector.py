"""Finite desktop requests with authorization rechecks and no blind side-effect replay."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import Field

from .models import StrictModel
from .node_journal import NodeJournal


class DesktopRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=200)
    run_id: str
    execution_epoch: int = Field(ge=1)
    operation: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime
    expires_at: datetime

    @classmethod
    def issue(cls, **values):
        now = datetime.now(UTC)
        return cls(**values, created_at=now, expires_at=now + timedelta(minutes=30))


class DesktopConnector:
    def __init__(self, journal: NodeJournal, authorize: Callable, handlers: dict[str, Callable]):
        self.journal, self.authorize, self.handlers = journal, authorize, handlers

    def execute(self, identity: str, request: DesktopRequest) -> dict:
        now = datetime.now(UTC)
        if (
            request.created_at.tzinfo is None
            or request.expires_at.tzinfo is None
            or request.created_at > now
            or request.expires_at <= request.created_at
            or request.expires_at - request.created_at > timedelta(minutes=30)
        ):
            raise ValueError("Desktop request has an invalid validity interval")
        self.authorize(identity, request)
        if request.operation not in self.handlers:
            raise PermissionError("Desktop operation is not in the installed allowlist")
        key = f"desktop:{identity}:{request.request_id}"
        record, fresh = self.journal.reserve(
            key,
            request.model_dump(mode="json"),
            {
                "phase": "WAITING",
                "run_id": request.run_id,
                "operation": request.operation,
                "expires_at": request.expires_at.isoformat(),
            },
        )
        if record["phase"] in {"COMPLETED", "UNCERTAIN", "EXECUTING", "EXPIRED"}:
            return record
        if now >= request.expires_at:
            record = {**record, "phase": "EXPIRED", "requires_confirmation": True}
        else:
            # Claim execution before invoking a side effect; after a crash it requires reconciliation.
            # reserve's unique key is the admission lock: only the creator may execute.
            if not fresh:
                return {**record, "phase": "RECONCILIATION_REQUIRED"}
            self.authorize(identity, request)
            self.journal.update(key, {**record, "phase": "EXECUTING"})
            try:
                result = self.handlers[request.operation](identity, request.payload)
                record = {**record, "phase": "COMPLETED", "result": result}
            except Exception:  # noqa: BLE001 -- every uncertain side effect requires reconciliation
                record = {**record, "phase": "UNCERTAIN", "requires_reconciliation": True}
        self.journal.update(key, record)
        return record
