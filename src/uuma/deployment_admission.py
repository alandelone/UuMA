"""Transactional intake gates for releases; existing work is never killed or resumed."""

from __future__ import annotations

import json

from .service import ConflictError


def current(conn, agent_id: str) -> dict:
    row = conn.execute(
        "SELECT payload_json FROM events WHERE event_type='DEPLOYMENT_INTAKE_CHANGED' "
        "AND aggregate_id=? ORDER BY sequence DESC LIMIT 1",
        (agent_id,),
    ).fetchone()
    return json.loads(row[0]) if row else {"paused": False}


def require_open(conn, agent_id: str):
    if current(conn, agent_id)["paused"]:
        raise ConflictError("Agent intake is paused for a manual deployment")


def set_admission(control, agents: list[str], plan_id: str, paused: bool):
    if not plan_id or not agents:
        raise ValueError("An immutable release plan and Agent set are required")
    for agent in agents:
        control.require_agent(agent)
    with control.events.transaction() as conn:
        for agent in agents:
            state = current(conn, agent)
            if state["paused"] and state["plan_id"] != plan_id:
                raise ConflictError("Another release owns this Agent's intake gate")
            control.events.append(
                event_type="DEPLOYMENT_INTAKE_CHANGED",
                aggregate_type="agent",
                aggregate_id=agent,
                actor_type="agent",
                actor_id="orchestrator",
                payload={"plan_id": plan_id, "paused": paused},
                conn=conn,
            )
