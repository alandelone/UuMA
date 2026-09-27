"""Commerce batch persistence, immutable JSON archive, and lab.db commerce tables."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ALLOWED_CATEGORIES = {"electronics", "consumable", "tool", "other"}
ALLOWED_OWNERSHIPS = {"self", "others"}
ALLOWED_REVIEW_STATUSES = {"unreviewed", "reviewed", "pending_identity_review"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash_payload(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _default_lab_db_path() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA"))
    override = os.environ.get("LAB_DATABASE_PATH")
    if override:
        return Path(override)
    return data_dir / "forge-lab-bot" / "lab.db"


class CommerceStore:
    def __init__(
        self,
        database_path: Path | str | None = None,
        archive_dir: Path | str | None = None,
    ):
        if database_path is None:
            self.database_path = _default_lab_db_path()
        else:
            self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        if archive_dir is None:
            self.archive_dir = self.database_path.parent / "commerce"
        else:
            self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.bootstrap()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.database_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def bootstrap(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS commerce_batches (
                    batch_id TEXT PRIMARY KEY,
                    payload_hash TEXT NOT NULL,
                    archive_path TEXT NOT NULL,
                    order_count INTEGER NOT NULL,
                    line_count INTEGER NOT NULL,
                    receipt_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_headers (
                    platform TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    order_status TEXT NOT NULL DEFAULT '',
                    order_total REAL,
                    currency TEXT NOT NULL DEFAULT 'MYR',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    latest_evidence_version INTEGER NOT NULL DEFAULT 1,
                    completeness_status TEXT NOT NULL DEFAULT 'complete',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(platform, account_id, order_id)
                );

                CREATE TABLE IF NOT EXISTS commerce_order_lines (
                    line_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    sku_id TEXT NOT NULL DEFAULT '',
                    product_name TEXT NOT NULL,
                    variant_name TEXT NOT NULL DEFAULT '',
                    unit_price REAL,
                    quantity REAL NOT NULL,
                    line_total REAL,
                    currency TEXT NOT NULL DEFAULT 'MYR',
                    category TEXT NOT NULL DEFAULT 'electronics',
                    ownership TEXT,
                    review_status TEXT NOT NULL DEFAULT 'unreviewed',
                    ai_category_suggestion TEXT,
                    ai_ownership_suggestion TEXT,
                    evidence_version INTEGER NOT NULL DEFAULT 1,
                    review_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_order_lines_order
                    ON commerce_order_lines(platform, account_id, order_id);
                CREATE INDEX IF NOT EXISTS idx_order_lines_review
                    ON commerce_order_lines(review_status, ownership);
                """
            )

    def write_immutable_archive(self, task_id: str, batch_id: str, payload: dict[str, Any]) -> Path:
        target_dir = self.archive_dir / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / f"{batch_id}.json"
        tmp_path = target_dir / f"{batch_id}.json.tmp_{uuid.uuid4().hex}"

        content = json.dumps(payload, indent=2, ensure_ascii=False)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, final_path)
        return final_path

    def ingest_batch(self, batch_payload: dict[str, Any]) -> dict[str, Any]:
        batch_id = batch_payload.get("batch_id")
        if not batch_id or not str(batch_id).strip():
            raise ValueError("batch_id is required in batch_payload.")
        batch_id = str(batch_id).strip()

        task_id = str(batch_payload.get("task_id", "default_task")).strip()
        platform = str(batch_payload.get("platform", "shopee")).strip().lower()
        account_id = str(batch_payload.get("account_id", "default_account")).strip()
        orders = batch_payload.get("orders", [])

        payload_hash = _hash_payload(batch_payload)

        # Check idempotency in commerce_batches
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM commerce_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] == payload_hash:
                    return {
                        "batch_id": batch_id,
                        "status": "DURABLE_STORED",
                        "receipt_status": "EXISTING_ACK",
                        "payload_hash": payload_hash,
                        "archive_path": existing["archive_path"],
                        "order_count": existing["order_count"],
                        "line_count": existing["line_count"],
                        "created_at": existing["created_at"],
                    }
                raise ValueError(
                    f"Conflict: batch_id '{batch_id}' already exists with a different payload hash."
                )

        # 1. Write immutable archive file first
        archive_path = self.write_immutable_archive(task_id, batch_id, batch_payload)
        now = _now()

        total_orders = len(orders)
        total_lines = 0

        # 2. Transactionally write to lab.db
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for order in orders:
                order_id = str(order.get("order_id", "")).strip()
                if not order_id:
                    continue
                order_status = str(order.get("status", "")).strip()
                order_total = float(order.get("total_amount", 0.0)) if order.get("total_amount") is not None else None
                currency = str(order.get("currency", "MYR")).strip().upper() or "MYR"

                # Check existing order header
                header = conn.execute(
                    """
                    SELECT first_seen_at, latest_evidence_version, order_status, order_total
                    FROM order_headers
                    WHERE platform = ? AND account_id = ? AND order_id = ?
                    """,
                    (platform, account_id, order_id),
                ).fetchone()

                if header is None:
                    evidence_version = 1
                    first_seen = now
                    conn.execute(
                        """
                        INSERT INTO order_headers(
                            platform, account_id, order_id, order_status, order_total,
                            currency, first_seen_at, last_seen_at, latest_evidence_version,
                            completeness_status, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?)
                        """,
                        (platform, account_id, order_id, order_status, order_total, currency, first_seen, now, evidence_version, json.dumps(order, ensure_ascii=False)),
                    )
                else:
                    first_seen = header["first_seen_at"]
                    # If status or total changed, bump evidence_version
                    has_changed = (header["order_status"] != order_status or header["order_total"] != order_total)
                    evidence_version = header["latest_evidence_version"] + (1 if has_changed else 0)
                    conn.execute(
                        """
                        UPDATE order_headers
                        SET order_status = ?, order_total = ?, currency = ?, last_seen_at = ?,
                            latest_evidence_version = ?, metadata_json = ?
                        WHERE platform = ? AND account_id = ? AND order_id = ?
                        """,
                        (order_status, order_total, currency, now, evidence_version, json.dumps(order, ensure_ascii=False), platform, account_id, order_id),
                    )

                items = order.get("items", [])
                seen_line_keys: set[str] = set()

                for item in items:
                    total_lines += 1
                    product_id = str(item.get("product_id", "")).strip() or "p_unknown"
                    sku_id = str(item.get("sku_id", "")).strip()
                    product_name = str(item.get("product_name", "")).strip() or "Unnamed Product"
                    variant_name = str(item.get("variant_name", "")).strip()
                    unit_price = float(item.get("unit_price", 0.0)) if item.get("unit_price") is not None else None
                    quantity = float(item.get("quantity", 1.0))
                    line_total = float(item.get("line_total", 0.0)) if item.get("line_total") is not None else (unit_price * quantity if unit_price is not None else None)

                    # Build candidate identity key
                    norm_key = f"{platform}:{account_id}:{order_id}:{product_id}:{sku_id}:{variant_name}"
                    is_collision = norm_key in seen_line_keys
                    seen_line_keys.add(norm_key)

                    # Provided stable line_id or generate one from business candidate key
                    provided_line_id = str(item.get("line_id", "")).strip()
                    candidate_hash = hashlib.sha256(norm_key.encode()).hexdigest()[:16]
                    line_id = provided_line_id or (f"line_{candidate_hash}_collision" if is_collision else f"line_{candidate_hash}")

                    ai_cat = str(item.get("ai_category_suggestion", "electronics")).strip()
                    ai_owner = str(item.get("ai_ownership_suggestion", "self")).strip()

                    review_status = "pending_identity_review" if is_collision else "unreviewed"

                    # Check if line already exists
                    existing_line = conn.execute(
                        "SELECT * FROM commerce_order_lines WHERE line_id = ?",
                        (line_id,),
                    ).fetchone()

                    if existing_line is None:
                        conn.execute(
                            """
                            INSERT INTO commerce_order_lines(
                                line_id, platform, account_id, order_id, product_id, sku_id,
                                product_name, variant_name, unit_price, quantity, line_total,
                                currency, category, ownership, review_status, ai_category_suggestion,
                                ai_ownership_suggestion, evidence_version, review_version, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'electronics', NULL, ?, ?, ?, 1, 1, ?, ?)
                            """,
                            (
                                line_id, platform, account_id, order_id, product_id, sku_id,
                                product_name, variant_name, unit_price, quantity, line_total,
                                currency, review_status, ai_cat, ai_owner, now, now,
                            ),
                        )
                    else:
                        # Existing line: update evidence version if changed, preserve user review!
                        ev_ver = existing_line["evidence_version"] + 1
                        conn.execute(
                            """
                            UPDATE commerce_order_lines
                            SET product_name = ?, variant_name = ?, unit_price = ?,
                                quantity = ?, line_total = ?, evidence_version = ?, updated_at = ?
                            WHERE line_id = ?
                            """,
                            (product_name, variant_name, unit_price, quantity, line_total, ev_ver, now, line_id),
                        )

            # Insert batch record
            conn.execute(
                """
                INSERT INTO commerce_batches(
                    batch_id, payload_hash, archive_path, order_count, line_count,
                    receipt_status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'DURABLE_STORED', ?)
                """,
                (batch_id, payload_hash, str(archive_path), total_orders, total_lines, now),
            )

        return {
            "batch_id": batch_id,
            "status": "DURABLE_STORED",
            "receipt_status": "NEW_ACK",
            "payload_hash": payload_hash,
            "archive_path": str(archive_path),
            "order_count": total_orders,
            "line_count": total_lines,
            "created_at": now,
        }

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM commerce_batches WHERE batch_id = ?",
                (batch_id.strip(),),
            ).fetchone()
            return dict(row) if row else None

    def list_order_lines(
        self,
        *,
        platform: str | None = None,
        account_id: str | None = None,
        order_id: str | None = None,
        review_status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM commerce_order_lines"
        filters: list[str] = []
        params: list[Any] = []

        if platform:
            filters.append("platform = ?")
            params.append(platform.strip().lower())
        if account_id:
            filters.append("account_id = ?")
            params.append(account_id.strip())
        if order_id:
            filters.append("order_id = ?")
            params.append(order_id.strip())
        if review_status:
            filters.append("review_status = ?")
            params.append(review_status.strip().lower())

        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, limit))

        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
