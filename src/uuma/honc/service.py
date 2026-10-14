import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from .graph_client import GraphExecutionClient
from .models import (
    ActualKind,
    AssessmentGranularity,
    AssessmentResult,
    CompletionAssessment,
    DailyReport,
    EventType,
    ExecutionEvent,
    HabitDefinition,
    OutboxItem,
    OutboxStatus,
    Round,
    RoundSegment,
    RoundStatus,
    TargetSystem,
    TrustedInput,
    canonical_json,
    compute_digest,
    get_timezone,
)
from .store import HoncStore

logger = logging.getLogger(__name__)


class HoncService:
    """Core service coordinating execution ledger, rounds, assessments, and outbox."""

    def __init__(
        self,
        store: HoncStore,
        graph_client: GraphExecutionClient | None = None,
        default_user_id: str = "default_user",
        default_profile: str = "honc",
    ) -> None:
        self.store = store
        self.graph_client = graph_client
        self.default_user_id = default_user_id
        self.default_profile = default_profile

    # -------------------------------------------------------------------------
    # Status & Context
    # -------------------------------------------------------------------------

    def get_status(self, user_id: str | None = None) -> dict[str, Any]:
        uid = user_id or self.default_user_id
        active_round = self.store.get_active_round(uid)
        round_info = None
        if active_round:
            segments = self.store.get_round_segments(active_round.round_id)
            duration = self.store.calculate_round_duration(active_round.round_id)
            active_segment = next((s for s in segments if s.ended_at is None), None)
            round_info = {
                "round_id": active_round.round_id,
                "task_id": active_round.task_id,
                "target_outcome": active_round.target_outcome,
                "tiny_step": active_round.tiny_step,
                "mode": active_round.mode,
                "status": active_round.status,
                "revision": active_round.revision,
                "observed_duration_seconds": duration,
                "active_segment": (
                    {
                        "segment_id": active_segment.segment_id,
                        "started_at": active_segment.started_at,
                        "time_source": active_segment.time_source,
                    }
                    if active_segment
                    else None
                ),
            }

        pending_outbox = self.store.list_pending_outbox(limit=10)
        recent_assessments = self.store.list_assessments(limit=5)

        return {
            "user_id": uid,
            "database_path": str(self.store.path),
            "active_round": round_info,
            "pending_outbox_count": len(pending_outbox),
            "pending_outbox": [
                {
                    "operation_id": o.operation_id,
                    "target_system": o.target_system,
                    "status": o.status,
                    "retry_count": o.retry_count,
                    "last_error": o.last_error,
                }
                for o in pending_outbox
            ],
            "recent_assessments": [
                {
                    "assessment_id": a.assessment_id,
                    "task_id": a.task_id,
                    "result": a.result,
                    "created_at": a.created_at,
                }
                for a in recent_assessments
            ],
        }

    def get_context(self, task_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        uid = user_id or self.default_user_id
        active_round = self.store.get_active_round(uid)
        recent_events = self.store.list_events(task_id=task_id, limit=10)
        habits = self.store.list_habits()

        task_snapshot_data = None
        if task_id:
            # Check local snapshot or fetch from graph if available
            snapshot = None
            if self.graph_client and self.graph_client.database_id:
                snapshot = self.store.get_latest_task_snapshot(
                    self.graph_client.database_id, task_id
                )
            if not snapshot:
                # Try finding any snapshot matching task_id
                with self.store.connect() as conn:
                    cur = conn.execute(
                        "SELECT snapshot_id FROM task_snapshots WHERE node_id = ? "
                        "ORDER BY created_at DESC LIMIT 1",
                        (task_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        snapshot = self.store.get_task_snapshot(row[0])

            if snapshot:
                task_snapshot_data = {
                    "node_id": snapshot.node_id,
                    "title": snapshot.title,
                    "task_status": snapshot.task_status,
                    "portfolio_role": snapshot.portfolio_role,
                    "done_when": snapshot.done_when,
                    "graph_version": snapshot.graph_version,
                }

        latest_next = next((e.next_step for e in recent_events if e.next_step), None)

        return {
            "user_id": uid,
            "task_id": task_id,
            "task_snapshot": task_snapshot_data,
            "active_round": (
                {
                    "round_id": active_round.round_id,
                    "target_outcome": active_round.target_outcome,
                    "tiny_step": active_round.tiny_step,
                    "status": active_round.status,
                }
                if active_round
                else None
            ),
            "current_next": latest_next,
            "recent_events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "occurred_at": e.occurred_at,
                    "outcome": e.outcome,
                    "next_step": e.next_step,
                    "blocker": e.blocker,
                    "state": e.state,
                }
                for e in recent_events
            ],
            "habits": [{"habit_id": h.habit_id, "name": h.name} for h in habits],
        }

    # -------------------------------------------------------------------------
    # Record Execution
    # -------------------------------------------------------------------------

    def record_execution(
        self,
        raw_content: str,
        user_id: str | None = None,
        entrypoint: str = "hermes_local",
        task_id: str | None = None,
        round_id: str | None = None,
        habit_id: str | None = None,
        outcome: str | None = None,
        next_step: str | None = None,
        blocker: str | None = None,
        state: str | None = None,
        actual_kind: str = ActualKind.UNKNOWN,
        actual_duration_seconds: int | None = None,
        occurred_at: str | None = None,
        source_receipt_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record an execution event backed by a deduplicated trusted user input."""
        uid = user_id or self.default_user_id
        now_iso = datetime.now(UTC).isoformat()
        actual_time = occurred_at or now_iso

        # 1. Trusted input deduplication
        inp = TrustedInput(
            user_id=uid,
            entrypoint=entrypoint,
            profile=self.default_profile,
            source_receipt_id=source_receipt_id,
            raw_content=raw_content,
            received_at=now_iso,
            metadata=metadata or {},
        )
        saved_input = self.store.record_trusted_input(inp)

        # 2. Unknown duration enforcement: never invent numbers if unspecified
        if actual_duration_seconds is None:
            actual_kind = ActualKind.UNKNOWN

        # 3. Determine event type
        is_backfill = bool(occurred_at and occurred_at[:10] != now_iso[:10])
        if habit_id:
            event_type = EventType.HABIT_TICK
        elif is_backfill:
            event_type = EventType.BACKFILL
        elif outcome:
            event_type = EventType.OUTCOME
        elif state and not outcome and not next_step:
            event_type = EventType.STATE_CHANGE
        else:
            event_type = EventType.PROGRESS

        event = ExecutionEvent(
            event_type=event_type,
            occurred_at=actual_time,
            recorded_at=now_iso,
            timezone="Asia/Kuala_Lumpur",
            trusted_input_id=saved_input.input_id,
            task_id=task_id,
            round_id=round_id,
            habit_id=habit_id,
            outcome=outcome,
            next_step=next_step,
            blocker=blocker,
            state=state,
            actual_kind=actual_kind,
            actual_duration_seconds=actual_duration_seconds,
            payload={"raw_content": raw_content},
        )
        saved_event = self.store.record_execution_event(event)

        return {
            "record_id": saved_event.event_id,
            "round_id": round_id,
            "assessment_status": "NONE",
            "graph_update_status": "NOT_REQUESTED",
            "projection_status": "PENDING_NOTION",
            "receipt_refs": {
                "input_id": saved_input.input_id,
                "event_id": saved_event.event_id,
            },
            "next_required_action": "NONE",
        }

    # -------------------------------------------------------------------------
    # Round Lifecycle Control
    # -------------------------------------------------------------------------

    def control_round(
        self,
        action: str,
        user_id: str | None = None,
        round_id: str | None = None,
        expected_revision: int | None = None,
        task_id: str | None = None,
        target_outcome: str = "",
        tiny_step: str = "",
        mode: str = "Focus",
        timer_budget_minutes: int = 25,
        criteria_snapshot: str | None = None,
        interruption_reason: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        """Control round lifecycle: prepare, start, pause, resume, end, cancel."""
        uid = user_id or self.default_user_id
        now_iso = datetime.now(UTC).isoformat()
        act = action.lower()

        if act == "prepare":
            if not target_outcome or not tiny_step:
                raise ValueError(
                    "Both target_outcome (果象) and tiny_step (小笨事) are required to prepare a round."
                )
            new_round = Round(
                user_id=uid,
                task_id=task_id,
                target_outcome=target_outcome,
                tiny_step=tiny_step,
                mode=mode,
                timer_budget_minutes=timer_budget_minutes,
                criteria_snapshot=criteria_snapshot,
                status=RoundStatus.PREPARED,
                revision=1,
            )
            created = self.store.create_round(new_round)
            return {
                "record_id": None,
                "round_id": created.round_id,
                "status": created.status,
                "revision": created.revision,
                "assessment_status": "NONE",
                "graph_update_status": "NONE",
                "projection_status": "READY",
                "receipt_refs": {"round_id": created.round_id},
                "next_required_action": "START_ROUND",
            }

        target_round_id = round_id
        if not target_round_id:
            active = self.store.get_active_round(uid)
            if not active:
                raise ValueError(f"No active round found for user {uid} to perform action '{act}'.")
            target_round_id = active.round_id

        current_round = self.store.get_round(target_round_id)
        if not current_round:
            raise ValueError(f"Round {target_round_id} does not exist.")

        rev = expected_revision if expected_revision is not None else current_round.revision

        if act == "start":
            if current_round.status not in (RoundStatus.PREPARED, RoundStatus.PAUSED):
                raise ValueError(f"Cannot start round in status {current_round.status}.")
            updated = self.store.update_round_status(target_round_id, rev, RoundStatus.RUNNING)
            # Open new active segment
            self.store.add_round_segment(
                RoundSegment(
                    round_id=target_round_id,
                    started_at=now_iso,
                    time_source="timer",
                )
            )
            # If graph client exists and task_id linked, submit focus start
            if self.graph_client and updated.task_id:
                try:
                    self.graph_client.submit_focus_event(
                        interval_id=f"honc-round-{target_round_id}",
                        event_type="start",
                        node_id=updated.task_id,
                        timestamp=now_iso,
                    )
                except (httpx.HTTPError, OSError) as exc:
                    logger.warning("Focus event start sync failed: %s", exc)

            return {
                "record_id": None,
                "round_id": updated.round_id,
                "status": updated.status,
                "revision": updated.revision,
                "assessment_status": "NONE",
                "graph_update_status": "FOCUS_STARTED" if updated.task_id else "NONE",
                "projection_status": "ACTIVE_TIMER",
                "receipt_refs": {"round_id": updated.round_id},
                "next_required_action": "FOCUS_WORK",
            }

        elif act == "pause":
            if current_round.status != RoundStatus.RUNNING:
                raise ValueError(f"Cannot pause round in status {current_round.status}.")
            updated = self.store.update_round_status(target_round_id, rev, RoundStatus.PAUSED)
            self.store.close_active_round_segment(
                target_round_id, ended_at=now_iso, reason=interruption_reason or "user_pause"
            )
            return {
                "record_id": None,
                "round_id": updated.round_id,
                "status": updated.status,
                "revision": updated.revision,
                "assessment_status": "NONE",
                "graph_update_status": "NONE",
                "projection_status": "PAUSED",
                "receipt_refs": {"round_id": updated.round_id},
                "next_required_action": "RESUME_OR_END",
            }

        elif act == "resume":
            if current_round.status != RoundStatus.PAUSED:
                raise ValueError(f"Cannot resume round in status {current_round.status}.")
            updated = self.store.update_round_status(target_round_id, rev, RoundStatus.RUNNING)
            self.store.add_round_segment(
                RoundSegment(
                    round_id=target_round_id,
                    started_at=now_iso,
                    time_source="timer",
                )
            )
            return {
                "record_id": None,
                "round_id": updated.round_id,
                "status": updated.status,
                "revision": updated.revision,
                "assessment_status": "NONE",
                "graph_update_status": "NONE",
                "projection_status": "ACTIVE_TIMER",
                "receipt_refs": {"round_id": updated.round_id},
                "next_required_action": "FOCUS_WORK",
            }

        elif act == "end":
            self.store.close_active_round_segment(
                target_round_id, ended_at=now_iso, reason=interruption_reason
            )
            total_duration = self.store.calculate_round_duration(target_round_id)

            # If outcome provided, close immediately, otherwise move to AWAITING_CHECK
            target_status = RoundStatus.CLOSED if outcome else RoundStatus.AWAITING_CHECK
            closed_at = now_iso if outcome else None
            updated = self.store.update_round_status(
                target_round_id, rev, target_status, closed_at=closed_at
            )

            record_id = None
            if outcome:
                event = self.store.record_execution_event(
                    ExecutionEvent(
                        event_type=EventType.OUTCOME,
                        occurred_at=now_iso,
                        recorded_at=now_iso,
                        task_id=updated.task_id,
                        round_id=target_round_id,
                        outcome=outcome,
                        actual_kind=ActualKind.TIMED,
                        actual_duration_seconds=total_duration,
                    )
                )
                record_id = event.event_id

            # Sync focus close to graph if available
            if self.graph_client and updated.task_id:
                try:
                    self.graph_client.submit_focus_event(
                        interval_id=f"honc-round-{target_round_id}",
                        event_type="close",
                        node_id=updated.task_id,
                        timestamp=now_iso,
                        duration_seconds=total_duration,
                    )
                except (httpx.HTTPError, OSError) as exc:
                    logger.warning("Focus event close sync failed: %s", exc)

            return {
                "record_id": record_id,
                "round_id": updated.round_id,
                "status": updated.status,
                "revision": updated.revision,
                "observed_duration_seconds": total_duration,
                "assessment_status": "CHECK_REQUIRED" if not outcome else "OUTCOME_RECORDED",
                "graph_update_status": "FOCUS_CLOSED" if updated.task_id else "NONE",
                "projection_status": "ROUND_ENDED",
                "receipt_refs": {"round_id": updated.round_id},
                "next_required_action": "RECORD_OUTCOME_NEXT"
                if not outcome
                else "ASSESS_COMPLETION",
            }

        elif act == "cancel":
            self.store.close_active_round_segment(
                target_round_id, ended_at=now_iso, reason="cancelled"
            )
            updated = self.store.update_round_status(
                target_round_id, rev, RoundStatus.CANCELLED, closed_at=now_iso
            )
            return {
                "record_id": None,
                "round_id": updated.round_id,
                "status": updated.status,
                "revision": updated.revision,
                "assessment_status": "NONE",
                "graph_update_status": "NONE",
                "projection_status": "CANCELLED",
                "receipt_refs": {"round_id": updated.round_id},
                "next_required_action": "NONE",
            }

        else:
            raise ValueError(f"Unknown round control action: {action}")

    # -------------------------------------------------------------------------
    # Habit Check
    # -------------------------------------------------------------------------

    def check_habit(
        self,
        habit_id: str,
        user_id: str | None = None,
        quantity: float = 1.0,
        user_report: str = "",
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        uid = user_id or self.default_user_id
        now_iso = datetime.now(UTC).isoformat()
        actual_time = occurred_at or now_iso

        habit = self.store.get_habit(habit_id)
        if not habit:
            # Auto-register if simple habit
            habit = self.store.register_habit(
                HabitDefinition(
                    habit_id=habit_id,
                    name=habit_id.replace("_", " ").title(),
                )
            )

        inp = self.store.record_trusted_input(
            TrustedInput(
                user_id=uid,
                entrypoint="hermes_local",
                raw_content=user_report or f"Habit {habit_id} checked: {quantity}",
            )
        )

        event = self.store.record_execution_event(
            ExecutionEvent(
                event_type=EventType.HABIT_TICK,
                occurred_at=actual_time,
                recorded_at=now_iso,
                trusted_input_id=inp.input_id,
                habit_id=habit_id,
                outcome=f"Checked {habit.name} (+{quantity} {habit.unit or 'times'})",
                payload={"quantity": quantity, "habit_name": habit.name},
            )
        )

        return {
            "record_id": event.event_id,
            "round_id": None,
            "habit_id": habit_id,
            "assessment_status": "NONE",
            "graph_update_status": "NONE",
            "projection_status": "PENDING_DAILYSTATE",
            "receipt_refs": {"event_id": event.event_id, "input_id": inp.input_id},
            "next_required_action": "NONE",
        }

    # -------------------------------------------------------------------------
    # Completion Assessment & Application
    # -------------------------------------------------------------------------

    def assess_completion(
        self,
        task_id: str,
        evidence: str,
        criteria_override: str | None = None,
        trusted_input_id: str | None = None,
    ) -> dict[str, Any]:
        """Assess whether evidence satisfies the task done_when criteria."""
        criteria_text = criteria_override or ""
        if not criteria_text:
            # Attempt to find snapshot
            with self.store.connect() as conn:
                cur = conn.execute(
                    "SELECT done_when FROM task_snapshots WHERE node_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                )
                row = cur.fetchone()
                if row and row["done_when"]:
                    criteria_text = row["done_when"]

        if not criteria_text.strip():
            # Missing criteria: cannot declare satisfied
            assessment = self.store.save_assessment(
                CompletionAssessment(
                    granularity=AssessmentGranularity.TASK,
                    task_id=task_id,
                    criteria_snapshot="",
                    satisfied_items=[],
                    missing_items=["缺少任务验收标准（done_when）"],
                    evidence=evidence,
                    trusted_input_id=trusted_input_id,
                    result=AssessmentResult.INSUFFICIENT,
                )
            )
            return {
                "assessment_id": assessment.assessment_id,
                "task_id": task_id,
                "result": assessment.result,
                "satisfied_items": [],
                "missing_items": assessment.missing_items,
                "evidence": evidence,
                "can_apply": False,
            }

        # Parse criteria into individual items (by lines / semicolons / numbers)
        raw_items = [
            line.strip().lstrip("-*1234567890. ")
            for line in criteria_text.replace("；", "\n").replace(";", "\n").splitlines()
            if line.strip()
        ]
        criteria_items = raw_items if raw_items else [criteria_text.strip()]

        satisfied: list[str] = []
        missing: list[str] = []

        # Check evidence against criteria items
        evidence_lower = evidence.lower()
        for item in criteria_items:
            # Heuristic token overlap / substring
            key_words = [
                w for w in item.replace("，", " ").replace("。", " ").split() if len(w) > 1
            ]
            if (
                not key_words
                or item.lower() in evidence_lower
                or any(kw.lower() in evidence_lower for kw in key_words)
            ):
                satisfied.append(item)
            else:
                missing.append(item)

        result = AssessmentResult.SATISFIED if not missing else AssessmentResult.INSUFFICIENT
        assessment = self.store.save_assessment(
            CompletionAssessment(
                granularity=AssessmentGranularity.TASK,
                task_id=task_id,
                criteria_snapshot=criteria_text,
                satisfied_items=satisfied,
                missing_items=missing,
                evidence=evidence,
                trusted_input_id=trusted_input_id,
                result=result,
            )
        )

        return {
            "assessment_id": assessment.assessment_id,
            "task_id": task_id,
            "result": assessment.result,
            "satisfied_items": satisfied,
            "missing_items": missing,
            "evidence": evidence,
            "can_apply": result == AssessmentResult.SATISFIED,
        }

    def apply_completion(
        self,
        task_id: str,
        trusted_input_id: str,
        user_id: str | None = None,
        operation_id: str | None = None,
        assessment_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit a satisfied task completion to Graph with execution receipt."""
        uid = user_id or self.default_user_id
        op_id = operation_id or f"honc-done-{task_id}-{uuid4().hex[:8]}"

        # Verify trusted input exists
        input_record = self.store.get_trusted_input(trusted_input_id)
        if not input_record:
            raise ValueError(f"Trusted input {trusted_input_id} does not exist.")

        # If assessment_id provided, verify satisfied
        if assessment_id:
            ass = self.store.get_assessment(assessment_id)
            if not ass or ass.result != AssessmentResult.SATISFIED:
                raise ValueError(
                    f"Cannot apply completion: assessment {assessment_id} is not SATISFIED."
                )

        payload_material = {
            "task_id": task_id,
            "action": "done",
            "trusted_input_id": trusted_input_id,
            "user_id": uid,
        }
        digest = compute_digest(payload_material)

        # Enqueue in outbox
        outbox_item = OutboxItem(
            target_system=TargetSystem.GRAPH,
            operation_id=op_id,
            content_digest=digest,
            status=OutboxStatus.PENDING,
        )
        self.store.enqueue_outbox(outbox_item)

        # If graph client is available, execute submission
        graph_status = "PENDING_OUTBOX"
        receipt_data = None
        if self.graph_client:
            try:
                decision_origin = {
                    "trusted_input_id": trusted_input_id,
                    "user_id": uid,
                    "channel": input_record.entrypoint,
                }
                resp = self.graph_client.submit_action_decision(
                    operation_id=op_id,
                    node_id=task_id,
                    action="done",
                    decision_origin=decision_origin,
                )
                receipt_data = resp.get("receipt")
                self.store.update_outbox_status(
                    operation_id=op_id,
                    status=OutboxStatus.SUCCEEDED,
                    receipt_json=canonical_json(resp),
                )
                graph_status = "SUCCEEDED"
            except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
                self.store.update_outbox_status(
                    operation_id=op_id,
                    status=OutboxStatus.FAILED,
                    error=str(exc),
                )
                graph_status = "FAILED_WILL_RETRY"

        return {
            "record_id": None,
            "round_id": None,
            "task_id": task_id,
            "operation_id": op_id,
            "assessment_status": "SATISFIED",
            "graph_update_status": graph_status,
            "projection_status": "PENDING_NOTION",
            "receipt_refs": {
                "operation_id": op_id,
                "trusted_input_id": trusted_input_id,
                "receipt": receipt_data,
            },
            "next_required_action": "RECONCILE_UPDATES" if graph_status != "SUCCEEDED" else "NONE",
        }

    # -------------------------------------------------------------------------
    # Correction
    # -------------------------------------------------------------------------

    def correct_record(
        self,
        original_event_id: str,
        reason: str,
        user_id: str | None = None,
        corrected_outcome: str | None = None,
        compensating_action: str | None = None,
    ) -> dict[str, Any]:
        """Append an immutable correction event preserving the original event."""
        uid = user_id or self.default_user_id
        original = self.store.get_event(original_event_id)
        if not original:
            raise ValueError(f"Original event {original_event_id} does not exist.")

        now_iso = datetime.now(UTC).isoformat()
        corr_inp = self.store.record_trusted_input(
            TrustedInput(
                user_id=uid,
                entrypoint="hermes_local",
                raw_content=f"Correction for event {original_event_id}: {reason}",
            )
        )

        corr_event = self.store.record_execution_event(
            ExecutionEvent(
                event_type=EventType.CORRECTION,
                occurred_at=now_iso,
                recorded_at=now_iso,
                trusted_input_id=corr_inp.input_id,
                task_id=original.task_id,
                round_id=original.round_id,
                outcome=corrected_outcome or f"Corrected: {reason}",
                correction_ref_id=original_event_id,
                payload={"reason": reason, "original_event": canonical_json(original.payload)},
            )
        )

        # If compensating action requested (e.g. reopen task on graph)
        graph_update_status = "NONE"
        if compensating_action and original.task_id:
            op_id = f"honc-compensate-{original.task_id}-{uuid4().hex[:8]}"
            outbox_item = OutboxItem(
                target_system=TargetSystem.GRAPH,
                operation_id=op_id,
                content_digest=compute_digest(
                    {"task_id": original.task_id, "action": compensating_action}
                ),
                status=OutboxStatus.PENDING,
            )
            self.store.enqueue_outbox(outbox_item)
            if self.graph_client:
                try:
                    self.graph_client.submit_action_decision(
                        operation_id=op_id,
                        node_id=original.task_id,
                        action=compensating_action,
                        decision_origin={
                            "trusted_input_id": corr_inp.input_id,
                            "user_id": uid,
                            "channel": "hermes_local",
                        },
                    )
                    self.store.update_outbox_status(op_id, OutboxStatus.SUCCEEDED)
                    graph_update_status = "COMPENSATED"
                except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
                    self.store.update_outbox_status(op_id, OutboxStatus.FAILED, error=str(exc))
                    graph_update_status = "COMPENSATION_QUEUED"
            else:
                graph_update_status = "COMPENSATION_QUEUED"

        return {
            "record_id": corr_event.event_id,
            "original_record_id": original_event_id,
            "round_id": original.round_id,
            "assessment_status": "CORRECTED",
            "graph_update_status": graph_update_status,
            "projection_status": "PENDING_PROJECTION_UPDATE",
            "receipt_refs": {"correction_event_id": corr_event.event_id},
            "next_required_action": "NONE",
        }

    # -------------------------------------------------------------------------
    # Reporting
    # -------------------------------------------------------------------------

    def get_report(
        self,
        date_str: str | None = None,
        user_id: str | None = None,
        timezone_name: str = "Asia/Kuala_Lumpur",
    ) -> dict[str, Any]:
        uid = user_id or self.default_user_id
        if not date_str:
            tz = get_timezone(timezone_name)
            date_str = datetime.now(tz).strftime("%Y-%m-%d")

        rep: DailyReport = self.store.get_daily_report(uid, date_str, timezone_name)
        return {
            "date": rep.date,
            "user_id": rep.user_id,
            "done_items": rep.done_items,
            "next_items": rep.next_items,
            "blockers": rep.blockers,
            "total_active_seconds": rep.total_active_seconds,
            "active_minutes": round(rep.total_active_seconds / 60, 1),
            "timed_seconds": rep.timed_seconds,
            "reported_seconds": rep.reported_seconds,
            "estimated_seconds": rep.estimated_seconds,
            "rounds_count": rep.rounds_count,
            "habits_summary": rep.habits_summary,
            "pending_outbox_count": rep.pending_outbox_count,
            "unlinked_events_count": rep.unlinked_events_count,
        }

    # -------------------------------------------------------------------------
    # Reconcile Updates
    # -------------------------------------------------------------------------

    def reconcile_updates(self) -> dict[str, Any]:
        """Check pending outbox items and reconcile without fabricating execution events."""
        pending = self.store.list_pending_outbox(limit=10)
        reconciled = 0
        still_pending = 0
        errors = []

        for item in pending:
            if item.target_system == TargetSystem.GRAPH and self.graph_client:
                try:
                    # Query existing receipt first to see if operation already succeeded
                    receipt = self.graph_client.get_receipt(item.operation_id)
                    if receipt:
                        self.store.update_outbox_status(
                            item.operation_id,
                            OutboxStatus.SUCCEEDED,
                            receipt_json=canonical_json(receipt),
                        )
                        reconciled += 1
                        continue
                except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
                    errors.append(f"{item.operation_id}: {exc}")
            still_pending += 1

        return {
            "checked_count": len(pending),
            "reconciled_count": reconciled,
            "still_pending_count": still_pending,
            "errors": errors,
        }
