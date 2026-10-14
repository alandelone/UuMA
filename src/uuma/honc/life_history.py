"""Owner-scoped immutable history snapshots and signed stable keyset cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import date
from typing import Any

from .life_store import LifeStore, canonical


def history(
    store: LifeStore,
    *,
    owner_id: str,
    record_id: str | None,
    start_date: date | None,
    end_date: date | None,
    view: str,
    limit: int,
    offset: int = 0,
    cursor: str | None = None,
    kinds: tuple[str, ...] = ("habit", "body", "diary", "anchor", "activity"),
    habit_id: str | None = None,
) -> dict[str, Any]:
    if view not in {"effective", "audit"} or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Use effective/audit and a limit between 1 and 100")
    if type(offset) is not int or offset < 0:
        raise ValueError("Offset must be a nonnegative integer")
    if not kinds or set(kinds) - {"habit", "body", "diary", "anchor", "activity"}:
        raise ValueError("Unsupported history kind")
    if record_id is None and (start_date is None or end_date is None):
        raise ValueError("Supply a record ID or both range dates")
    if start_date and end_date and start_date > end_date:
        raise ValueError("Range start cannot follow range end")
    query_key = hashlib.sha256(
        canonical(
            (owner_id, record_id, str(start_date), str(end_date), view, sorted(kinds), habit_id)
        ).encode()
    ).hexdigest()
    with store.ledger.connect() as connection:
        key = bytes(
            connection.execute("SELECT value FROM life_history_key WHERE singleton=1").fetchone()[0]
        )
        anchors_exist = bool(
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='life_anchors' AND type='table'"
            ).fetchone()
        )
        legacy_exist = bool(
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='life_legacy_events' AND type='table'"
            ).fetchone()
        )
        if cursor:
            if offset:
                raise ValueError("A cursor cannot be combined with an offset")
            try:
                encoded, signature = cursor.split(".")
                if not hmac.compare_digest(
                    hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest(), signature
                ):
                    raise ValueError("Invalid cursor signature")
                state = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            except (ValueError, json.JSONDecodeError) as error:
                raise ValueError("Invalid or foreign history cursor") from error
            if state["query"] != query_key:
                raise ValueError("Cursor belongs to another owner or query")
        else:
            state = {
                "query": query_key,
                "revision_cutoff": connection.execute(
                    "SELECT COALESCE(MAX(rowid),0) FROM life_revisions"
                ).fetchone()[0],
                "anchor_cutoff": connection.execute(
                    "SELECT COALESCE(MAX(rowid),0) FROM life_anchors"
                ).fetchone()[0]
                if anchors_exist
                else 0,
                "legacy_cutoff": connection.execute(
                    "SELECT COALESCE(MAX(rowid),0) FROM life_legacy_events"
                ).fetchone()[0]
                if legacy_exist
                else 0,
                "after": None,
            }
        conditions = ["o.owner_id=?", "o.kind IN ('habit','body','diary')", "r.rowid<=?"]
        parameters: list[Any] = [owner_id, state["revision_cutoff"]]
        if view == "effective":
            conditions += [
                "r.revision=(SELECT MAX(v.revision) FROM life_revisions v WHERE v.object_id=r.object_id AND v.rowid<=?)",
                "r.status!='void'",
            ]
            parameters.append(state["revision_cutoff"])
        pieces = [
            "SELECT o.kind, r.object_id, r.revision, r.status, r.source_ref, r.operation_id, r.payload_json, r.recorded_at "
            "FROM life_objects o JOIN life_revisions r ON o.object_id=r.object_id WHERE "
            + " AND ".join(conditions)
        ]
        if anchors_exist:
            pieces.append(
                "SELECT 'anchor', record_id, 1, 'recorded', source_ref, operation_id, payload_json, recorded_at "
                "FROM life_anchors WHERE owner_id=? AND rowid<=?"
            )
            parameters.extend((owner_id, state["anchor_cutoff"]))
        if legacy_exist:
            pieces.append(
                "SELECT 'activity', record_id, 1, 'recorded', source_path, NULL, payload_json, recorded_at "
                "FROM life_legacy_events WHERE owner_id=? AND rowid<=?"
            )
            parameters.extend((owner_id, state["legacy_cutoff"]))
        outer = ["kind IN (" + ",".join("?" for _ in kinds) + ")"]
        parameters.extend(kinds)
        if record_id:
            outer.append("object_id=?")
            parameters.append(record_id)
        observed = "COALESCE(date(json_extract(payload_json,'$.time.occurred_at'),'+8 hours'),json_extract(payload_json,'$.time.occurred_date'))"
        if record_id is None:
            outer.append(f"COALESCE({observed},date(recorded_at,'+8 hours')) BETWEEN ? AND ?")
            parameters.extend((start_date.isoformat(), end_date.isoformat()))
        if habit_id:
            outer.append("kind='habit' AND json_extract(payload_json,'$.habit_id')=?")
            parameters.append(habit_id)
        relation = (
            "WITH entries AS ("
            + " UNION ALL ".join(pieces)
            + ") SELECT * FROM entries WHERE "
            + " AND ".join(outer)
        )
        all_matching_parameters = list(parameters)
        aggregate_rows = connection.execute(
            "SELECT json_extract(payload_json,'$.habit_id') AS habit_id, "
            "json_extract(payload_json,'$.definition_snapshot.record_type') AS record_type, "
            "json_extract(payload_json,'$.unit') AS unit, COUNT(*) AS reports, "
            "SUM(CASE WHEN json_extract(payload_json,'$.outcome') IN ('completed','partial') "
            "THEN json_extract(payload_json,'$.value') ELSE NULL END) AS total_value "
            "FROM (" + relation + ") WHERE kind='habit' GROUP BY habit_id,record_type,unit",
            all_matching_parameters,
        ).fetchall()
        if state["after"]:
            relation += " AND (recorded_at, object_id, revision) > (?, ?, ?)"
            parameters.extend(state["after"])
        parameters.extend((limit + 1, offset))
        rows = connection.execute(
            relation + " ORDER BY recorded_at, object_id, revision LIMIT ? OFFSET ?", parameters
        ).fetchall()
        values = [store.decode_object(row) for row in rows[:limit]]
        for value in values:
            time = value["payload"].get("time", {})
            value["range_basis"] = (
                "occurred_date"
                if time.get("occurred_date") or time.get("occurred_at")
                else "recorded_date"
            )
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            state["after"] = [last["recorded_at"], last["object_id"], last["revision"]]
            encoded = base64.urlsafe_b64encode(canonical(state).encode()).decode().rstrip("=")
            next_cursor = (
                encoded + "." + hmac.new(key, encoded.encode(), hashlib.sha256).hexdigest()
            )
        return {
            "records": values,
            "next_cursor": next_cursor,
            "next_offset": offset + limit if len(rows) > limit else None,
            "view": view,
            "aggregates": [dict(row) for row in aggregate_rows],
            "snapshot": {"revision_cutoff": state["revision_cutoff"]},
        }
