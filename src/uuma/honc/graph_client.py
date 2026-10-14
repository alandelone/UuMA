from __future__ import annotations

from typing import Any

import httpx


class GraphExecutionClient:
    """HTTP client communicating with Yonc Graph's execution endpoints."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        database_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.database_id = database_id
        self._client = client or httpx.Client(base_url=self.base_url, timeout=15.0)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.database_id:
            headers["X-Graph-Database-Id"] = self.database_id
        return headers

    def get_health(self) -> dict[str, Any]:
        resp = self._client.get(f"{self.base_url}/api/v2/health")
        resp.raise_for_status()
        data = resp.json()
        if "database_id" in data and not self.database_id:
            self.database_id = data["database_id"]
        return data

    def get_node(self, node_id: str) -> dict[str, Any]:
        resp = self._client.get(
            f"{self.base_url}/api/v2/nodes/{node_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def submit_action_decision(
        self,
        operation_id: str,
        node_id: str,
        action: str,
        decision_origin: dict[str, Any],
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"{self.base_url}/api/v2/execution/action-decisions",
            headers=self._headers(),
            json={
                "operation_id": operation_id,
                "node_id": node_id,
                "action": action,
                "decision_origin": decision_origin,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_receipt(self, operation_id: str) -> dict[str, Any] | None:
        resp = self._client.get(
            f"{self.base_url}/api/v2/execution/receipts/{operation_id}",
            headers=self._headers(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def submit_focus_event(
        self,
        interval_id: str,
        event_type: str,
        node_id: str | None = None,
        timestamp: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "interval_id": interval_id,
            "event_type": event_type,
        }
        if node_id:
            payload["node_id"] = node_id
        if timestamp:
            payload["timestamp"] = timestamp
        if duration_seconds is not None:
            payload["duration_seconds"] = duration_seconds

        resp = self._client.post(
            f"{self.base_url}/api/v2/execution/focus-events",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
