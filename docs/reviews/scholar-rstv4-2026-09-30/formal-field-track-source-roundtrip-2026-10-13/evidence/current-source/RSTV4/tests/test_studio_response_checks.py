from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_studio_revision_mapping import package_fixture
from test_writing_studio import wait_for_job

from rstv4.database import transaction
from rstv4.service import NotFoundError, RevisionConflictError, RSTV4Error
from rstv4.studio_api import create_app
from rstv4.studio_response_checks import validate_claims


def prepared(tmp_path):
    service, manuscript_id, opinion, _, document, _, _, directory, _ = package_fixture(tmp_path)
    service.update_comment(opinion["comment_id"], {"author_decision": "Accept the requested toolbar change.",
                                               "response_text": "✅ We changed the toolbar count. No study is conducted."})
    context = service.response_review_context(manuscript_id, opinion["comment_id"])
    changed = next(item for item in context["evidence"] if item["status"] == "GENERATED_TEXT_CHANGED")
    text = "We changed the toolbar count."
    start = len("✅ ".encode("utf-16-le")) // 2
    request = {"request_id": "response-review-test-1", "context_sha256": context["context_sha256"], "outcome": "MODIFIED",
               "claims": [{"start": start, "end": start + len(text), "text": text, "offset_unit": "utf16",
                           "evidence_ids": [changed["evidence_id"]]}], "acknowledged_all_assertions": True}
    return service, manuscript_id, opinion["comment_id"], context, request, document, directory


def test_reply_is_not_completed_by_status_shortcut_and_explicit_check_binds_actual_pdf(tmp_path):
    service, ms, comment, context, request, _, directory = prepared(tmp_path)
    with pytest.raises(ValueError, match="explicit"):
        service.update_comment(comment, {"status": "RESOLVED"})
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "NOT_REVIEWED"
    original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
    result = service.confirm_response_review(ms, comment, request)
    assert result["comment"]["status"] == "RESOLVED"
    assert result["comment"]["response_verification"]["status"] == "CURRENT"
    check = result["history"][0]
    assert check["context"]["state"] == context["state"]
    assert check["context"]["evidence"][0]["final_page"] == 1
    assert check["context"]["evidence"][0]["boxes"]
    assert not check["context"]["scientific_acceptance"]
    assert original == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}


@pytest.mark.parametrize("invalid", ["retained", "unrelated", "overlap", "unicode", "text", "unacknowledged", "no_diff"])
def test_assertions_require_exact_saved_selection_and_actual_changed_location(tmp_path, invalid):
    _, _, _, context, request, _, _ = prepared(tmp_path)
    claims = deepcopy(request["claims"])
    acknowledged = True
    if invalid == "retained":
        claims[0]["evidence_ids"] = [next(row["evidence_id"] for row in context["evidence"] if row["status"] == "EXACT_BASELINE_TEXT_RETAINED")]
    elif invalid == "unrelated":
        claims[0]["evidence_ids"] = ["foreign-evidence"]
    elif invalid == "overlap":
        claims.append(deepcopy(claims[0]))
    elif invalid == "unicode":
        context["state"]["response_text"] = "😀changed"
        claims[0].update(start=1, end=2, text="x")
    elif invalid == "text":
        claims[0]["text"] = "Not the saved reply"
    elif invalid == "unacknowledged":
        acknowledged = False
    else:
        context["baseline_to_target_diff"] = ""
    with pytest.raises(ValueError):
        validate_claims(context, "MODIFIED", claims, acknowledged)


def test_legacy_unknown_mapping_cannot_be_confirmed_as_implemented(tmp_path):
    service, ms, opinion, _, _, _, _, _, _ = package_fixture(tmp_path, sentences=False)
    service.update_comment(opinion["comment_id"], {"author_decision": "Accept", "response_text": "Changed"})
    context = service.response_review_context(ms, opinion["comment_id"])
    assert context["evidence"][0]["status"] == "SENTENCE_MAPPING_UNKNOWN"
    claim = {"start": 0, "end": 7, "text": "Changed", "offset_unit": "utf16", "evidence_ids": [context["evidence"][0]["evidence_id"]]}
    with pytest.raises(ValueError, match="unknown"):
        validate_claims(context, "MODIFIED", [claim], True)


