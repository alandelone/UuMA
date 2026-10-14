from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from rstv4.database import transaction
from rstv4.service import NotFoundError, RevisionConflictError
from rstv4.studio_api import create_app
from test_writing_studio import complete_document, create_studio


def fixture(tmp_path: Path, *, linked=False):
    service, track_id, manuscript_id = create_studio(tmp_path)
    round_row = service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
    comments = service.import_comments(round_row["review_round_id"],
        [{"text": f"Fixture opinion {i}", "include": True} for i in [1, 2]], source="FIXTURE")
    document = complete_document(service.get_workspace(manuscript_id))
    ids = [item["comment_id"] for item in comments]
    service.save_document(manuscript_id, base_revision=0, operation_id="original-author-save",
                          document=document, comment_ids=ids if linked else [])
    change = service.list_changes(manuscript_id)[0]
    return service, track_id, manuscript_id, comments, document, change


def assign(service, manuscript_id, change, comment_ids, *, request_id="late-association-1", revision=None, reverse=None):
    return service.set_change_links(manuscript_id, change["change_id"], request_id=request_id,
        expected_link_revision=change["association_revision"] if revision is None else revision,
        comment_ids=comment_ids, reverses_event_id=reverse)


def test_unassigned_edit_can_be_assigned_to_multiple_comments_without_rewriting_originals(tmp_path: Path):
    service, _, manuscript_id, comments, document, change = fixture(tmp_path)
    assert change["comment_ids"] == [] and change["association_origin"] == "recorded_at_save"
    assert "+想法：The author decides the central scientific claim." in change["author_diff"]
    ids = [item["comment_id"] for item in comments]
    result = assign(service, manuscript_id, change, ids)
    assert result["change"]["comment_ids"] == sorted(ids)
    assert result["change"]["initial_comment_ids"] == []
    assert result["change"]["before_json"] == change["before_json"]
    assert result["change"]["after_json"] == change["after_json"]
    assert result["event"]["before_comment_ids"] == []
    assert result["event"]["after_comment_ids"] == sorted(ids)
    assert service.get_workspace(manuscript_id)["document"] == document
    assert service.get_workspace(manuscript_id)["document_revision"] == 1
    assert all(row["changes"][0]["change_id"] == change["change_id"] for row in service.list_comments(manuscript_id))
    with TestClient(create_app(tmp_path)) as client:
        response = client.get(f"/api/manuscripts/{manuscript_id}/changes")
        assert response.status_code == 200 and response.json() == [result["change"]]


def test_unlink_and_undo_append_history_keep_original_edit_context_and_idempotent_save(tmp_path: Path):
    service, _, manuscript_id, comments, document, change = fixture(tmp_path, linked=True)
    ids = [item["comment_id"] for item in comments]
    unlinked = assign(service, manuscript_id, change, [])
    assert all(not row["changes"] for row in service.list_comments(manuscript_id))
    restored = assign(service, manuscript_id, unlinked["change"], ids, request_id="undo-association-1", reverse=unlinked["event"]["event_id"])
    assert restored["change"]["comment_ids"] == sorted(ids)
    assert len(restored["change"]["association_events"]) == 2
    assert restored["event"]["reverses_event_id"] == unlinked["event"]["event_id"]
    assert restored["change"]["initial_comment_ids"] == sorted(ids)
    # Replaying an original author's save uses original request context, not current links.
    assign(service, manuscript_id, restored["change"], [], request_id="unlink-association-2")
    replay = service.save_document(manuscript_id, base_revision=0, operation_id="original-author-save", document=document, comment_ids=ids)
    assert replay["idempotent_replay"] and replay["document_revision"] == 1
    assert service.list_changes(manuscript_id)[0]["comment_ids"] == []
    with pytest.raises(RevisionConflictError, match="different review links"):
        service.save_document(manuscript_id, base_revision=0, operation_id="original-author-save", document=document, comment_ids=[])


def test_retry_does_not_repeat_events_and_does_not_roll_back_later_associations(tmp_path: Path):
    service, _, manuscript_id, comments, _, change = fixture(tmp_path)
    first = assign(service, manuscript_id, change, [comments[0]["comment_id"]])
    later = assign(service, manuscript_id, first["change"], [comments[1]["comment_id"]], request_id="late-association-2")
    replay = assign(service, manuscript_id, change, [comments[0]["comment_id"]])
    assert replay["idempotent_replay"] and replay["event"] == first["event"]
    assert replay["change"] == later["change"]
    assert len(replay["change"]["association_events"]) == 2
    with pytest.raises(RevisionConflictError, match="different decision"):
        assign(service, manuscript_id, change, [comments[1]["comment_id"]])


