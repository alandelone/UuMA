"""Node endpoints linked to the existing Agent registry and control event chain."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, field_validator

from .control_client import validate_endpoint
from .models import StrictModel
from .service import NotFoundError, PolicyDeniedError


class EndpointBinding(StrictModel):
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    node_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    runtime: str = Field(min_length=1, max_length=100)
    endpoint: str
    protocol_version: Literal["1.0"] = "1.0"
    revision: str = Field(min_length=1, max_length=100)

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_protected(cls, value):
        return validate_endpoint(value)


class RuntimeRegistry:
    def __init__(self, control):
        self.control = control

    def bind(self, binding: EndpointBinding, *, actor_id: str):
        if actor_id != "orchestrator":
            raise PolicyDeniedError("Only the control identity can bind trusted runtime endpoints")
        self.control.require_agent(binding.agent_id)
        payload = binding.model_dump(mode="json")
        with self.control.events.transaction() as conn:
            self.control.events.append(
                event_type="AGENT_ENDPOINT_BOUND",
                aggregate_type="agent",
                aggregate_id=binding.agent_id,
                actor_type="agent",
                actor_id=actor_id,
                payload=payload,
                conn=conn,
            )
        return payload

    def get(self, agent_id: str):
        self.control.require_agent(agent_id)
        for binding in self.list():
            if binding["agent_id"] == agent_id:
                return binding
        raise NotFoundError("Agent has no trusted runtime endpoint")

    def list(self):
        with self.control.events.connect() as conn:
            return [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT payload_json FROM events WHERE sequence IN "
                    "(SELECT MAX(sequence) FROM events WHERE event_type='AGENT_ENDPOINT_BOUND' "
                    "GROUP BY aggregate_id) ORDER BY aggregate_id"
                )
            ]
