"""Shared fixtures and utilities for Scholar Catalog E2E opaque-box tests."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

# Ensure both UuMA and RSTV4 are in Python path
uuma_root = Path(__file__).resolve().parents[2]
rstv4_root = uuma_root.parent / "RSTV4"
if str(uuma_root / "src") not in sys.path:
    sys.path.insert(0, str(uuma_root / "src"))
if str(rstv4_root / "src") not in sys.path:
    sys.path.insert(0, str(rstv4_root / "src"))

from rstv4.catalog_understanding import CatalogUnderstanding
from rstv4.database import initialize_catalog, transaction
from rstv4.paper_understanding import understanding_profile

# Extended database schemas
SCHEMA_THEME_CORRECTIONS = """
CREATE TABLE IF NOT EXISTS catalog_theme_corrections (
  correction_seq INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL UNIQUE,
  request_json TEXT NOT NULL,
  base_observation_id TEXT NOT NULL REFERENCES catalog_theme_observations(observation_id),
  revision INTEGER NOT NULL CHECK(revision > 0),
  operation TEXT NOT NULL CHECK(operation IN ('EDIT','RESTORE')),
  effective_observation_id TEXT NOT NULL REFERENCES catalog_theme_observations(observation_id),
  restored_revision INTEGER,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(base_observation_id, revision)
);
"""

SCHEMA_SKELETON_VIEWS = """
CREATE TABLE IF NOT EXISTS catalog_skeleton_view_requests (
  request_id TEXT PRIMARY KEY REFERENCES catalog_deep_requests(request_id),
  pipeline_json TEXT NOT NULL,
  content_job_id TEXT REFERENCES catalog_reading_jobs(job_id),
  purpose_job_id TEXT REFERENCES catalog_reading_jobs(job_id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_skeleton_content_views (
  view_id TEXT PRIMARY KEY,
  skeleton_id TEXT NOT NULL REFERENCES paper_skeletons(skeleton_id),
  job_id TEXT NOT NULL UNIQUE REFERENCES catalog_reading_jobs(job_id),
  source_digest TEXT NOT NULL,
  content_json TEXT NOT NULL,
  contracts_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_skeleton_purpose_judgments (
  judgment_id TEXT PRIMARY KEY,
  view_id TEXT NOT NULL REFERENCES catalog_skeleton_content_views(view_id),
  job_id TEXT NOT NULL UNIQUE REFERENCES catalog_reading_jobs(job_id),
  purpose_json TEXT NOT NULL,
  judgment_json TEXT NOT NULL,
  contract_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class MockEmbeddings:
    """Deterministic, BGE-M3 compliant vector generator for opaque-box E2E testing."""

    def __init__(self, generation: str = "fixture-v1", dimensions: int = 1024):
        self.generation = generation
        self.dimensions = dimensions
        self.calls: list[list[str]] = []
        self.hook: Callable[[], None] | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "owner": "alandelone-server-001",
            "model": "bge-m3",
            "dimensions": self.dimensions,
            "backend": "onnxruntime",
            "device": "cpu",
            "generation": self.generation,
        }

    def embed(self, texts: list[str], identity: dict[str, Any]) -> list[list[float]]:
        assert identity == self.describe(), f"Identity mismatch: {identity} vs {self.describe()}"
        self.calls.append(list(texts))
        if self.hook is not None:
            self.hook()

        vectors = []
        for text in texts:
            # Deterministic pseudo-random vector based on text hash
            seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            vec = rng.normal(size=self.dimensions).astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec.tolist())
        return vectors


def default_card(themes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    dims = [
        {"key": d["key"], "state": "NOT_ASSESSED", "evidence": []}
        for d in understanding_profile()["dimensions"]
    ]
    return {
        "reading_disposition": "INITIAL_SUFFICIENT",
        "disposition_rationale": "Initial overview answers the research scope.",
        "dimensions": dims,
        "deep_read_reasons": [],
        "themes": themes or [
            {
                "label": "Decentralized Governance",
                "definition": "Distribution of decision authority across network participants.",
                "role": "CENTRAL",
                "evidence": [{"block_id": "b1", "quote": "decentralized governance"}],
            },
            {
                "label": "Energy Trading",
                "definition": "Peer-to-peer energy exchange mechanisms in smart grids.",
                "role": "SUBSTANTIAL",
                "evidence": [{"block_id": "b1", "quote": "energy trading"}],
            },
        ],
    }


def make_paper_source(
    root: Path,
    paper_id: str,
    title: str = "Test Research Paper",
    text: str = "We study decentralized governance and energy trading mechanisms.",
    themes: list[dict[str, Any]] | None = None,
    with_understanding: bool = True,
) -> dict[str, Any]:
    """Helper to populate canonical catalog.db with valid paper, source file, parse run, and blocks."""
    db_path = root / "data" / "catalog.db"
    pdf_path = root / f"{paper_id}.pdf"
    content = b"%PDF-1.4\n1 0 obj\n<< /Title (" + title.encode() + b") >>\nendobj\n" + text.encode()
    pdf_path.write_bytes(content)
    pdf_sha = hashlib.sha256(content).hexdigest()
    pdf_size = len(content)

    with transaction(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO papers VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (paper_id, paper_id, None, title, title.lower(), "[\"Dr. Jane Doe\"]", 2026,
             None, None, None, "2026-11-04T00:00:00Z", "2026-11-04T00:00:00Z"),
        )
        conn.execute(
            """INSERT OR REPLACE INTO source_file_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (f"{paper_id}-file", paper_id, pdf_sha, pdf_size, "application/pdf", str(pdf_path),
             "FIXTURE", None, "VERIFIED", "{}", "2026-11-04T00:00:00Z"),
        )
        conn.execute(
            """INSERT OR REPLACE INTO parse_runs VALUES(?,?,?,?,?,?,?,?,?)""",
            (f"{paper_id}-parse", f"{paper_id}-file", "fixture-parser", "1.0", "config-digest",
             "SUCCEEDED", "{}", "2026-11-04T00:00:00Z", "2026-11-04T00:00:00Z"),
        )
        block_id = f"{paper_id}-b1"
        block_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        conn.execute(
            """INSERT OR REPLACE INTO document_blocks VALUES(?,?,?,?,?,?,?,?,?)""",
            (block_id, f"{paper_id}-parse", 0, 1, "Introduction", "TEXT", text, "{}", block_sha),
        )

    store = CatalogUnderstanding(root)
    card = default_card(themes)
    for theme in card["themes"]:
        theme["evidence"][0]["block_id"] = block_id
        if theme["evidence"][0]["quote"] not in text:
            theme["evidence"][0]["quote"] = text[:30]

    published = None
    if with_understanding:
        published = store.publish_initial(
            paper_id=paper_id,
            parse_run_id=f"{paper_id}-parse",
            card=card,
            contract={"prompt_version": "quick-read-v2-paperskeleton", "actual_model": "software-fixture"},
            publication_key=f"{paper_id}-initial",
            purpose={"kind": "LIBRARY_OVERVIEW"},
        )

    return {
        "paper_id": paper_id,
        "title": title,
        "pdf_path": pdf_path,
        "pdf_sha": pdf_sha,
        "block_id": f"{paper_id}-b1",
        "text": text,
        "published": published,
        "store": store,
    }


def populate_skeleton_l1_to_l4(
    root: Path,
    paper_id: str,
    propositions: list[dict[str, Any]] | None = None,
    relations: list[dict[str, Any]] | None = None,
    intents: list[dict[str, Any]] | None = None,
    macro_role: str = "Result_Performance",
) -> dict[str, Any]:
    """Helper to populate genuine L1-L4 skeleton units for a paper."""
    db_path = root / "data" / "catalog.db"
    pv_id = f"{paper_id}-pv1"
    skeleton_id = f"{paper_id}-skel1"
    unit_id = f"{paper_id}-unit1"

    l1 = {
        "propositions": propositions or [
            {
                "atom_id": f"{paper_id}-a1",
                "statement": "Energy consensus improves settlement latency by 45%.",
                "quote": "improves settlement latency",
                "source_span": [10, 45],
            }
        ]
    }
    l2 = {"relations": relations or []}
    l3 = {
        "intents": intents or [
            {
                "atom_id": f"{paper_id}-a1",
                "primary": "Objective_Finding",
                "secondary": ["Method_Contribution"],
                "rationale": "Empirical latency measurement verified across test nodes.",
            }
        ]
    }

    with transaction(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO paper_versions (paper_version_id, paper_id, version, pdf_path,
               pdf_digest, parsed_path, parsed_digest, source_json, created_at)
               VALUES (?, ?, 1, NULL, 'fixture-pdf-sha', NULL, 'fixture-text-sha', ?, '2026-11-04T00:00:00Z')""",
            (pv_id, paper_id, json.dumps({"parse_run_id": f"{paper_id}-parse", "file_version_id": f"{paper_id}-file"})),
        )
        conn.execute(
            """INSERT OR REPLACE INTO paper_skeletons (skeleton_id, paper_version_id, version, extractor_model, prompt_version, content_digest, created_at)
               VALUES (?, ?, 1, 'fixture-deep-model', 'fixture-prompt-l1-l4', 'full-content-sha', '2026-11-04T00:00:00Z')""",
            (skeleton_id, pv_id),
        )
        conn.execute(
            """INSERT OR REPLACE INTO skeleton_units (unit_id, skeleton_id, seq_idx, page_idx, section, raw_text,
               layer1_json, layer2_json, layer3_json, layer4, content_digest)
               VALUES (?, ?, 0, 1, 'Evaluation', 'Raw evaluation text citation.', ?, ?, ?, ?, 'unit-sha256')""",
            (unit_id, skeleton_id, json.dumps(l1), json.dumps(l2), json.dumps(l3), macro_role),
        )

    return {
        "skeleton_id": skeleton_id,
        "pv_id": pv_id,
        "unit_id": unit_id,
        "layer1": l1,
        "layer2": l2,
        "layer3": l3,
        "layer4": macro_role,
    }


def create_sealed_evidence_archive(root: Path, archive_path: Path) -> dict[str, Any]:
    """Helper to build an authentic sealed ZIP evidence archive with stage-manifest.json."""
    db_path = root / "data" / "catalog.db"
    assert db_path.exists(), "Source catalog.db required to create archive"

    files_to_pack = {}
    with transaction(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for row in conn.execute("SELECT paper_id, storage_path, sha256 FROM source_file_versions"):
            p = Path(row["storage_path"])
            if p.exists():
                files_to_pack[f"sources/{row['paper_id']}.pdf"] = (p.read_bytes(), row["sha256"])

    db_bytes = db_path.read_bytes()
    db_sha = hashlib.sha256(db_bytes).hexdigest()
    files_to_pack["catalog.db"] = (db_bytes, db_sha)

    manifest_entries = {name: sha for name, (_bytes, sha) in files_to_pack.items()}
    manifest_payload = {
        "schema_version": 1,
        "stage": "STAGE_FULL_EVIDENCE_DELIVERY",
        "generator": "UuMA Scholar Evidence Packaging Carrier v546",
        "created_at": "2026-11-04T00:00:00Z",
        "artifacts": manifest_entries,
    }
    manifest_bytes = json.dumps(manifest_payload, indent=2).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("stage-manifest.json", manifest_bytes)
        for name, (data, _sha) in files_to_pack.items():
            zf.writestr(name, data)

    return {
        "archive_path": archive_path,
        "manifest_sha": manifest_sha,
        "files_count": len(files_to_pack) + 1,
        "manifest": manifest_payload,
    }


@pytest.fixture
def catalog_sandbox(tmp_path: Path):
    """Provides a pristine catalog sandbox with schema initialized and two sample papers."""
    db_dir = tmp_path / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "catalog.db"
    initialize_catalog(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_THEME_CORRECTIONS)
        conn.executescript(SCHEMA_SKELETON_VIEWS)

    embedder = MockEmbeddings()

    p1 = make_paper_source(
        tmp_path,
        paper_id="paper_dd83af8026e3",
        title="Decentralized Governance in Peer-to-Peer Energy Trading",
        text="We study decision authority and decentralized governance in energy trading markets. Consensus models enable settlement.",
        themes=[
            {
                "label": "Decentralized Governance",
                "definition": "Distribution of decision authority across network participants.",
                "role": "CENTRAL",
                "evidence": [{"block_id": "b1", "quote": "decentralized governance"}],
            },
            {
                "label": "Energy Trading",
                "definition": "Coordination of energy market exchanges.",
                "role": "SUBSTANTIAL",
                "evidence": [{"block_id": "b1", "quote": "energy trading"}],
            },
        ],
    )

    p2 = make_paper_source(
        tmp_path,
        paper_id="paper_fe192837465a",
        title="Scalable Microgrid Consensus Protocols for Smart Energy",
        text="A novel consensus protocol optimizing electricity settlements in microgrid networks. Decentralized governance ensures trust.",
        themes=[
            {
                "label": "Microgrid Consensus",
                "definition": "Consensus protocols designed for low-latency microgrid networks.",
                "role": "CENTRAL",
                "evidence": [{"block_id": "b1", "quote": "consensus protocol optimizing"}],
            },
            {
                "label": "Decentralized Governance",
                "definition": "Distribution of decision authority across network participants.",
                "role": "PASSING_MENTION",
                "evidence": [{"block_id": "b1", "quote": "Decentralized governance ensures"}],
            },
        ],
    )

    return {
        "root": tmp_path,
        "db_path": db_path,
        "embedder": embedder,
        "p1": p1,
        "p2": p2,
    }