@pytest.mark.parametrize("defect", ["foreign_change", "foreign_comment", "archived_comment", "stale_revision", "invalid_reversal"])
def test_invalid_assignment_is_atomic_and_preserves_prior_history(tmp_path: Path, defect: str):
    service, track_id, manuscript_id, comments, _, change = fixture(tmp_path)
    other = service.create_manuscript(track_id, "Other fixture")["manuscript"]["manuscript_id"]
    selected, revision, reverse, owner = [comments[0]["comment_id"]], 0, None, manuscript_id
    expected = RevisionConflictError
    if defect == "foreign_change":
        owner = other
        expected = NotFoundError
    elif defect == "foreign_comment":
        round_row = service.create_review_round(other, round_number=1, venue=None)
        selected = [service.import_comments(round_row["review_round_id"], [{"text": "Other opinion", "include": True}], source="FIXTURE")[0]["comment_id"]]
        expected = NotFoundError
    elif defect == "archived_comment":
        service.archive_comment(selected[0])
        expected = ValueError
    elif defect == "stale_revision":
        revision = 1
    else:
        reverse = "unknown-event"
    before = service.list_changes(manuscript_id)
    with pytest.raises(expected):
        assign(service, owner, change, selected, revision=revision, reverse=reverse)
    assert service.list_changes(manuscript_id) == before


def test_archived_original_links_can_be_retained_or_removed_without_loss_and_same_id_restore(tmp_path: Path):
    service, _, manuscript_id, comments, _, change = fixture(tmp_path, linked=True)
    ids = [item["comment_id"] for item in comments]
    service.archive_comment(ids[0])
    retained = assign(service, manuscript_id, change, ids)
    removed = assign(service, manuscript_id, retained["change"], [ids[1]], request_id="remove-archived-link")
    assert removed["change"]["initial_comment_ids"] == sorted(ids)
    with pytest.raises(ValueError, match="archived"):
        assign(service, manuscript_id, removed["change"], ids, request_id="forbidden-archived-link")
    service.archive_comment(ids[0], restore=True)
    restored = assign(service, manuscript_id, removed["change"], ids, request_id="restored-original-id")
    assert restored["change"]["comment_ids"] == sorted(ids)
    assert len(restored["change"]["association_events"]) == 3


def test_competing_assignments_conflict_instead_of_overwriting(tmp_path: Path):
    service, _, manuscript_id, comments, _, change = fixture(tmp_path)
    barrier = Barrier(2)

    def create(index):
        barrier.wait(timeout=5)
        try:
            return assign(service, manuscript_id, change, [comments[index]["comment_id"]], request_id=f"concurrent-association-{index}")
        except RevisionConflictError:
            return "CONFLICT"

    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(create, [0, 1]))
    assert results.count("CONFLICT") == 1
    assert len(service.list_changes(manuscript_id)[0]["association_events"]) == 1


def test_legacy_context_capture_is_explicit_and_never_invents_older_history(tmp_path: Path):
    service, _, manuscript_id, comments, document, change = fixture(tmp_path, linked=True)
    import json
    with transaction(service.db_path) as conn:
        row = conn.execute("SELECT payload_json FROM studio_operations WHERE operation_id=?", ("original-author-save",)).fetchone()
        payload = json.loads(row[0])
        payload.pop("comment_ids")
        conn.execute("UPDATE studio_operations SET payload_json=? WHERE operation_id=?", (json.dumps(payload), "original-author-save"))
        conn.execute("DELETE FROM studio_change_link_state WHERE change_id=?", (change["change_id"],))
    assert service.list_changes(manuscript_id)[0]["association_origin"] == "legacy_current_links_unverified"
    updated = assign(service, manuscript_id, change, [])
    assert updated["change"]["association_origin"] == "legacy_capture_before_late_link"
    assert len(updated["change"]["association_events"]) == 1
    replay = service.save_document(manuscript_id, base_revision=0, operation_id="original-author-save", document=document,
                                  comment_ids=[item["comment_id"] for item in comments])
    assert replay["idempotent_replay"]


def test_saved_document_undo_is_a_separate_compensating_change_and_links_are_not_erased(tmp_path: Path):
    service, _, manuscript_id, comments, document, change = fixture(tmp_path, linked=True)
    original = service.get_document_revision(manuscript_id, 0)["document"]
    service.save_document(manuscript_id, base_revision=1, operation_id="undo-original-document", document=original,
                          operation_kind="UNDO", comment_ids=[item["comment_id"] for item in comments])
    history = service.list_changes(manuscript_id)
    assert history[0] == change and history[1]["is_compensating"] == 1
    assert history[0]["after_json"] != history[1]["after_json"]
    assert service.get_workspace(manuscript_id)["document"] == original
    assert document != original


def test_http_rejects_boolean_revision_without_writing_history(tmp_path: Path):
    service, _, manuscript_id, comments, _, change = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(f"/api/manuscripts/{manuscript_id}/changes/{change['change_id']}/associations",
            json={"request_id": "invalid-revision-http", "expected_link_revision": True, "comment_ids": [comments[0]["comment_id"]]})
        assert response.status_code == 422
    assert service.list_changes(manuscript_id)[0] == change
