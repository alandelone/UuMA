import sys
from pathlib import Path
from uuid import uuid4

import pytest
from rstv4.approval import capture_user_approval
from rstv4.models import (
    DecisionProposalInput,
    EvidenceAssessmentInput,
    ExperimentPlanInput,
    ResearchProjectInput,
    ResearchType,
)
from rstv4.service import RSTV4Service


def make_service(tmp_path: Path) -> RSTV4Service:
    return RSTV4Service(tmp_path)


def grant(service: RSTV4Service, proposal: dict) -> None:
    capture_user_approval(
        service.root,
        profile="scholar",
        session_id="test-session",
        message_id=uuid4().hex,
        user_message=proposal["approval_phrase"],
    )


def test_experiment_and_evidence_lifecycle(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project(
        ResearchProjectInput(
            slug="radar-canopy",
            title="Radar canopy sensing",
            field="Agricultural sensing",
            research_type=ResearchType.ENGINEERING_SYSTEM,
            type_payload={
                key: {} for key in ("requirements", "system_design", "implementation", "validation")
            },
        )
    )

    method = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(
            kind="method", statement="Run a fixed calibration command.", rationale="Test"
        ),
    )
    grant(service, method)
    service.approve_scientific_decision("radar-canopy", method["proposal_id"], 1)
    plan = service.propose_experiment_plan(
        "radar-canopy",
        ExperimentPlanInput(
            method_node_id=method["node_id"],
            argv=[sys.executable, "-c", "print('ACCURACY=0.94')"],
        ),
    )
    with pytest.raises(PermissionError):
        service.run_experiment("radar-canopy", plan["plan_id"])
    grant(service, plan)
    service.approve_experiment_plan("radar-canopy", plan["plan_id"], 1)
    exp = service.run_experiment("radar-canopy", plan["plan_id"])
    assert exp["exit_code"] == 0
    assert "ACCURACY=0.94" in exp["stdout_preview"]

    # 2. Record experiment run as Evidence
    ev = service.record_experiment_evidence(
        "radar-canopy",
        exp["run_id"],
        statement="Sensor achieved 0.94 calibration accuracy under wet conditions.",
        confidence=0.95,
    )
    assert ev["statement"].startswith("Sensor achieved 0.94")

    # 3. Propose Claim supported by this experiment Evidence
    claim = service.propose_decision(
        "radar-canopy",
        DecisionProposalInput(
            kind="claim",
            statement="Canopy water content can be calibrated with >90% accuracy.",
            rationale="Supported by empirical experiment run",
            evidence_ids=[ev["evidence_id"]],
        ),
    )
    grant(service, claim)
    service.approve_scientific_decision("radar-canopy", claim["proposal_id"], 1)

    service.assess_claim_evidence(
        "radar-canopy",
        EvidenceAssessmentInput(
            claim_node_id=claim["node_id"],
            evidence_id=ev["evidence_id"],
            verdict="PARTIAL",
            rationale="The run supports this configuration but does not establish generality.",
            conditions=["wet conditions", "tested configuration"],
            assessor_model="test-assessor",
            prompt_version="v1",
        ),
    )

    # 4. Check Citation verification
    valid_text = f"As shown in calibration tests [{ev['evidence_id']}], accuracy exceeds 90%."
    verify_res = service.verify_citations("radar-canopy", valid_text)
    assert verify_res["is_resolvable"] is True
    assert verify_res["content_status"] == "ASSESSED"
    assert ev["evidence_id"] in verify_res["valid_citations"]

    invalid_text = "As shown in fictitious study [@doi:10.9999/fake], results are good."
    verify_res2 = service.verify_citations("radar-canopy", invalid_text)
    assert verify_res2["is_resolvable"] is False
    assert "doi:10.9999/fake" in verify_res2["invalid_citations"]

    # 5. Compile Manuscript
    manuscript = service.compile_manuscript(
        "radar-canopy",
        abstract="This paper presents a radar sensor for canopy moisture estimation.",
        sections=[{"title": "Results", "content": valid_text}],
    )
    assert "# Radar canopy sensing" in manuscript
    assert "## Abstract" in manuscript
    assert "## Results" in manuscript

    # 6. Simulate Peer Review
    review = service.simulate_review("radar-canopy")
    assert review["scientific_status"] == "NEEDS_HUMAN_REVIEW"
    assert "recommendations" in review
    assert "rebuttal_proposals" in review


def test_experiment_script_digest_is_rechecked(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_project(
        ResearchProjectInput(
            slug="digest-check",
            title="Digest check",
            field="Testing",
            research_type=ResearchType.ENGINEERING_SYSTEM,
            type_payload={
                key: {} for key in ("requirements", "system_design", "implementation", "validation")
            },
        )
    )
    method = service.propose_decision(
        "digest-check",
        DecisionProposalInput(kind="method", statement="Run pinned script", rationale="Test"),
    )
    grant(service, method)
    service.approve_scientific_decision("digest-check", method["proposal_id"], 1)
    project_dir = service.root / "projects" / "digest-check"
    script = project_dir / "experiment.py"
    script.write_text("print('first')\n", encoding="utf-8")
    import hashlib

    plan = service.propose_experiment_plan(
        "digest-check",
        ExperimentPlanInput(
            method_node_id=method["node_id"],
            argv=[sys.executable, str(script)],
            script_path="experiment.py",
            script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        ),
    )
    grant(service, plan)
    service.approve_experiment_plan("digest-check", plan["plan_id"], 1)
    script.write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(Exception, match="script changed"):
        service.run_experiment("digest-check", plan["plan_id"])
