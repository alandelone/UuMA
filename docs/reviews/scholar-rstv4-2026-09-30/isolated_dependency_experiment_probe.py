from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

from rstv4.approval import capture_user_approval
from rstv4.models import (
    DecisionProposalInput, ExperimentPlanInput, FieldInput,
    TrackFirstTopicInput, TrackFirstTrackInput, TrackFirstManuscriptInput,
)
from rstv4.track_first import TrackFirstService
from rstv4.studio import StudioService

OUTPUT = Path(__file__).parent / "scholar-acceptance-results.json"
PRODUCTION = Path(__file__).resolve().parents[4] / "RSTV4/data/catalog.db"

def approve(service: TrackFirstService, proposal: dict) -> dict:
    capture_user_approval(service.root, profile="scholar", session_id="acceptance-test-only",
                          message_id=uuid4().hex, user_message=proposal["approval_phrase"])
    return service.approve_decision(proposal["proposal_id"], 1)

def main() -> None:
    result: dict = {"production_database_access": "read-only"}
    with sqlite3.connect(PRODUCTION.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        names = ("papers", "research_fields", "topics", "research_tracks", "projects", "manuscripts",
                 "collections", "acquisition_jobs", "parse_runs", "paper_skeletons", "fieldkg_builds",
                 "fieldkg_snapshots", "evidence", "decisions", "projection_outbox")
        result["production_counts"] = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in names if table in tables
        }
    root = Path(mkdtemp(prefix="scholar-acceptance-", dir=Path(__file__).parent))
    service = TrackFirstService(root)
    field = service.create_field(FieldInput(name="验收测试 · 独立测试库"))
    topic = service.create_topic(TrackFirstTopicInput(field_id=field["field_id"], name="测试 Topic"))
    track = service.create_track(TrackFirstTrackInput(field_id=field["field_id"],
                primary_topic_id=topic["topic_id"], title="验收测试 Track", research_type="engineering_system"))
    track_id = track["track_id"]
    original = approve(service, service.propose_decision(track_id, DecisionProposalInput(
        kind="method", statement="Original approved method", rationale="Isolated acceptance probe")))
    dependent = approve(service, service.propose_decision(track_id, DecisionProposalInput(
        kind="research_question", statement="Question depending on original method",
        rationale="Dependency propagation acceptance probe", upstream_node_ids=[original["node_id"]])))
    manuscript = service.create_manuscript(TrackFirstManuscriptInput(track_id=track_id,
                title="验收测试稿件 · 不属于生产研究", node_ids=[dependent["node_id"]]))
    plan = service.propose_experiment_plan(track_id, ExperimentPlanInput(method_node_id=original["node_id"],
                argv=[sys.executable, "-c", "print('ISOLATED_ACCEPTANCE_ONLY')"]))
    capture_user_approval(root, profile="scholar", session_id="acceptance-test-only",
                          message_id=uuid4().hex, user_message=plan["approval_phrase"])
    service.approve_experiment_plan(plan["plan_id"], 1)
    replacement = approve(service, service.propose_decision(track_id, DecisionProposalInput(
        kind="method", statement="Replacement method", rationale="Supersession acceptance probe",
        supersedes_node_id=original["node_id"])))
    impacts = service.impact_analysis(original["node_id"])
    paper_after = service.get_manuscript(manuscript["manuscript_id"])
    result["supersession_probe"] = {
        "original_status": service.get_decision(original["proposal_id"])["status"],
        "dependent_status": service.get_decision(dependent["proposal_id"])["status"],
        "impact_node_statuses": [node["status"] for node in impacts],
        "dependent_manuscript_needs_scientific_review": paper_after["needs_scientific_review"],
        "expected": "dependent STALE and dependent manuscript needs_scientific_review=1",
    }
    try:
        run = service.run_experiment(plan["plan_id"])
        result["superseded_method_run_probe"] = {
            "blocked": False, "exit_code": run["exit_code"],
            "stdout": run["stdout_preview"].strip(),
            "expected": "reject execution after method supersession",
        }
    except Exception as exc:
        result["superseded_method_run_probe"] = {"blocked": True, "exception": type(exc).__name__}
    studio = StudioService(root)
    workspace = studio.create_manuscript(track_id, "界面验收测试稿件 · 独立测试库")
    result["isolated_fixture"] = {"root": str(root), "track_id": track_id,
                                  "manuscript_id": workspace["manuscript"]["manuscript_id"]}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
