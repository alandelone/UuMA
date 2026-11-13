"""Nightly Automated LSIP Semantic Extraction and Catalog Publishing CLI.

Executes during the 22:00 - 04:00 MYT overnight window to:
1. Ingest deterministic deltas (Yonc Graph, Brainstormer Audits, UuMA Control events).
2. Ingest active conversational episodes (Antigravity transcripts, Codex rollouts).
3. Enforce Honc privacy boundary (quarantining diary entries, indexing habits only).
4. Atomically dual-publish librarian_semantic_catalog.json and catalog.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .librarian_conversational_adapter import ConversationalSourceAdapter
from .librarian_honc_adapter import HoncPrivacyAdapter
from .librarian_semantic_db import init_semantic_db
from .librarian_semantic_pipeline import (
    SemanticPipelineCoordinator,
    atomic_publish_semantic_catalog,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("librarian.nightly")


def run_nightly_pipeline(
    semantic_db_path: Path,
    catalog_output_dir: Path,
    sources_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute complete semantic extraction and catalog publication."""
    start_time = time.time()
    logger.info("Starting Librarian LSIP Nightly Pipeline at %s", datetime.now(UTC).isoformat())

    conn = init_semantic_db(semantic_db_path)
    coordinator = SemanticPipelineCoordinator(conn)

    # Register additional adapters
    coordinator.register_adapter(HoncPrivacyAdapter("honc-database"))
    coordinator.register_adapter(ConversationalSourceAdapter("antigravity-core", default_category="Experience"))
    coordinator.register_adapter(ConversationalSourceAdapter("codex-sessions", default_category="Experience"))

    extracted_counts: dict[str, int] = {}
    config = sources_config or {}

    # 1. Deterministic Yonc Graph DB
    yonc_db = config.get("yonc_db")
    if yonc_db and Path(yonc_db).exists():
        logger.info("Ingesting Yonc Graph DB from %s...", yonc_db)
        try:
            records = coordinator.run_adapter("yonc-graph", Path(yonc_db), project="yonc-graph")
            extracted_counts["yonc-graph"] = len(records)
        except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as e:
            logger.error("Failed to ingest Yonc Graph: %s", e)
            extracted_counts["yonc-graph"] = 0

    # 2. UuMA Control DB
    uuma_db = config.get("uuma_db")
    if uuma_db and Path(uuma_db).exists():
        logger.info("Ingesting UuMA Control DB from %s...", uuma_db)
        try:
            records = coordinator.run_adapter("uuma-control", Path(uuma_db), project="UuMA")
            extracted_counts["uuma-control"] = len(records)
        except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as e:
            logger.error("Failed to ingest UuMA Control: %s", e)
            extracted_counts["uuma-control"] = 0

    # 3. Brainstormer State JSON
    brainstormer_json = config.get("brainstormer_json")
    if brainstormer_json and Path(brainstormer_json).exists():
        logger.info("Ingesting Brainstormer state from %s...", brainstormer_json)
        try:
            records = coordinator.run_adapter(
                "brainstormer-structured-files",
                Path(brainstormer_json),
                project="brainstormer",
            )
            extracted_counts["brainstormer"] = len(records)
        except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as e:
            logger.error("Failed to ingest Brainstormer: %s", e)
            extracted_counts["brainstormer"] = 0

    # 4. Antigravity transcripts (if directory configured)
    agy_dir = config.get("antigravity_transcripts_dir")
    if agy_dir and Path(agy_dir).exists():
        logger.info("Scanning Antigravity transcripts in %s...", agy_dir)
        agy_count = 0
        for f in Path(agy_dir).rglob("transcript.jsonl"):
            try:
                recs = coordinator.run_adapter("antigravity-core", f, project="antigravity")
                agy_count += len(recs)
            except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as e:
                logger.warning("Failed to extract %s: %s", f.name, e)
        extracted_counts["antigravity-core"] = agy_count

    # 5. Codex rollouts (if directory configured)
    codex_dir = config.get("codex_sessions_dir")
    if codex_dir and Path(codex_dir).exists():
        logger.info("Scanning Codex rollouts in %s...", codex_dir)
        codex_count = 0
        for f in sorted(Path(codex_dir).rglob("rollout-*.jsonl"), reverse=True)[:20]:
            try:
                recs = coordinator.run_adapter("codex-sessions", f, project="codex")
                codex_count += len(recs)
            except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as e:
                logger.warning("Failed to extract %s: %s", f.name, e)
        extracted_counts["codex-sessions"] = codex_count

    # 6. Honc entries (if configured)
    honc_file = config.get("honc_file")
    if honc_file and Path(honc_file).exists():
        logger.info("Ingesting Honc entries from %s...", honc_file)
        try:
            recs = coordinator.run_adapter("honc-database", Path(honc_file), project="honc")
            extracted_counts["honc-database"] = len(recs)
        except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as e:
            logger.error("Failed to ingest Honc: %s", e)
            extracted_counts["honc-database"] = 0

    # 7. Export unified semantic catalog
    logger.info("Exporting unified catalog from semantic database...")
    catalog_dict = coordinator.export_catalog()
    catalog_records = catalog_dict.get("records", [])

    # Dual-publish atomic files
    atomic_publish_semantic_catalog(catalog_dict, catalog_output_dir)
    logger.info(
        "Successfully dual-published %d semantic records to %s",
        len(catalog_records),
        catalog_output_dir,
    )

    elapsed = round(time.time() - start_time, 2)
    summary = {
        "status": "success",
        "elapsed_seconds": elapsed,
        "extracted_counts": extracted_counts,
        "total_catalog_records": len(catalog_records),
        "exported_at": datetime.now(UTC).isoformat(),
    }
    logger.info("Nightly pipeline completed: %s", json.dumps(summary))
    conn.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Librarian LSIP Nightly Pipeline")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(".uuma-local/librarian_semantic.db"),
        help="Path to librarian_semantic.db",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".uuma-local/catalog"),
        help="Directory to publish librarian_semantic_catalog.json",
    )
    parser.add_argument("--config", type=Path, default=None, help="JSON configuration with source paths")
    args = parser.parse_args()

    config = {}
    if args.config and args.config.exists():
        config = json.loads(args.config.read_text(encoding="utf-8"))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = run_nightly_pipeline(args.db, args.output_dir, sources_config=config)
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
