"""Hermes scheduler-script entry, using its existing at-most-once delivery queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .life_context import LifeContextBroker


class HermesReminderDelivery:
    def __init__(self, config: dict[str, Any]) -> None:
        from cron import delivery_queue, executions

        self.queue, self.executions, self.config = delivery_queue, executions, config

    def allocate(self, group: dict[str, Any]) -> str:
        record = self.executions.create_execution(
            self.config["scheduler_job_id"], source="honc-life:" + group["group_id"]
        )
        self.executions.mark_execution_running(record["id"])
        return record["id"]

    def deliver(self, group: dict[str, Any]) -> dict[str, Any]:
        identifier = group["native_execution_id"]
        if not identifier:
            raise ValueError("Original native attempt must be persisted before enqueue")
        binding = self.config["delivery_binding"]
        job = {
            "id": self.config["scheduler_job_id"],
            "name": "honc 习惯提醒",
            "profile": "honc",
            "profile_home": self.config["profile_home"],
            "origin": {
                **binding,
                "profile": "honc",
                "chat_type": "dm",
                "user_id": self.config["owner_id"],
            },
            "deliver": "origin",
            "execution_id": identifier,
            "no_agent": True,
            "attach_to_session": False,
        }
        self.queue.enqueue(identifier, job, group["content"])
        return self.lookup(identifier) or {"state": "QUEUED", "native_execution_id": identifier}

    def lookup(self, identifier: str) -> dict[str, Any] | None:
        value = self.queue.get_status(identifier)
        if value is None:
            return None
        native_state = value["status"]
        # 'failed' may follow a network-side effect; it does not prove that nothing was sent.
        state = {
            "delivered": "DELIVERED",
            "pending": "QUEUED",
            "delivering": "QUEUED",
            "unknown": "DELIVERY_UNKNOWN",
            "failed": "DELIVERY_UNKNOWN",
            "suppressed": "SUPPRESSED",
        }.get(native_state, "DELIVERY_UNKNOWN")
        receipt = {
            "state": state,
            "native_execution_id": identifier,
            "native_delivery_status": native_state,
            "finished_at": value.get("finished_at"),
        }
        if state == "DELIVERED":
            self.executions.finish_execution(identifier, success=True, delivery_outcome="delivered")
        elif native_state in {"unknown", "failed", "suppressed"}:
            self.executions.finish_execution(
                identifier,
                success=False,
                error="honc delivery " + native_state,
                delivery_outcome=native_state,
            )
        return receipt


def run_tick(
    config: dict[str, Any],
    *,
    now: datetime | None = None,
    delivery: HermesReminderDelivery | None = None,
) -> dict[str, int]:
    broker = LifeContextBroker(config)
    runtime = broker.runtime
    delivery = delivery or HermesReminderDelivery(config)
    now = now or datetime.now(UTC)
    runtime.reconcile(now, delivery.lookup)
    groups = runtime.prepare(now)
    for group in groups:
        runtime.dispatch(
            group["group_id"], group["fence"], now, delivery.deliver, allocate=delivery.allocate
        )
    return {"prepared_groups": len(groups)}


def main(config_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    run_tick(config)
    # Empty stdout keeps the outer Hermes no-agent tick silent. Only its delivery
    # queue sends the frozen business group, retaining the original native ID.
