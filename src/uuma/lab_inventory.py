from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

BUCKETS = {"AVAILABLE", "RESERVED", "INSTALLED", "DAMAGED", "CONSUMED"}
BUILD_STATUSES = {"OPEN", "IN_PROGRESS", "COMPLETED", "ABANDONED"}
COMMISSIONING_STATUSES = {"PASS", "FAIL", "IN_PROGRESS", "BLOCKED"}
FAILURE_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
LESSON_TARGETS = {"ESCHEMATIC", "PROCUREMENT", "BUILD_PROCESS", "STOCKKEEPER", "LAB_ONLY"}
LESSON_SEVERITIES = {"BLOCK", "WARN", "RECOMMEND", "PREFERENCE", "KNOWLEDGE"}
LESSON_STATUSES = {"CANDIDATE", "SUPPORTED", "ACCEPTED", "DEPRECATED", "REJECTED"}
FEEDBACK_STATUSES = {"PROPOSED", "ACCEPTED", "REJECTED"}

TRANSITIONS: dict[str, tuple[str | None, str | None]] = {
    "RECEIVE": (None, "AVAILABLE"),
    "RESERVE": ("AVAILABLE", "RESERVED"),
    "RELEASE": ("RESERVED", "AVAILABLE"),
    "INSTALL": ("RESERVED", "INSTALLED"),
    "UNINSTALL": ("INSTALLED", "AVAILABLE"),
    "REPAIR": ("DAMAGED", "AVAILABLE"),
    "CONSUME": ("AVAILABLE", "CONSUMED"),
    "SCRAP": ("DAMAGED", None),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class InventoryError(ValueError):
    pass


class InventoryStore:
    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.bootstrap()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def bootstrap(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS component_refs (
                    component_id TEXT PRIMARY KEY,
                    display_name_snapshot TEXT,
                    source_system TEXT NOT NULL DEFAULT 'eschematic',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS locations (
                    location_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_location_id TEXT REFERENCES locations(location_id),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_lots (
                    lot_id TEXT PRIMARY KEY,
                    component_id TEXT NOT NULL REFERENCES component_refs(component_id),
                    supplier TEXT,
                    offer_ref TEXT,
                    ordered_quantity REAL,
                    received_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS builds (
                    build_id TEXT PRIMARY KEY,
                    design_revision_id TEXT NOT NULL,
                    design_manifest_hash TEXT,
                    design_manifest_json TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inventory_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    component_id TEXT NOT NULL REFERENCES component_refs(component_id),
                    lot_id TEXT NOT NULL DEFAULT '',
                    quantity REAL NOT NULL CHECK(quantity > 0),
                    from_bucket TEXT,
                    to_bucket TEXT,
                    from_location_id TEXT,
                    to_location_id TEXT,
                    build_id TEXT REFERENCES builds(build_id),
                    actor_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    evidence_ref TEXT,
                    occurred_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS legacy_import_rows (
                    source_key TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES inventory_events(event_id),
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_history_lines (
                    source_key TEXT PRIMARY KEY,
                    source_workbook_hash TEXT NOT NULL,
                    source_sheet TEXT NOT NULL,
                    source_row INTEGER NOT NULL,
                    order_id TEXT NOT NULL,
                    ordered_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    supplier TEXT,
                    category TEXT,
                    product_name TEXT NOT NULL,
                    product_url TEXT,
                    offer_ref TEXT,
                    variant TEXT,
                    ordered_quantity REAL NOT NULL CHECK(ordered_quantity > 0),
                    order_unit TEXT NOT NULL DEFAULT 'listing_unit',
                    goods_amount_raw REAL,
                    paid_amount_order_raw REAL,
                    shipping_amount_order_raw REAL,
                    identity_key TEXT NOT NULL,
                    component_id TEXT,
                    resolution_status TEXT NOT NULL,
                    evidence_ref TEXT,
                    imported_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS commissioning_records (
                    record_id TEXT PRIMARY KEY,
                    build_id TEXT NOT NULL REFERENCES builds(build_id),
                    test_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    notes TEXT NOT NULL DEFAULT '',
                    evidence_ref TEXT,
                    occurred_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS worklog_records (
                    worklog_id TEXT PRIMARY KEY,
                    build_id TEXT REFERENCES builds(build_id),
                    project_name TEXT NOT NULL,
                    source_ref TEXT,
                    action TEXT NOT NULL,
                    observation TEXT NOT NULL,
                    hypothesis TEXT NOT NULL DEFAULT '',
                    confirmed_cause TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    parts_json TEXT NOT NULL DEFAULT '[]',
                    next_action TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS failure_records (
                    failure_id TEXT PRIMARY KEY,
                    build_id TEXT REFERENCES builds(build_id),
                    component_id TEXT REFERENCES component_refs(component_id),
                    severity TEXT NOT NULL,
                    symptom TEXT NOT NULL,
                    suspected_cause TEXT NOT NULL DEFAULT '',
                    confirmed_cause TEXT NOT NULL DEFAULT '',
                    action_taken TEXT NOT NULL DEFAULT '',
                    evidence_ref TEXT,
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS engineering_lessons (
                    lesson_id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    target_system TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
                    status TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    exceptions TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS design_feedback_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    design_revision_id TEXT NOT NULL,
                    target_component_id TEXT REFERENCES component_refs(component_id),
                    change_summary TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    reviewer TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_inventory_component
                    ON inventory_events(component_id, lot_id);
                CREATE INDEX IF NOT EXISTS idx_inventory_build
                    ON inventory_events(build_id);
                CREATE INDEX IF NOT EXISTS idx_purchase_history_order
                    ON purchase_history_lines(order_id);
                CREATE INDEX IF NOT EXISTS idx_purchase_history_resolution
                    ON purchase_history_lines(resolution_status, identity_key);
                CREATE INDEX IF NOT EXISTS idx_commissioning_build
                    ON commissioning_records(build_id);
                CREATE INDEX IF NOT EXISTS idx_worklog_build
                    ON worklog_records(build_id);
                CREATE INDEX IF NOT EXISTS idx_worklog_project
                    ON worklog_records(project_name);
                CREATE INDEX IF NOT EXISTS idx_failure_build
                    ON failure_records(build_id);
                CREATE INDEX IF NOT EXISTS idx_failure_component
                    ON failure_records(component_id);
                CREATE INDEX IF NOT EXISTS idx_lessons_target
                    ON engineering_lessons(target_system, status);
                CREATE INDEX IF NOT EXISTS idx_design_feedback_rev
                    ON design_feedback_proposals(design_revision_id);
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO locations(location_id, name, created_at) VALUES ('UNLOCATED', 'Unlocated', ?)",
                (_now(),),
            )

    @staticmethod
    def _validate_quantity(quantity: float) -> float:
        value = float(quantity)
        if value <= 0:
            raise InventoryError("Quantity must be greater than zero.")
        return value

    @staticmethod
    def _validate_bucket(bucket: str | None) -> str | None:
        if bucket is None:
            return None
        normalized = bucket.strip().upper()
        if normalized not in BUCKETS:
            raise InventoryError(f"Unknown inventory bucket: {bucket}")
        return normalized

    def register_component(self, component_id: str, display_name: str = "") -> dict[str, str]:
        if not component_id.strip():
            raise InventoryError("component_id is required.")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO component_refs(component_id, display_name_snapshot, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(component_id) DO UPDATE SET
                    display_name_snapshot=excluded.display_name_snapshot,
                    updated_at=excluded.updated_at
                """,
                (component_id.strip(), display_name.strip() or None, _now()),
            )
        return {"component_id": component_id.strip(), "status": "registered"}

    def create_location(
        self, name: str, parent_location_id: str | None = None, location_id: str | None = None
    ) -> dict[str, str | None]:
        if not name.strip():
            raise InventoryError("Location name is required.")
        assigned_id = location_id or _id("loc")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO locations(location_id, name, parent_location_id, created_at) VALUES (?, ?, ?, ?)",
                (assigned_id, name.strip(), parent_location_id, _now()),
            )
        return {
            "location_id": assigned_id,
            "name": name.strip(),
            "parent_location_id": parent_location_id,
        }

    def create_build(
        self,
        design_revision_id: str,
        design_manifest_hash: str = "",
        design_manifest: dict[str, Any] | None = None,
        build_id: str | None = None,
    ) -> dict[str, Any]:
        if not design_revision_id.strip():
            raise InventoryError("design_revision_id is required.")
        assigned_id = build_id or _id("build")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO builds(
                    build_id, design_revision_id, design_manifest_hash,
                    design_manifest_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    assigned_id,
                    design_revision_id.strip(),
                    design_manifest_hash.strip() or None,
                    json.dumps(design_manifest, sort_keys=True) if design_manifest else None,
                    _now(),
                ),
            )
        return {
            "build_id": assigned_id,
            "design_revision_id": design_revision_id.strip(),
            "status": "OPEN",
        }

    def _balance_in_connection(
        self,
        connection: sqlite3.Connection,
        component_id: str,
        bucket: str,
        lot_id: str = "",
        location_id: str = "UNLOCATED",
    ) -> float:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE
                    WHEN to_bucket = ? AND to_location_id = ? THEN quantity ELSE 0 END), 0)
              - COALESCE(SUM(CASE
                    WHEN from_bucket = ? AND from_location_id = ? THEN quantity ELSE 0 END), 0)
              AS balance
            FROM inventory_events
            WHERE component_id = ? AND lot_id = ?
            """,
            (bucket, location_id, bucket, location_id, component_id, lot_id),
        ).fetchone()
        return float(row["balance"] or 0)

    def _record_event(
        self,
        *,
        event_type: str,
        component_id: str,
        quantity: float,
        from_bucket: str | None,
        to_bucket: str | None,
        lot_id: str = "",
        from_location_id: str | None = None,
        to_location_id: str | None = None,
        build_id: str | None = None,
        actor_id: str = "forge-lab-bot",
        reason: str,
        evidence_ref: str = "",
        metadata: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        amount = self._validate_quantity(quantity)
        source_bucket = self._validate_bucket(from_bucket)
        target_bucket = self._validate_bucket(to_bucket)
        if source_bucket is None and target_bucket is None:
            raise InventoryError("An inventory event needs a source or destination bucket.")
        if not reason.strip():
            raise InventoryError("Every inventory event requires a reason.")
        source_location = from_location_id or ("UNLOCATED" if source_bucket else None)
        target_location = to_location_id or ("UNLOCATED" if target_bucket else None)
        event_id = _id("inv")

        owns_connection = connection is None
        conn = connection or self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE") if owns_connection else None
            component = conn.execute(
                "SELECT component_id FROM component_refs WHERE component_id = ?", (component_id,)
            ).fetchone()
            if component is None:
                raise InventoryError(
                    "Unknown component_id. Register the canonical eSchematic component reference first."
                )
            if source_bucket:
                available = self._balance_in_connection(
                    conn, component_id, source_bucket, lot_id, source_location or "UNLOCATED"
                )
                if available + 1e-9 < amount:
                    raise InventoryError(
                        f"Insufficient {source_bucket} balance: requested {amount}, available {available}."
                    )
            conn.execute(
                """
                INSERT INTO inventory_events(
                    event_id, event_type, component_id, lot_id, quantity,
                    from_bucket, to_bucket, from_location_id, to_location_id,
                    build_id, actor_id, reason, evidence_ref, occurred_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    component_id,
                    lot_id,
                    amount,
                    source_bucket,
                    target_bucket,
                    source_location,
                    target_location,
                    build_id,
                    actor_id,
                    reason.strip(),
                    evidence_ref.strip() or None,
                    _now(),
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
            if owns_connection:
                conn.commit()
        except Exception:
            if owns_connection:
                conn.rollback()
            raise
        finally:
            if owns_connection:
                conn.close()
        return {
            "event_id": event_id,
            "event_type": event_type,
            "component_id": component_id,
            "quantity": amount,
            "from_bucket": source_bucket,
            "to_bucket": target_bucket,
            "lot_id": lot_id,
            "build_id": build_id,
        }

    def receive(
        self,
        component_id: str,
        quantity: float,
        *,
        lot_id: str = "",
        location_id: str = "UNLOCATED",
        display_name: str = "",
        supplier: str = "",
        offer_ref: str = "",
        actor_id: str = "forge-lab-bot",
        reason: str = "received and inspected",
        evidence_ref: str = "",
    ) -> dict[str, Any]:
        self.register_component(component_id, display_name)
        if lot_id:
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO purchase_lots(
                        lot_id, component_id, supplier, offer_ref, received_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (lot_id, component_id, supplier or None, offer_ref or None, _now(), _now()),
                )
        return self._record_event(
            event_type="RECEIVE",
            component_id=component_id,
            quantity=quantity,
            from_bucket=None,
            to_bucket="AVAILABLE",
            lot_id=lot_id,
            to_location_id=location_id,
            actor_id=actor_id,
            reason=reason,
            evidence_ref=evidence_ref,
        )

    def transition(
        self,
        event_type: str,
        component_id: str,
        quantity: float,
        *,
        lot_id: str = "",
        location_id: str = "UNLOCATED",
        build_id: str | None = None,
        source_bucket: str | None = None,
        actor_id: str = "forge-lab-bot",
        reason: str,
        evidence_ref: str = "",
    ) -> dict[str, Any]:
        normalized = event_type.strip().upper()
        if normalized == "MARK_DAMAGED":
            source = self._validate_bucket(source_bucket)
            if source in {None, "DAMAGED", "CONSUMED"}:
                raise InventoryError("MARK_DAMAGED requires an active source_bucket.")
            target = "DAMAGED"
        elif normalized in TRANSITIONS:
            source, target = TRANSITIONS[normalized]
        else:
            raise InventoryError(f"Unsupported inventory transition: {event_type}")
        if normalized in {"INSTALL", "UNINSTALL"} and not build_id:
            raise InventoryError(f"{normalized} requires build_id.")
        return self._record_event(
            event_type=normalized,
            component_id=component_id,
            quantity=quantity,
            from_bucket=source,
            to_bucket=target,
            lot_id=lot_id,
            from_location_id=location_id if source else None,
            to_location_id=location_id if target else None,
            build_id=build_id,
            actor_id=actor_id,
            reason=reason,
            evidence_ref=evidence_ref,
        )

    def adjust(
        self,
        component_id: str,
        bucket: str,
        delta: float,
        *,
        lot_id: str = "",
        location_id: str = "UNLOCATED",
        actor_id: str = "forge-lab-bot",
        reason: str,
        evidence_ref: str = "",
    ) -> dict[str, Any]:
        if delta == 0:
            raise InventoryError("Adjustment delta cannot be zero.")
        normalized_bucket = self._validate_bucket(bucket)
        return self._record_event(
            event_type="ADJUST",
            component_id=component_id,
            quantity=abs(delta),
            from_bucket=normalized_bucket if delta < 0 else None,
            to_bucket=normalized_bucket if delta > 0 else None,
            lot_id=lot_id,
            from_location_id=location_id if delta < 0 else None,
            to_location_id=location_id if delta > 0 else None,
            actor_id=actor_id,
            reason=reason,
            evidence_ref=evidence_ref,
            metadata={"delta": delta},
        )

    def balances(self, component_id: str | None = None) -> list[dict[str, Any]]:
        clauses = "WHERE component_id = ?" if component_id else ""
        parameters: tuple[Any, ...] = (component_id,) if component_id else ()
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                WITH movements AS (
                    SELECT component_id, lot_id, to_location_id AS location_id,
                           to_bucket AS bucket, quantity AS delta
                    FROM inventory_events
                    WHERE to_bucket IS NOT NULL
                    UNION ALL
                    SELECT component_id, lot_id, from_location_id AS location_id,
                           from_bucket AS bucket, -quantity AS delta
                    FROM inventory_events
                    WHERE from_bucket IS NOT NULL
                )
                SELECT component_id, lot_id, location_id, bucket, SUM(delta) AS quantity
                FROM movements
                {clauses}
                GROUP BY component_id, lot_id, location_id, bucket
                HAVING ABS(SUM(delta)) > 0.000000001
                ORDER BY component_id, lot_id, location_id, bucket
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def check_bom_shortage(self, resolved_items: list[dict[str, Any]]) -> dict[str, Any]:
        requirements: dict[str, float] = {}
        for item in resolved_items:
            component_id = str(item.get("component_id", "")).strip()
            if not component_id:
                raise InventoryError("Each resolved BOM item requires component_id.")
            requirements[component_id] = requirements.get(component_id, 0) + self._validate_quantity(
                float(item.get("quantity", 0))
            )

        balances = self.balances()
        available: dict[str, float] = {}
        for row in balances:
            if row["bucket"] == "AVAILABLE":
                available[row["component_id"]] = available.get(row["component_id"], 0) + float(
                    row["quantity"]
                )
        results = []
        for component_id, required in requirements.items():
            on_hand = available.get(component_id, 0)
            shortage = max(required - on_hand, 0)
            results.append(
                {
                    "component_id": component_id,
                    "required": required,
                    "available": on_hand,
                    "shortage": shortage,
                    "status": "SHORTAGE" if shortage > 0 else "AVAILABLE",
                }
            )
        return {
            "status": "SHORTAGE" if any(row["shortage"] > 0 for row in results) else "AVAILABLE",
            "items": results,
            "procurement_requirements": [row for row in results if row["shortage"] > 0],
        }

    def current_as_built(self, build_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            build = connection.execute(
                "SELECT * FROM builds WHERE build_id = ?", (build_id,)
            ).fetchone()
            if build is None:
                raise InventoryError("Unknown build_id.")
            rows = connection.execute(
                """
                SELECT component_id, lot_id,
                    SUM(CASE WHEN to_bucket = 'INSTALLED' THEN quantity ELSE 0 END)
                  - SUM(CASE WHEN from_bucket = 'INSTALLED' THEN quantity ELSE 0 END) AS quantity
                FROM inventory_events
                WHERE build_id = ?
                GROUP BY component_id, lot_id
                HAVING quantity > 0.000000001
                ORDER BY component_id, lot_id
                """,
                (build_id,),
            ).fetchall()
        return {
            "build_id": build_id,
            "design_revision_id": build["design_revision_id"],
            "design_manifest_hash": build["design_manifest_hash"],
            "status": build["status"],
            "installed_items": [dict(row) for row in rows],
        }

    def import_legacy_rows(
        self, rows: list[dict[str, Any]], *, commit: bool = False, actor_id: str = "forge-lab-bot"
    ) -> dict[str, Any]:
        preview = []
        seen: set[str] = set()
        for index, row in enumerate(rows, start=1):
            source_key = str(row.get("source_key", "")).strip()
            component_id = str(row.get("component_id", "")).strip()
            if not source_key or source_key in seen:
                raise InventoryError(f"Row {index} needs a unique source_key.")
            if not component_id:
                raise InventoryError(f"Row {index} needs a resolved component_id.")
            seen.add(source_key)
            preview.append(
                {
                    "source_key": source_key,
                    "component_id": component_id,
                    "display_name": str(row.get("display_name", "")),
                    "quantity": self._validate_quantity(float(row.get("quantity", 0))),
                    "lot_id": str(row.get("lot_id", "LEGACY")),
                    "location_id": str(row.get("location_id", "UNLOCATED")),
                    "evidence_ref": str(row.get("evidence_ref", "")),
                }
            )
        if not commit:
            return {"status": "preview", "rows": preview, "committed": 0, "skipped": 0}

        committed = 0
        skipped = 0
        for row in preview:
            with self.connect() as connection:
                prior = connection.execute(
                    "SELECT event_id FROM legacy_import_rows WHERE source_key = ?",
                    (row["source_key"],),
                ).fetchone()
                if prior:
                    skipped += 1
                    continue
            event = self.receive(
                row["component_id"],
                row["quantity"],
                lot_id=row["lot_id"],
                location_id=row["location_id"],
                display_name=row["display_name"],
                actor_id=actor_id,
                reason="legacy inventory import",
                evidence_ref=row["evidence_ref"],
            )
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO legacy_import_rows(source_key, event_id, imported_at) VALUES (?, ?, ?)",
                    (row["source_key"], event["event_id"], _now()),
                )
            committed += 1
        return {"status": "committed", "rows": preview, "committed": committed, "skipped": skipped}

    def import_purchase_history(
        self, rows: list[dict[str, Any]], *, commit: bool = False
    ) -> dict[str, Any]:
        """Stage order evidence without changing physical inventory balances."""
        preview: list[dict[str, Any]] = []
        seen: set[str] = set()
        required_text_fields = (
            "source_key",
            "source_workbook_hash",
            "source_sheet",
            "order_id",
            "ordered_at",
            "status",
            "product_name",
            "identity_key",
        )
        for index, row in enumerate(rows, start=1):
            normalized = {field: str(row.get(field, "")).strip() for field in required_text_fields}
            missing = [field for field, value in normalized.items() if not value]
            if missing:
                raise InventoryError(f"Row {index} is missing required fields: {', '.join(missing)}.")
            if normalized["source_key"] in seen:
                raise InventoryError(f"Row {index} needs a unique source_key.")
            seen.add(normalized["source_key"])
            component_id = str(row.get("component_id") or "").strip()
            preview.append(
                {
                    **normalized,
                    "source_row": int(row.get("source_row", 0)),
                    "supplier": str(row.get("supplier", "")).strip(),
                    "category": str(row.get("category", "")).strip(),
                    "product_url": str(row.get("product_url", "")).strip(),
                    "offer_ref": str(row.get("offer_ref", "")).strip(),
                    "variant": str(row.get("variant", "")).strip(),
                    "ordered_quantity": self._validate_quantity(
                        float(row.get("ordered_quantity", 0))
                    ),
                    "order_unit": str(row.get("order_unit", "listing_unit")).strip()
                    or "listing_unit",
                    "goods_amount_raw": float(row.get("goods_amount_raw", 0)),
                    "paid_amount_order_raw": float(row.get("paid_amount_order_raw", 0)),
                    "shipping_amount_order_raw": float(
                        row.get("shipping_amount_order_raw", 0)
                    ),
                    "component_id": component_id or None,
                    "resolution_status": "RESOLVED" if component_id else "NEEDS_COMPONENT_REVIEW",
                    "evidence_ref": str(row.get("evidence_ref", "")).strip(),
                }
            )
        summary = {
            "rows": len(preview),
            "resolved": sum(row["component_id"] is not None for row in preview),
            "needs_component_review": sum(row["component_id"] is None for row in preview),
            "inventory_events_created": 0,
            "inventory_balance_changed": False,
        }
        if not commit:
            return {
                "status": "preview",
                **summary,
                "committed": 0,
                "skipped": 0,
                "sample_rows": preview[:25],
            }

        committed = 0
        skipped = 0
        with self.connect() as connection:
            for row in preview:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO purchase_history_lines(
                        source_key, source_workbook_hash, source_sheet, source_row,
                        order_id, ordered_at, status, supplier, category, product_name,
                        product_url, offer_ref, variant, ordered_quantity, order_unit,
                        goods_amount_raw, paid_amount_order_raw, shipping_amount_order_raw,
                        identity_key, component_id, resolution_status, evidence_ref,
                        imported_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["source_key"],
                        row["source_workbook_hash"],
                        row["source_sheet"],
                        row["source_row"],
                        row["order_id"],
                        row["ordered_at"],
                        row["status"],
                        row["supplier"] or None,
                        row["category"] or None,
                        row["product_name"],
                        row["product_url"] or None,
                        row["offer_ref"] or None,
                        row["variant"] or None,
                        row["ordered_quantity"],
                        row["order_unit"],
                        row["goods_amount_raw"],
                        row["paid_amount_order_raw"],
                        row["shipping_amount_order_raw"],
                        row["identity_key"],
                        row["component_id"],
                        row["resolution_status"],
                        row["evidence_ref"] or None,
                        _now(),
                        "{}",
                    ),
                )
                if cursor.rowcount:
                    committed += 1
                else:
                    skipped += 1
        return {
            "status": "committed",
            **summary,
            "committed": committed,
            "skipped": skipped,
            "sample_rows": preview[:25],
        }

    def purchase_history(
        self, *, needs_review_only: bool = False, limit: int = 100
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clause = "WHERE resolution_status = 'NEEDS_COMPONENT_REVIEW'" if needs_review_only else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT source_key, order_id, ordered_at, status, supplier, category,
                       product_name, variant, ordered_quantity, order_unit, identity_key,
                       component_id, resolution_status, evidence_ref
                FROM purchase_history_lines
                {clause}
                ORDER BY ordered_at DESC, source_row ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_purchase_history_line(
        self, source_key: str, component_id: str
    ) -> dict[str, Any]:
        if not source_key.strip() or not component_id.strip():
            raise InventoryError("source_key and component_id are required.")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE purchase_history_lines
                SET component_id = ?, resolution_status = 'RESOLVED'
                WHERE source_key = ?
                """,
                (component_id.strip(), source_key.strip()),
            )
            if cursor.rowcount != 1:
                raise InventoryError("Unknown purchase-history source_key.")
        return {
            "source_key": source_key.strip(),
            "component_id": component_id.strip(),
            "resolution_status": "RESOLVED",
        }

    def list_builds(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clause = "WHERE status = ?" if status else ""
        params = (status.strip().upper(), safe_limit) if status else (safe_limit,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT build_id, design_revision_id, design_manifest_hash, status, created_at
                FROM builds
                {clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def update_build_status(self, build_id: str, status: str) -> dict[str, Any]:
        normalized = status.strip().upper()
        if normalized not in BUILD_STATUSES:
            raise InventoryError(f"Unknown build status: {status}")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE builds SET status = ? WHERE build_id = ?",
                (normalized, build_id.strip()),
            )
            if cursor.rowcount != 1:
                raise InventoryError("Unknown build_id.")
        return {"build_id": build_id.strip(), "status": normalized}

    def record_commissioning(
        self,
        build_id: str,
        test_name: str,
        status: str,
        *,
        operator: str = "forge-lab-bot",
        metrics: dict[str, Any] | None = None,
        notes: str = "",
        evidence_ref: str = "",
        record_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        normalized_status = status.strip().upper()
        if normalized_status not in COMMISSIONING_STATUSES:
            raise InventoryError(f"Unknown commissioning status: {status}")
        if not test_name.strip():
            raise InventoryError("test_name is required.")
        assigned_id = record_id or _id("comm")
        occurred = occurred_at or _now()
        with self.connect() as connection:
            build = connection.execute(
                "SELECT build_id FROM builds WHERE build_id = ?", (build_id.strip(),)
            ).fetchone()
            if build is None:
                raise InventoryError("Unknown build_id.")
            connection.execute(
                """
                INSERT INTO commissioning_records(
                    record_id, build_id, test_name, status, operator,
                    metrics_json, notes, evidence_ref, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assigned_id,
                    build_id.strip(),
                    test_name.strip(),
                    normalized_status,
                    operator.strip() or "forge-lab-bot",
                    json.dumps(metrics or {}, sort_keys=True),
                    notes.strip(),
                    evidence_ref.strip() or None,
                    occurred,
                ),
            )
        return {
            "record_id": assigned_id,
            "build_id": build_id.strip(),
            "test_name": test_name.strip(),
            "status": normalized_status,
            "occurred_at": occurred,
        }

    def list_commissioning(
        self, *, build_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clauses = []
        params: list[Any] = []
        if build_id:
            clauses.append("build_id = ?")
            params.append(build_id.strip())
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT record_id, build_id, test_name, status, operator,
                       metrics_json, notes, evidence_ref, occurred_at
                FROM commissioning_records
                {where}
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
            result.append(item)
        return result

    def record_worklog(
        self,
        project_name: str,
        action: str,
        observation: str,
        *,
        build_id: str | None = None,
        source_ref: str = "",
        hypothesis: str = "",
        confirmed_cause: str = "",
        result: str = "",
        parts: list[str] | None = None,
        next_action: str = "",
        worklog_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        if not project_name.strip() or not action.strip() or not observation.strip():
            raise InventoryError("project_name, action, and observation are required for a worklog.")
        assigned_id = worklog_id or _id("log")
        occurred = occurred_at or _now()
        normalized = {
            "build_id": build_id.strip() if build_id else None,
            "project_name": project_name.strip(),
            "source_ref": source_ref.strip() or None,
            "action": action.strip(),
            "observation": observation.strip(),
            "hypothesis": hypothesis.strip(),
            "confirmed_cause": confirmed_cause.strip(),
            "result": result.strip(),
            "parts_json": json.dumps(parts or [], sort_keys=True),
            "next_action": next_action.strip(),
        }
        with self.connect() as connection:
            if build_id:
                build = connection.execute(
                    "SELECT build_id FROM builds WHERE build_id = ?", (build_id.strip(),)
                ).fetchone()
                if build is None:
                    raise InventoryError("Unknown build_id.")
            existing = connection.execute(
                "SELECT * FROM worklog_records WHERE worklog_id = ?", (assigned_id,)
            ).fetchone()
            if existing is not None:
                if any(existing[key] != value for key, value in normalized.items()):
                    raise InventoryError(
                        "The worklog_id already exists with different journal content."
                    )
                return {
                    "worklog_id": assigned_id,
                    "project_name": normalized["project_name"],
                    "build_id": normalized["build_id"],
                    "occurred_at": existing["occurred_at"],
                }
            connection.execute(
                """
                INSERT INTO worklog_records(
                    worklog_id, build_id, project_name, source_ref,
                    action, observation, hypothesis, confirmed_cause,
                    result, parts_json, next_action, occurred_at, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assigned_id,
                    normalized["build_id"],
                    normalized["project_name"],
                    normalized["source_ref"],
                    normalized["action"],
                    normalized["observation"],
                    normalized["hypothesis"],
                    normalized["confirmed_cause"],
                    normalized["result"],
                    normalized["parts_json"],
                    normalized["next_action"],
                    occurred,
                    _now(),
                ),
            )
        return {
            "worklog_id": assigned_id,
            "project_name": normalized["project_name"],
            "build_id": normalized["build_id"],
            "occurred_at": occurred,
        }

    def list_worklogs(
        self, *, project_name: str | None = None, build_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clauses = []
        params: list[Any] = []
        if project_name:
            clauses.append("project_name = ?")
            params.append(project_name.strip())
        if build_id:
            clauses.append("build_id = ?")
            params.append(build_id.strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT worklog_id, build_id, project_name, source_ref,
                       action, observation, hypothesis, confirmed_cause,
                       result, parts_json, next_action, occurred_at, recorded_at
                FROM worklog_records
                {where}
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["parts"] = json.loads(item.pop("parts_json") or "[]")
            result.append(item)
        return result

    def record_failure(
        self,
        symptom: str,
        *,
        severity: str = "MEDIUM",
        build_id: str | None = None,
        component_id: str | None = None,
        suspected_cause: str = "",
        confirmed_cause: str = "",
        action_taken: str = "",
        evidence_ref: str = "",
        failure_id: str | None = None,
        occurred_at: str | None = None,
    ) -> dict[str, Any]:
        if not symptom.strip():
            raise InventoryError("symptom is required for failure recording.")
        normalized_severity = severity.strip().upper()
        if normalized_severity not in FAILURE_SEVERITIES:
            raise InventoryError(f"Unknown failure severity: {severity}")
        assigned_id = failure_id or _id("fail")
        occurred = occurred_at or _now()
        with self.connect() as connection:
            if build_id:
                build = connection.execute(
                    "SELECT build_id FROM builds WHERE build_id = ?", (build_id.strip(),)
                ).fetchone()
                if build is None:
                    raise InventoryError("Unknown build_id.")
            if component_id:
                comp = connection.execute(
                    "SELECT component_id FROM component_refs WHERE component_id = ?",
                    (component_id.strip(),),
                ).fetchone()
                if comp is None:
                    raise InventoryError("Unknown component_id.")
            connection.execute(
                """
                INSERT INTO failure_records(
                    failure_id, build_id, component_id, severity,
                    symptom, suspected_cause, confirmed_cause,
                    action_taken, evidence_ref, occurred_at, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assigned_id,
                    build_id.strip() if build_id else None,
                    component_id.strip() if component_id else None,
                    normalized_severity,
                    symptom.strip(),
                    suspected_cause.strip(),
                    confirmed_cause.strip(),
                    action_taken.strip(),
                    evidence_ref.strip() or None,
                    occurred,
                    _now(),
                ),
            )
        return {
            "failure_id": assigned_id,
            "severity": normalized_severity,
            "build_id": build_id.strip() if build_id else None,
            "component_id": component_id.strip() if component_id else None,
            "occurred_at": occurred,
        }

    def list_failures(
        self,
        *,
        build_id: str | None = None,
        component_id: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clauses = []
        params: list[Any] = []
        if build_id:
            clauses.append("build_id = ?")
            params.append(build_id.strip())
        if component_id:
            clauses.append("component_id = ?")
            params.append(component_id.strip())
        if severity:
            clauses.append("severity = ?")
            params.append(severity.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT failure_id, build_id, component_id, severity,
                       symptom, suspected_cause, confirmed_cause,
                       action_taken, evidence_ref, occurred_at, recorded_at
                FROM failure_records
                {where}
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def propose_lesson(
        self,
        statement: str,
        scope: str,
        *,
        target_system: str = "LAB_ONLY",
        severity: str = "RECOMMEND",
        confidence: float = 0.8,
        status: str = "CANDIDATE",
        evidence_refs: list[str] | None = None,
        exceptions: str = "",
        created_by: str = "forge-lab-bot",
        lesson_id: str | None = None,
    ) -> dict[str, Any]:
        if not statement.strip() or not scope.strip():
            raise InventoryError("statement and scope are required for an engineering lesson.")
        norm_target = target_system.strip().upper()
        if norm_target not in LESSON_TARGETS:
            raise InventoryError(f"Unknown target system: {target_system}")
        norm_severity = severity.strip().upper()
        if norm_severity not in LESSON_SEVERITIES:
            raise InventoryError(f"Unknown lesson severity: {severity}")
        norm_status = status.strip().upper()
        if norm_status not in LESSON_STATUSES:
            raise InventoryError(f"Unknown lesson status: {status}")
        conf = float(confidence)
        if not (0.0 <= conf <= 1.0):
            raise InventoryError("confidence must be between 0.0 and 1.0.")
        assigned_id = lesson_id or _id("lsn")
        now_ts = _now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO engineering_lessons(
                    lesson_id, statement, scope, target_system, severity,
                    confidence, status, evidence_refs_json, exceptions,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assigned_id,
                    statement.strip(),
                    scope.strip(),
                    norm_target,
                    norm_severity,
                    conf,
                    norm_status,
                    json.dumps(evidence_refs or [], sort_keys=True),
                    exceptions.strip(),
                    created_by.strip() or "forge-lab-bot",
                    now_ts,
                    now_ts,
                ),
            )
        return {
            "lesson_id": assigned_id,
            "statement": statement.strip(),
            "target_system": norm_target,
            "status": norm_status,
            "confidence": conf,
        }

    def list_lessons(
        self,
        *,
        target_system: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clauses = []
        params: list[Any] = []
        if target_system:
            clauses.append("target_system = ?")
            params.append(target_system.strip().upper())
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT lesson_id, statement, scope, target_system, severity,
                       confidence, status, evidence_refs_json, exceptions,
                       created_by, created_at, updated_at
                FROM engineering_lessons
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence_refs"] = json.loads(item.pop("evidence_refs_json") or "[]")
            result.append(item)
        return result

    def update_lesson_status(
        self, lesson_id: str, status: str, *, exceptions: str | None = None
    ) -> dict[str, Any]:
        norm_status = status.strip().upper()
        if norm_status not in LESSON_STATUSES:
            raise InventoryError(f"Unknown lesson status: {status}")
        with self.connect() as connection:
            if exceptions is not None:
                cursor = connection.execute(
                    """
                    UPDATE engineering_lessons
                    SET status = ?, exceptions = ?, updated_at = ?
                    WHERE lesson_id = ?
                    """,
                    (norm_status, exceptions.strip(), _now(), lesson_id.strip()),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE engineering_lessons
                    SET status = ?, updated_at = ?
                    WHERE lesson_id = ?
                    """,
                    (norm_status, _now(), lesson_id.strip()),
                )
            if cursor.rowcount != 1:
                raise InventoryError("Unknown lesson_id.")
        return {"lesson_id": lesson_id.strip(), "status": norm_status}

    def propose_design_feedback(
        self,
        design_revision_id: str,
        change_summary: str,
        rationale: str,
        *,
        target_component_id: str | None = None,
        evidence_refs: list[str] | None = None,
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        if not design_revision_id.strip() or not change_summary.strip() or not rationale.strip():
            raise InventoryError("design_revision_id, change_summary, and rationale are required.")
        assigned_id = proposal_id or _id("prop")
        now_ts = _now()
        with self.connect() as connection:
            if target_component_id:
                comp = connection.execute(
                    "SELECT component_id FROM component_refs WHERE component_id = ?",
                    (target_component_id.strip(),),
                ).fetchone()
                if comp is None:
                    raise InventoryError("Unknown target_component_id.")
            connection.execute(
                """
                INSERT INTO design_feedback_proposals(
                    proposal_id, design_revision_id, target_component_id,
                    change_summary, rationale, evidence_refs_json,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PROPOSED', ?, ?)
                """,
                (
                    assigned_id,
                    design_revision_id.strip(),
                    target_component_id.strip() if target_component_id else None,
                    change_summary.strip(),
                    rationale.strip(),
                    json.dumps(evidence_refs or [], sort_keys=True),
                    now_ts,
                    now_ts,
                ),
            )
        return {
            "proposal_id": assigned_id,
            "design_revision_id": design_revision_id.strip(),
            "status": "PROPOSED",
        }

    def list_design_feedback(
        self,
        *,
        design_revision_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 10_000))
        clauses = []
        params: list[Any] = []
        if design_revision_id:
            clauses.append("design_revision_id = ?")
            params.append(design_revision_id.strip())
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT proposal_id, design_revision_id, target_component_id,
                       change_summary, rationale, evidence_refs_json,
                       status, reviewer, created_at, updated_at
                FROM design_feedback_proposals
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence_refs"] = json.loads(item.pop("evidence_refs_json") or "[]")
            result.append(item)
        return result

    def update_design_feedback_status(
        self, proposal_id: str, status: str, *, reviewer: str = ""
    ) -> dict[str, Any]:
        norm_status = status.strip().upper()
        if norm_status not in FEEDBACK_STATUSES:
            raise InventoryError(f"Unknown feedback status: {status}")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE design_feedback_proposals
                SET status = ?, reviewer = ?, updated_at = ?
                WHERE proposal_id = ?
                """,
                (norm_status, reviewer.strip() or None, _now(), proposal_id.strip()),
            )
            if cursor.rowcount != 1:
                raise InventoryError("Unknown proposal_id.")
        return {"proposal_id": proposal_id.strip(), "status": norm_status}