def test_changed_reply_restored_reply_reopen_and_retry_preserve_old_check(tmp_path):
    service, ms, comment, context, request, _, _ = prepared(tmp_path)
    first = service.confirm_response_review(ms, comment, request)
    service.update_comment(comment, {"response_text": "Later reply"})
    service.update_comment(comment, {"response_text": context["state"]["response_text"]})
    current = service.list_comments(ms)[0]
    assert current["status"] == "VERIFY" and current["response_verification"]["status"] == "STALE"
    replay = service.confirm_response_review(ms, comment, request)
    assert replay["idempotent_replay"] and replay["check_id"] == first["check_id"]
    assert replay["comment"]["status"] == "VERIFY" and len(replay["history"]) == 1
    assert replay["history"][0] == first["history"][0]
    with pytest.raises(RevisionConflictError, match="different decision"):
        service.confirm_response_review(ms, comment, {**request, "outcome": "EXPLAINED_NO_CHANGE", "claims": []})
    fresh = service.response_review_context(ms, comment)
    second = service.confirm_response_review(ms, comment, {**request, "request_id": "response-review-test-2", "context_sha256": fresh["context_sha256"]})
    assert len(second["history"]) == 2 and second["history"][0] == first["history"][0]
    service.update_comment(comment, {"status": "VERIFY"})
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "STALE"


def test_author_revision_archive_and_association_reversal_invalidate_exact_review(tmp_path):
    service, ms, comment, _, request, document, _ = prepared(tmp_path)
    first = service.confirm_response_review(ms, comment, request)
    change = next(item for item in service.list_changes(ms) if comment in item["comment_ids"])
    unlinked = service.set_change_links(ms, change["change_id"], request_id="reply-unlink-test", expected_link_revision=change["association_revision"], comment_ids=[])
    service.set_change_links(ms, change["change_id"], request_id="reply-relink-test", expected_link_revision=unlinked["change"]["association_revision"], comment_ids=[comment], reverses_event_id=unlinked["event"]["event_id"])
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "STALE"
    context = service.response_review_context(ms, comment)
    second = service.confirm_response_review(ms, comment, {**request, "request_id": "reply-after-link-test", "context_sha256": context["context_sha256"]})
    service.archive_comment(comment)
    service.archive_comment(comment, restore=True)
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "STALE"
    document["title"] = "Changed later author title"
    service.save_document(ms, base_revision=2, operation_id="reply-author-later", document=document)
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "STALE"
    context = service.response_review_context(ms, comment)
    with pytest.raises(RevisionConflictError, match="Generate"):
        service.confirm_response_review(ms, comment, {**request, "request_id": "reply-stale-author-test", "context_sha256": context["context_sha256"]})
    assert second["history"][0] == first["history"][0]


def test_stale_confirmation_and_reply_cas_cannot_override_concurrent_reply(tmp_path):
    service, ms, comment, _, request, _, _ = prepared(tmp_path)
    original = service.list_comments(ms)[0]
    barrier = Barrier(2)
    def edit(value):
        barrier.wait()
        try:
            return service.update_comment(comment, {"response_text": value, "expected_content_sha256": original["content_sha256"]})
        except RevisionConflictError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["Tab one saved reply", "Tab two saved reply"]))
    assert results.count("conflict") == 1
    assert service.list_comments(ms)[0]["response_text"] in {"Tab one saved reply", "Tab two saved reply"}
    with pytest.raises(RevisionConflictError, match="reopen"):
        service.confirm_response_review(ms, comment, request)


