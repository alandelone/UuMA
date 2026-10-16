"""Real compiler and typed acknowledgement of presentation, preserving prose guards."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_studio_layout_integration import branch, compiled_source, replay
from test_writing_studio import wait_for_job

from rstv4.service import RevisionConflictError
from rstv4.studio_api import create_app
from rstv4.studio_response_checks import validate_claims

__all__ = ["branch", "compiled_source"]  # Explicitly expose shared pytest fixtures.


def prepared(branch):
    service, ms, source, _ = branch
    review = service.create_review_round(ms, round_number=1, venue="Presentation software fixture")
    comment = service.import_comments(review["review_round_id"], [{"text": "Change only the margins."}], source="FIXTURE")[0]
    ws = service.get_workspace(ms)
    document = deepcopy(ws["document"])
    document["layout"] = {"page_margin": "narrow"}
    service.save_document(ms, base_revision=1, operation_id="presentation-linked-margin", document=document,
                          operation_kind="LAYOUT", comment_ids=[comment["comment_id"]])
    assert replay(service, ms, source)["status"] == "SUCCEEDED"
    text = "We changed only the margins."
    service.update_comment(comment["comment_id"], {"response_text": text, "author_decision": "Presentation only; original prose retained."})
    context = service.response_review_context(ms, comment["comment_id"])
    assert len(context["evidence"]) == 1 and context["evidence"][0]["status"] == "LAYOUT_ONLY"
    request = {"request_id": "presentation-review-native-contract", "context_sha256": context["context_sha256"],
               "outcome": "PRESENTATION_MODIFIED", "acknowledged_all_assertions": True,
               "claims": [{"start": 0, "end": len(text), "text": text, "offset_unit": "utf16",
                           "evidence_ids": [context["evidence"][0]["evidence_id"]]}]}
    return service, ms, comment["comment_id"], context, request, document


@pytest.fixture(scope="module")
def exact_context(compiled_source, tmp_path_factory):
    # Share a real compiled context for pure negative validation; mutate only deep copies.
    from test_studio_layout_integration import branch as branch_fixture

    generator = branch_fixture.__wrapped__(compiled_source, tmp_path_factory.mktemp("presentation-context"))
    context_branch = next(generator)
    try:
        yield prepared(context_branch)[3:5]
    finally:
        try:
            next(generator)
        except StopIteration:
            pass


@pytest.mark.parametrize("invalid", ["scientific_outcome", "no_claim", "unacknowledged", "prose_changed",
    "unknown_baseline", "retained", "wrong_kind", "scientific_support", "missing_old_boxes",
    "unmoved_boxes", "same_pdf", "wrong_target", "wrong_baseline", "wrong_pdf", "wrong_text", "duplicate"])
def test_presentation_never_bypasses_fixed_pdf_exact_reply_and_type_guards(exact_context, invalid):
    original, original_request = exact_context
    context, request = deepcopy(original), deepcopy(original_request)
    row = context["evidence"][0]
    if invalid == "scientific_outcome":
        request["outcome"] = "MODIFIED"
        context["baseline_to_target_diff"] = "Pretend prose change"
    elif invalid == "no_claim":
        request["claims"] = []
    elif invalid == "unacknowledged":
        request["acknowledged_all_assertions"] = False
    elif invalid == "prose_changed":
        context["baseline_to_target_diff"] = "Actual changed prose"
    elif invalid == "unknown_baseline":
        context["baseline_available"] = False
    elif invalid == "retained":
        row["status"] = "EXACT_BASELINE_TEXT_RETAINED"
    elif invalid == "wrong_kind":
        row["change_kind"] = "CITATION"
    elif invalid == "scientific_support":
        row["supports_scientific_text_modification"] = True
    elif invalid == "missing_old_boxes":
        row["baseline_boxes"] = []
    elif invalid == "unmoved_boxes":
        row["baseline_boxes"] = row["boxes"]
    elif invalid == "same_pdf":
        row["baseline_pdf_sha256"] = row["final_pdf_sha256"]
    elif invalid == "wrong_target":
        row["generated_version_id"] = "another-target"
    elif invalid == "wrong_baseline":
        row["baseline_version_id"] = "another-baseline"
    elif invalid == "wrong_pdf":
        row["final_pdf_sha256"] = "f" * 64
    elif invalid == "wrong_text":
        request["claims"][0]["text"] = "Not the saved reply"
    else:
        request["claims"][0]["evidence_ids"] *= 2
    with pytest.raises(ValueError):
        validate_claims(context, request["outcome"], request["claims"], request["acknowledged_all_assertions"])


def test_presentation_http_confirmation_replay_export_and_later_reply_staleness(branch):
    service, ms, comment, context, request, _ = prepared(branch)
    route = f"/api/manuscripts/{ms}/comments/{comment}/response-checks"
    with TestClient(create_app(service.root)) as client:
        response = client.post(route, json=request)
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["comment"]["response_verification"]["status"] == "CURRENT"
        assert first["comment"]["response_verification"]["outcome"] == "PRESENTATION_MODIFIED"
        assert first["history"][0]["context"]["evidence"] == context["evidence"]
        retry = client.post(route, json=request)
        assert retry.status_code == 200 and retry.json()["idempotent_replay"]
        assert retry.json()["check_id"] == first["check_id"] and len(retry.json()["history"]) == 1
    package = wait_for_job(service, service.create_job(ms, "SUBMISSION_PACKAGE", input_revision=2))
    assert package["status"] == "SUCCEEDED", package
    exported = json.loads((Path(package["result"]["directory"])/"response-review-history.json").read_text(encoding="utf8"))
    assert exported["comments"][0]["checks"] == first["history"]
    assert package["result"]["manifest"]["unresolved_comment_ids"] == []
    service.update_comment(comment, {"response_text": "A later reply."})
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "STALE"
    assert service.response_review_history(ms, comment)["history"] == first["history"]
    assert service.confirm_response_review(ms, comment, request)["idempotent_replay"]
    with pytest.raises(RevisionConflictError):
        service.confirm_response_review(ms, comment, {**request,"outcome":"MODIFIED"})
