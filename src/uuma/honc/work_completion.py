"""Authenticated user completion reports -> existing Graph execution receipt protocol.

Only the Hermes host calls this coordinator. Model-generated text is never an input.
An unqualified explicit completion is a user attestation, not an artifact verification.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from typing import Any

import httpx

from .graph_client import GraphExecutionClient
from .models import (
    AssessmentResult,
    CompletionAssessment,
    ExecutionEvent,
    OutboxItem,
    TaskSnapshot,
    TrustedInput,
    canonical_json,
)
from .store import HoncStore

PROTOCOL = "honc_auto_completion_v1"


def is_completion_report(text: str) -> bool:
    if re.search(
        r'["「『“][^"」』”]*(?:完成|做完|搞定|\bdone\b|\bfinished\b)[^"」』”]*["」』”]',
        text,
        re.IGNORECASE,
    ):
        return False
    if re.search(
        r"[？?]|^(?:如果|假设|例如|比如|引用|他说|她说|别人|有人|明天|后天|[\"「『])|"
        r"还没|没有|(?:没|未|不).{0,4}(?:完成|做完|搞定|做好|通过)|尚未|只完成|只做|部分|一半|初稿|草稿|差一点|还差|还要|还需要|失败|报错|未达标|"
        r"计划|打算|准备|不要|好像|差不多|可能|大概|以为|是否|应该.{0,8}完成|别.{0,4}(?:勾|标|记)|不.{0,3}(?:算|标|勾)|"
        r"\b(?:if|suppose|tomorrow|not|partial|plan|will|he said|she said)\b",
        text,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"完成(?:了)?|做完(?:了)?|搞定(?:了)?|做好了|验收通过|"
            r"\b(?:completed|finished|done)\b",
            text,
            re.IGNORECASE,
        )
    )


class WorkCompletion:
    def __init__(self, store: HoncStore, graph: GraphExecutionClient) -> None:
        self.store, self.graph = store, graph
        self.lock = threading.RLock()

    def report(
        self,
        *,
        text: str,
        owner_id: str,
        session_id: str,
        source_event_id: str,
        input_kind: str = "text",
    ) -> dict[str, Any] | None:
        """Arguments come exclusively from verified host transport identity and original text."""
        if not all((owner_id, session_id, source_event_id)):
            raise PermissionError("Authenticated transport identity is required")
        if input_kind not in {"text", "voice_transcript"}:
            raise PermissionError("Unsupported authenticated message type")
        if input_kind == "voice_transcript":
            text = text.strip()
            if len(text) > 1 and text[0] == text[-1] == '"':
                text = text[1:-1]
        if not is_completion_report(text):
            return None
        if not re.search(r"任务|工作|\btask\b|Graph", text, re.IGNORECASE):
            with self.store.connect() as connection:
                life_exists = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='life_objects'"
                ).fetchone()
                if life_exists:
                    rows = connection.execute(
                        "SELECT r.payload_json FROM life_objects o JOIN life_revisions r "
                        "ON o.object_id=r.object_id AND o.head_revision=r.revision "
                        "WHERE o.owner_id=? AND o.kind='habit_definition'",
                        (owner_id,),
                    ).fetchall()
                    for row in rows:
                        definition = json.loads(row[0])["definition"]
                        names = [definition["name"], *definition.get("aliases", [])]
                        if any(name.casefold() in text.casefold() for name in names):
                            return None
        with self.lock:
            try:
                return self._report(text, owner_id, session_id, source_event_id)
            except (httpx.HTTPError, OSError, ValueError) as exc:
                return {
                    "status": "UNAVAILABLE",
                    "graph_verified": False,
                    "error_kind": type(exc).__name__,
                    "reply": "收到你的完成报告，但 Project Graph 暂时无法核实，尚未确认勾选成功。",
                }

    def _report(self, text: str, owner: str, session: str, source: str) -> dict[str, Any] | None:
        health = self.graph.get_health()
        if not health.get("database_id") or not self.graph.database_id:
            raise ValueError("Graph identity is unavailable")
        graph = self.graph.get_graph()
        nodes = {node["id"]: node for node in graph["nodes"]}
        # Exact IDs/titles only. Never match a shared keyword such as 'tests'.
        direct = [
            n
            for n in nodes.values()
            if re.search(
                r"(?<![A-Za-z0-9_-])" + re.escape(n["id"]) + r"(?![A-Za-z0-9_-])",
                text,
                re.IGNORECASE,
            )
        ]
        matches = direct or [
            n
            for n in nodes.values()
            if len(n.get("title", "")) >= 2 and n["title"].casefold() in text.casefold()
        ]
        if not matches and re.search(
            r"(?:这个|这项|当前)(?:任务|工作)(?:已经|今天|现在)?(?:完成|做完)|"
            r"(?:完成|做完)(?:了)?(?:当前|这个|这项)(?:任务|工作)|\bthis task\b",
            text,
        ):
            active = self.store.get_active_round(owner)
            if active and active.task_id in nodes:
                matches = [nodes[active.task_id]]
        if not matches and not re.search(
            r"任务|工作|这(?:个|项)|\btask\b|Graph", text, re.IGNORECASE
        ):
            return None
        if len(matches) != 1:
            return {
                "status": "NEEDS_TARGET",
                "graph_verified": False,
                "candidates": [{"id": n["id"], "title": n["title"]} for n in matches[:10]],
                "reply": "请说明完成的是哪项任务（任务名称或ID）。"
                + (
                    "找到多个候选：" + "；".join(n["title"] for n in matches[:5]) if matches else ""
                ),
            }
        node = matches[0]
        report = self.store.record_trusted_input(
            TrustedInput(
                user_id=owner,
                profile="honc",
                session_id=session,
                entrypoint="hermes_authenticated_completion",
                source_receipt_id=source,
                raw_content=text,
                metadata={"evidence_kind": "user_completion_report"},
            )
        )
        operation = (
            "hc-" + hashlib.sha256(f"{owner}:{source}:{node['id']}".encode()).hexdigest()[:32]
        )
        prior = self.store.get_outbox(operation)
        if prior:
            return self.reconcile(prior)
        role = node.get("portfolio_role")
        current, seen = node, set()
        while not role and current.get("parent_id") in nodes:
            if current["id"] in seen:
                raise ValueError("Graph hierarchy cycle")
            seen.add(current["id"])
            current = nodes[current["parent_id"]]
            role = current.get("portfolio_role")
        blocked = (
            node.get("node_kind") != "WORK"
            or node.get("work_type") != "ACTION"
            or node.get("is_proposed", False)
            or node.get("archived", False)
            or node.get("status") in {"REVIEW", "CANCELLED", "SUPERSEDED"}
            or role == "PARKED"
            or any(
                e["relation"] == "contains" and e["source_id"] == node["id"] for e in graph["edges"]
            )
        )
        # One source-stamped local fact regardless of whether completion can be applied.
        with self.store.connect() as connection:
            recorded = connection.execute(
                "SELECT 1 FROM execution_events WHERE trusted_input_id=? AND task_id=?",
                (report.input_id, node["id"]),
            ).fetchone()
        if not recorded:
            self.store.record_execution_event(
                ExecutionEvent(
                    event_type="OUTCOME",
                    trusted_input_id=report.input_id,
                    task_id=node["id"],
                    outcome=text,
                    payload={"evidence_kind": "user_completion_report"},
                )
            )
        if blocked:
            return {
                "status": "REVIEW_REQUIRED",
                "graph_verified": False,
                "reply": f"已记录「{node['title']}」的完成报告；该项不是可自动勾选的普通任务，需要复核。",
            }
        if node.get("status") == "DONE":
            return {
                "status": "ALREADY_DONE",
                "graph_verified": True,
                "task_id": node["id"],
                "reply": f"Project Graph 中「{node['title']}」已经是完成状态，已核实。",
            }
        criteria = str(node.get("done_when") or "").strip()
        if not criteria:
            return {
                "status": "NEEDS_CRITERIA",
                "graph_verified": False,
                "reply": f"已记录「{node['title']}」的完成报告，但 Graph 里没有完成标准，暂未勾选。",
            }
        self.store.save_task_snapshot(
            TaskSnapshot(
                graph_database_id=self.graph.database_id,
                node_id=node["id"],
                portfolio_role=role,
                graph_version=graph["graph_version"],
                task_status=node["status"],
                title=node["title"],
                done_when=criteria,
            )
        )
        assessment = self.store.save_assessment(
            CompletionAssessment(
                task_id=node["id"],
                criteria_snapshot=criteria,
                satisfied_items=[],
                evidence="用户明确报告此任务已完成（用户自述，未独立检验产物）：" + text,
                trusted_input_id=report.input_id,
                result=AssessmentResult.USER_REPORTED,
            )
        )
        payload = {
            "operation_id": operation,
            "node_id": node["id"],
            "action": "done",
            "expected_graph_version": graph["graph_version"],
            "decision_origin": {
                "trusted_input_id": report.input_id,
                "user_id": owner,
                "channel": "hermes_authenticated_completion",
                "source_event_id": source,
                "assessment_id": assessment.assessment_id,
                "evidence_kind": "user_completion_report",
                "done_when": criteria,
                "criteria_configured": bool(criteria),
            },
        }
        envelope = {
            "protocol": PROTOCOL,
            "database_id": self.graph.database_id,
            "title": node["title"],
            "payload": payload,
        }
        item = self.store.enqueue_outbox(
            OutboxItem(
                operation_id=operation,
                content_digest=hashlib.sha256(canonical_json(payload).encode()).hexdigest(),
                preceding_version=graph["graph_version"],
                receipt_json=canonical_json(envelope),
            )
        )
        return self.reconcile(item)

    def reconcile(self, item: OutboxItem) -> dict[str, Any]:
        """Retry the original operation, never change identity/version after uncertainty."""
        envelope = json.loads(item.receipt_json or "{}")
        if envelope.get("protocol") != PROTOCOL:
            raise ValueError("Not an authenticated completion operation")
        if envelope["database_id"] != self.graph.database_id:
            raise ValueError("Completion belongs to a different Graph database")
        payload = envelope["payload"]
        operation, node_id = payload["operation_id"], payload["node_id"]
        try:
            receipt = self.graph.get_receipt(operation)
            if not receipt:
                if item.status in {"CONFLICT", "NEEDS_HUMAN"}:
                    return {
                        "status": "REVIEW_REQUIRED",
                        "graph_verified": False,
                        "operation_id": operation,
                        "reply": f"「{envelope['title']}」的同步需要重新核对，尚未确认勾选成功。",
                    }
                receipt = self.graph.submit_verified_completion(payload)
            record = receipt.get("receipt", {})
            valid = (
                record.get("operation_id") == operation
                and record.get("node_id") == node_id
                and record.get("action") == "done"
                and not record.get("undone_at")
                and record.get("state_after", {}).get("status") == "DONE"
                and record.get("decision_origin") == payload["decision_origin"]
            )
            node = self.graph.get_node(node_id)
            if not valid or node.get("status") != "DONE":
                raise ValueError("Graph receipt and current node did not confirm completion")
            envelope["verified_receipt"] = receipt
            self.store.update_outbox_status(
                operation, "SUCCEEDED", receipt_json=canonical_json(envelope)
            )
            return {
                "status": "VERIFIED",
                "graph_verified": True,
                "task_id": node_id,
                "operation_id": operation,
                "reply": f"已将 Project Graph 的「{envelope['title']}」勾选完成，并已读回确认。",
            }
        except (httpx.HTTPError, OSError, ValueError) as exc:
            state = "FAILED"
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {409, 412}:
                state = "CONFLICT"
            elif isinstance(exc, ValueError):
                state = "NEEDS_HUMAN"
            self.store.update_outbox_status(operation, state, error=type(exc).__name__)
            return {
                "status": "PENDING_VERIFICATION",
                "graph_verified": False,
                "operation_id": operation,
                "reply": f"已记录「{envelope['title']}」的完成报告，Graph 勾选结果尚待确认；会按原回执对账。",
            }

    def reconcile_pending(self, limit: int = 5) -> dict[str, int]:
        """Drain only this protocol's existing operations; never infer new completions."""
        pending = [
            item
            for item in self.store.list_pending_outbox(limit=100)
            if json.loads(item.receipt_json or "{}").get("protocol") == PROTOCOL
        ][:limit]
        counts = {"checked": len(pending), "verified": 0, "pending": len(pending)}
        if not pending:
            return counts
        try:
            self.graph.get_health()
            for item in pending:
                if self.reconcile(item)["graph_verified"]:
                    counts["verified"] += 1
                    counts["pending"] -= 1
        except (httpx.HTTPError, OSError, ValueError):
            # Preserve the original pending operation. A future tick can query its receipt.
            pass
        return counts
