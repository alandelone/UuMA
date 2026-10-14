"""Optional semantic tools for the existing honc MCP server.

No global server, command entry point, environment identity or live database is
created here. A trusted inbound adapter must supply a request-scoped LifeService
when the host registers these tools at a new session boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field, StrictInt

from .life_models import (
    AnchorRecordRequest,
    BodyRecordRequest,
    DiaryRecordRequest,
    HabitCheckinRequest,
    HabitConfigureRequest,
    RecordCorrectionRequest,
    SettingsUpdateRequest,
    ToolResult,
)
from .life_service import LifeService


def register_life_tools(
    server: FastMCP,
    service_provider: Callable[[], LifeService],
    context_provider: Callable[[str | None], LifeService] | None = None,
) -> None:
    """Register semantic operations; adapter ingestion/binding cannot become tools."""

    def scoped(context_ref):
        return context_provider(context_ref) if context_provider is not None else service_provider()

    @server.tool()
    def honc_get_life_context(
        habit_id: str | None = None,
        habit_name: str | None = None,
        business_date: date | None = None,
        context_ref: str | None = None,
    ) -> ToolResult:
        """Read this owner's settings, habit revisions and current-message operation grants.

        Missing matches never create habits. Only returned request_refs can authorize writes.
        Settings revision zero means defaults have not yet been persisted.
        Overview is compact. For check-in call again with habit_id or exact habit_name
        to get only that habit's occurrence IDs. Set business_date for yesterday/backfill.
        Copy the selected occurrence's instance_id and habit_revision; never ask again
        when the user already named the time/meal. Do not search sessions or MCP prompts.
        """
        return scoped(context_ref).get_context(
            habit_id=habit_id, habit_name=habit_name, business_date=business_date, compact=True
        )

    @server.tool()
    def honc_configure_habit(
        request: HabitConfigureRequest, context_ref: str | None = None
    ) -> ToolResult:
        """Create, patch, pause, resume or retire a habit using its current-message grant.

        Existing habits require expected_revision; patches retain unspecified fields.
        Retirement keeps history. Creation without reminder config adds no schedule.
        """
        return scoped(context_ref).configure_habit(request)

    @server.tool()
    def honc_update_life_settings(
        request: SettingsUpdateRequest, context_ref: str | None = None
    ) -> ToolResult:
        """Patch settings with expected_revision and a current-message grant.

        Defaults: wake 08:00, bedtime 21:30, one reminder. Importance never adds sends.
        Body follow-up, nightly chasing, owner and recipient changes are forbidden.
        """
        return scoped(context_ref).update_settings(request)

    @server.tool()
    def honc_record_habit(
        request: HabitCheckinRequest, context_ref: str | None = None
    ) -> ToolResult:
        """Atomically record 1-8 explicit habit reports against current habit revisions.

        Use exact source quotes and units. Unknown quantity/time stays unknown.
        Only verified owner/habit/date occurrence IDs bind completion; focus rounds stay intact.
        """
        return scoped(context_ref).record_habit(request)

    @server.tool()
    def honc_record_body(request: BodyRecordRequest, context_ref: str | None = None) -> ToolResult:
        """Save positive or negative body observations using the user's original words.

        Leave unreported details null. No diagnoses, follow-up questions or reminders are created.
        Related records must belong to this owner. A committed receipt confirms the write.
        """
        return scoped(context_ref).record_body(request)

    @server.tool()
    def honc_save_diary(request: DiaryRecordRequest, context_ref: str | None = None) -> ToolResult:
        """Save original diary text and optional date/links; preserve unknown dates.

        The unique diary habit is recorded atomically. Do not submit a second habit check-in.
        """
        return scoped(context_ref).save_diary(request)

    @server.tool()
    def honc_correct_life_record(
        request: RecordCorrectionRequest, context_ref: str | None = None
    ) -> ToolResult:
        """Append a correction or void to an explicit fact ID at expected_revision.

        Original versions remain in audit history. Replacement fields must match the fact kind.
        Habit quantities retain their original unit; configuration uses configure_habit instead.
        """
        return scoped(context_ref).correct_record(request)

    @server.tool()
    def honc_record_anchor(
        request: AnchorRecordRequest, context_ref: str | None = None
    ) -> ToolResult:
        """Record explicit current wake/day start/bedtime and advance the same unsent occurrence.

        Future plans, hypothetical statements and automatic ticks are not factual anchors.
        A recorded anchor or reserved reminder is never claimed as a delivered notification.
        """
        return scoped(context_ref).record_anchor(request)

    @server.tool()
    def honc_get_life_operation(
        operation_id: str | None = None,
        request_ref: str | None = None,
        context_ref: str | None = None,
    ) -> ToolResult:
        """Read one persisted write receipt in the current owner's scope.

        Supply exactly one ID. After UNKNOWN, look up this receipt; do not blindly re-submit.
        An absent receipt alone does not establish that an uncertain write failed.
        """
        return scoped(context_ref).get_operation(operation_id=operation_id, request_ref=request_ref)

    @server.tool()
    def honc_get_life_history(
        record_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        view: Literal["effective", "audit"] = "effective",
        limit: Annotated[StrictInt, Field(ge=1, le=100)] = 20,
        offset: Annotated[StrictInt, Field(ge=0)] = 0,
        cursor: str | None = None,
        kinds: list[Literal["habit", "body", "diary", "anchor", "activity"]] | None = None,
        habit_id: str | None = None,
        context_ref: str | None = None,
    ) -> ToolResult:
        """Read an explicit fact or date range, scoped to this owner, with bounded pagination.

        Effective excludes voids; audit retains all revisions. Unknown occurrence dates
        use the marked recorded-date range rather than pretending the event happened today.
        Continue with the signed cursor and unchanged filters for a stable version snapshot.
        """
        return scoped(context_ref).get_history(
            record_id=record_id,
            start_date=start_date,
            end_date=end_date,
            view=view,
            limit=limit,
            offset=offset,
            cursor=cursor,
            kinds=tuple(kinds)
            if kinds is not None
            else ("habit", "body", "diary", "anchor", "activity"),
            habit_id=habit_id,
        )
