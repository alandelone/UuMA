"""Save consultation unknowns through Wisdom's own semantic MCP before submitting a reply."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any


def run_sync(factory: Callable) -> Any:
    """FastMCP can invoke a synchronous tool while its asyncio loop is running."""
    def invoke() -> Any:
        return asyncio.run(factory())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return invoke()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(invoke).result(timeout=160)


def retain_records(result: Any, task: dict, call: Callable[[str, dict], dict]) -> Any:
    """Use immutable assignment inputs and actual readbacks, never model-supplied record IDs."""
    contract = task["contract"]
    if contract.get("source") != "consultation":
        return result
    if result.outcome.value in {"FAILED", "CANCELLED"}:
        return result
    if result.agent_id != "wisdom-oldman" or task.get("assignee") != "wisdom-oldman":
        raise PermissionError("Consultation retention requires its assigned Wisdom owner")
    extension = contract["output_schema"]["x-uuma-knowledge-consultation"]
    if extension["version"] != "brainstormer-wisdom-v1":
        raise ValueError("Unknown consultation retention contract")
    request = extension["request"]
    answer = result.partial_state.get("consultation")
    if not answer or answer.get("status") == "ANSWERED":
        return result
    questions = answer.get("remaining_questions") or []
    if (not isinstance(questions, list) or len(questions) > 20
            or any(not isinstance(q, str) or not 1 <= len(q) <= 2000 for q in questions)):
        raise ValueError("Invalid bounded consultation questions")
    suffix = sha256(result.run_id.encode()).hexdigest()[:24]
    root_id, gap_id = "question_consult_" + suffix, "gap_consult_" + suffix
    provenance = (
        f"Consultation uuma:run:{result.run_id}; parent uuma:run:{request['parent_run_id']}; "
        f"Brainstormer project {request['project_id']}; topic {request['topic_id']}. "
        f"Purpose: {request['purpose']}. Original source references remain in the immutable "
        "consultation task contract. Retention alone does not initiate research or approve knowledge."
    )
    verified: list[str] = []

    def ensure(kind: str, identifier: str, expected: dict) -> None:
        current = call("knowledge_get", {"object_id": identifier})
        if current.get("_missing") is True:
            call("knowledge_add_" + kind, {kind + "_json": json.dumps(expected)})
            current = call("knowledge_get", {"object_id": identifier})
        record = current.get("record")
        if not isinstance(record, dict) or any(record.get(k) != v for k, v in expected.items()):
            raise RuntimeError("Consultation retention readback mismatch: " + identifier)
        verified.append(identifier)

    ensure("question", root_id, {
        "question_id": root_id, "text": request["question"],
        "why_worth_knowing": provenance,
    })
    children = []
    for index, question in enumerate(questions):
        identifier = root_id + "_" + str(index + 1)
        ensure("question", identifier, {
            "question_id": identifier, "text": question,
            "why_worth_knowing": provenance, "parent_question_id": root_id,
        })
        children.append(identifier)
    ensure("gap", gap_id, {
        "gap_id": gap_id, "gap_type": "UNANSWERED_QUESTION", "question_id": root_id,
        "reason": "Unanswered consultation; retained child questions: " + json.dumps(children),
        "why_worthwhile": provenance,
        "current_knowledge": "Qualified candidate reply and remaining inputs are retained in "
        f"uuma:run:{result.run_id}; no claim is approved by this retention receipt.",
    })
    normalized = result.model_copy(deep=True)
    original = deepcopy(answer)
    normalized.partial_state["consultation_model_response"] = original
    normalized.partial_state["consultation"]["research_refs"] = [root_id, gap_id]
    for reference in original.get("research_refs") or []:
        if reference not in verified:
            normalized.partial_state["consultation"]["answer"] = (
                normalized.partial_state["consultation"]["answer"].replace(
                    reference, "[unverified model reference]",
                )
            )
    normalized.partial_state["consultation_retention"] = {
        "status": "READ_BACK_VERIFIED", "question_id": root_id, "gap_id": gap_id,
        "child_question_ids": children, "verified_record_ids": verified,
        "consultation_run_ref": "uuma:run:" + result.run_id,
        "research_started": False, "canonical_knowledge_approved": False,
    }
    return normalized


def retain_consultation_result(result: Any, task: dict, profile_path: str) -> Any:
    """Connect only to the configured Wisdom-owned knowledge MCP; never open a database."""
    if os.environ.get("UUMA_AGENT_ID") != "wisdom-oldman":
        raise PermissionError("Only Wisdom may retain its consultation knowledge questions")
    profile = Path(profile_path).resolve()
    if profile.name != "wisdom-oldman" or not (profile / "config.yaml").is_file():
        raise RuntimeError("An explicit existing Wisdom profile is required for retention")

    async def run() -> Any:
        import yaml
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        config = yaml.safe_load((profile / "config.yaml").read_text())
        entries = [entry for entry in config["mcp_servers"].values()
                   if "uuma.mcp_knowledge" in (entry.get("args") or [])]
        if len(entries) != 1:
            raise RuntimeError("Expected exactly one configured Wisdom semantic knowledge MCP")
        entry = entries[0]
        env = os.environ.copy()
        env.update({k: str(v) for k, v in entry.get("env", {}).items()})
        if env.get("UUMA_AGENT_ID") != "wisdom-oldman":
            raise PermissionError("Knowledge MCP owner must remain Wisdom")
        allowed = entry.get("tools", {}).get("include")
        required = {"knowledge_get", "knowledge_add_question", "knowledge_add_gap"}
        if allowed is not None and not required.issubset(allowed):
            raise PermissionError("Wisdom knowledge allowlist does not permit retention")
        async with stdio_client(StdioServerParameters(
            command=entry["command"], args=entry["args"], env=env,
        )) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            loop = asyncio.get_running_loop()

            async def invoke(name: str, arguments: dict) -> dict:
                response = await session.call_tool(name, arguments)
                text = "\n".join(c.text for c in response.content if hasattr(c, "text"))
                if response.isError:
                    error = text
                    expected_id = arguments.get("object_id", "")
                    missing = any(repr(prefix + expected_id) in error for prefix in (
                        "", "questions:", "gaps:",
                    ))
                    if name == "knowledge_get" and expected_id and missing:
                        return {"_missing": True}
                    raise RuntimeError("Knowledge MCP retention failed: " + error)
                value = response.structuredContent
                if value is None:
                    value = json.loads(text)
                while isinstance(value, dict) and set(value) == {"result"}:
                    value = value["result"]
                    if isinstance(value, str):
                        value = json.loads(value)
                if not isinstance(value, dict) or "error" in value:
                    raise RuntimeError("Knowledge MCP did not return a successful receipt")
                return value

            def call(name: str, arguments: dict) -> dict:
                return asyncio.run_coroutine_threadsafe(invoke(name, arguments), loop).result(25)

            return await asyncio.to_thread(retain_records, result, task, call)

    return run_sync(lambda: asyncio.wait_for(run(), timeout=150))