def test_no_change_explanation_requires_reason_and_is_exported_with_immutable_checks(tmp_path):
    service, ms, comment, _, _, _, directory = prepared(tmp_path)
    service.update_comment(comment, {"response_text": "We retained the original disclaimer because no study was conducted.", "author_decision": "Decline additional study claims; this is a software fixture."})
    context = service.response_review_context(ms, comment)
    request = {"request_id": "no-change-reply-test", "context_sha256": context["context_sha256"], "outcome": "EXPLAINED_NO_CHANGE", "claims": [], "acknowledged_all_assertions": True}
    check = service.confirm_response_review(ms, comment, request)
    package = wait_for_job(service, service.create_job(ms, "SUBMISSION_PACKAGE", input_revision=2))
    assert package["status"] == "SUCCEEDED", package
    report = json.loads((Path(package["result"]["directory"]) / "response-review-history.json").read_text(encoding="utf-8"))
    assert report["comments"][0]["checks"] == check["history"]
    assert package["result"]["manifest"]["unresolved_comment_ids"] == []
    assert (directory / "unresolved-comments.json").read_text(encoding="utf-8") != "[]"
    service.update_comment(comment, {"author_decision": ""})
    fresh = service.response_review_context(ms, comment)
    with pytest.raises(ValueError, match="reason"):
        service.confirm_response_review(ms, comment, {**request, "request_id": "empty-reason-reply", "context_sha256": fresh["context_sha256"]})


def test_legacy_resolved_is_exported_as_unverified_and_packaging_rejects_midflight_reply_change(tmp_path, monkeypatch):
    service, ms, comment, _, _, _, _ = prepared(tmp_path)
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE review_comments SET status='RESOLVED' WHERE comment_id=?", (comment,))
    assert service.list_comments(ms)[0]["response_verification"]["status"] == "LEGACY_UNVERIFIED"
    legacy_package = wait_for_job(service, service.create_job(ms, "SUBMISSION_PACKAGE", input_revision=2))
    assert legacy_package["status"] == "SUCCEEDED", legacy_package
    assert legacy_package["result"]["manifest"]["unresolved_comment_ids"] == [comment]
    exported = json.loads((Path(legacy_package["result"]["directory"]) / "response-review-history.json").read_text(encoding="utf-8"))
    assert exported["comments"][0]["verification"]["status"] == "LEGACY_UNVERIFIED"
    assert exported["comments"][0]["checks"] == []
    package_count = len(service.list_submission_packages(ms))
    original = service._verified_artifact_bytes
    changed = False
    def read_and_edit(artifact):
        nonlocal changed
        raw = original(artifact)
        if not changed:
            changed = True
            service.update_comment(comment, {"response_text": "Changed during package creation"})
        return raw
    monkeypatch.setattr(service, "_verified_artifact_bytes", read_and_edit)
    job = wait_for_job(service, service.create_job(ms, "SUBMISSION_PACKAGE", input_revision=2))
    assert job["status"] == "FAILED" and "changed during packaging" in job["error"]["message"]
    assert len(service.list_submission_packages(ms)) == package_count


def test_owned_api_strict_unicode_selection_and_historical_retry(tmp_path):
    service, ms, comment, _, request, _, _ = prepared(tmp_path)
    with pytest.raises(NotFoundError):
        service.response_review_context("wrong-manuscript", comment)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/manuscripts/wrong-manuscript/comments/{comment}/response-review").status_code == 404
        url = f"/api/manuscripts/{ms}/comments/{comment}/response-checks"
        invalid = deepcopy(request)
        invalid["claims"][0]["start"] = True
        assert client.post(url, json=invalid).status_code == 422
        assert client.post(url, json={**request, "acknowledged_all_assertions": "true"}).status_code == 422
        first = client.post(url, json=request)
        assert first.status_code == 200, first.text
        assert client.post(url, json=request).json()["idempotent_replay"]
        assert client.post(f"/api/manuscripts/wrong-manuscript/comments/{comment}/response-checks", json=request).status_code == 404


def test_archived_history_is_owned_and_readable_without_current_pdf(tmp_path, monkeypatch):
    service, ms, comment, _, request, _, _ = prepared(tmp_path)
    confirmed = service.confirm_response_review(ms, comment, request)
    service.archive_comment(comment)
    def unavailable(artifact):
        raise RSTV4Error("Current compiled artifact is unavailable")
    monkeypatch.setattr(service, "_verified_artifact_bytes", unavailable)
    with pytest.raises(RSTV4Error, match="unavailable"):
        service.response_review_context(ms, comment)
    assert service.response_review_history(ms, comment)["history"] == confirmed["history"]
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/manuscripts/{ms}/comments/{comment}/response-checks").json()["history"] == confirmed["history"]
        assert client.get(f"/api/manuscripts/wrong-ms/comments/{comment}/response-checks").status_code == 404
