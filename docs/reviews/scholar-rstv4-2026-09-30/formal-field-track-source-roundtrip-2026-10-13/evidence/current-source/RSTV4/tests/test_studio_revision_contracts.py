from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_writing_studio import complete_document, create_studio

from rstv4.studio_api import _split_review_comments, create_app


@pytest.mark.parametrize("changed_field", ["document", "base_revision", "operation_kind", "comment_ids"])
def test_save_id_reuse_cannot_acknowledge_a_different_edit(tmp_path: Path, changed_field: str) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    round_row = service.create_review_round(manuscript_id, round_number=1, venue=None)
    opinion = service.import_comments(round_row["review_round_id"], [{"text": "Original opinion"}], source="FIXTURE")[0]
    document = complete_document(service.get_workspace(manuscript_id))
    request = {"base_revision": 0, "operation_id": "immutable-save-operation", "document": document,
               "operation_kind": "EDIT", "comment_ids": [opinion["comment_id"]]}
    with TestClient(create_app(tmp_path)) as client:
        endpoint = f"/api/manuscripts/{manuscript_id}/document"
        first = client.put(endpoint, json=request)
        assert first.status_code == 200
        changed = deepcopy(request)
        if changed_field == "document":
            changed["document"]["title"] = "New author content must not be silently acknowledged"
        elif changed_field == "base_revision":
            changed["base_revision"] = 1
        elif changed_field == "operation_kind":
            changed["operation_kind"] = "UNDO"
        else:
            changed["comment_ids"] = []
        rejected = client.put(endpoint, json=changed)
        assert rejected.status_code == 409
        current = client.get(f"/api/manuscripts/{manuscript_id}/workspace").json()
        assert current["document_revision"] == 1
        assert current["document"] == document
        assert len(service.list_comments(manuscript_id)[0]["changes"]) == 1
        # An exact retry still succeeds even after its opinion is archived.
        service.archive_comment(opinion["comment_id"])
        replay = client.put(endpoint, json=request)
        assert replay.status_code == 200
        assert replay.json()["idempotent_replay"] is True


def test_comment_labels_survive_archive_restore_import_and_new_round(
    tmp_path: Path,
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    first_round = service.create_review_round(manuscript_id, round_number=1, venue=None)
    comments = service.import_comments(
        first_round["review_round_id"],
        [
            {"text": "First opinion"},
            {"text": "Second opinion"},
        ],
        source="PASTED",
    )
    assert [row["display_label"] for row in comments] == ["A01", "A02"]
    service.archive_comment(comments[0]["comment_id"])
    assert service.list_comments(manuscript_id)[0]["display_label"] == "A02"
    later = service.import_comments(
        first_round["review_round_id"], [{"text": "Third opinion"}], source="PASTED"
    )[0]
    assert later["display_label"] == "A03"
    restored = service.archive_comment(comments[0]["comment_id"], restore=True)
    assert restored["comment_id"] == comments[0]["comment_id"]
    assert restored["display_label"] == "A01"
    second_round = service.create_review_round(
        manuscript_id, round_number=2, venue=None
    )
    other = service.import_comments(
        second_round["review_round_id"], [{"text": "Next round"}], source="PASTED"
    )[0]
    assert other["display_label"] == "A04"


def test_legacy_labels_are_assigned_with_archived_rows_and_preserved_metadata(
    tmp_path: Path,
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    round_row = service.create_review_round(manuscript_id, round_number=1, venue=None)
    comments = service.import_comments(
        round_row["review_round_id"],
        [
            {"text": "First"},
            {"text": "Second"},
        ],
        source="PASTED",
        import_metadata={"original_text": "First\n\nSecond", "filename": "review.txt"},
    )
    with sqlite3.connect(service.db_path) as conn:
        for row in comments:
            metadata = json.loads(
                conn.execute(
                    "SELECT import_metadata_json FROM review_comments WHERE comment_id=?",
                    (row["comment_id"],),
                ).fetchone()[0]
            )
            metadata.pop("comment_number", None)
            conn.execute(
                "UPDATE review_comments SET import_metadata_json=? WHERE comment_id=?",
                (json.dumps(metadata), row["comment_id"]),
            )
    service.archive_comment(comments[0]["comment_id"])
    current = service.list_comments(manuscript_id)
    assert current[0]["display_label"] == "A02"
    assert current[0]["import_metadata"]["filename"] == "review.txt"
    assert current[0]["original_text"] == "Second"
    service.import_comments(
        round_row["review_round_id"], [{"text": "Third"}], source="PASTED"
    )
    assert [
        row["display_label"]
        for row in service.list_comments(manuscript_id, include_archived=True)
    ] == ["A01", "A02", "A03"]


def test_import_101_selected_comments_is_explicit_and_atomic(tmp_path: Path) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    round_row = service.create_review_round(manuscript_id, round_number=1, venue=None)
    with pytest.raises(ValueError, match="100"):
        service.import_comments(
            round_row["review_round_id"],
            [{"text": f"Opinion {i}"} for i in range(101)],
            source="PASTED",
        )
    assert service.list_comments(manuscript_id) == []


def test_file_preview_retains_101_and_selected_import_preserves_raw_source(
    tmp_path: Path,
) -> None:
    raw = "\n\n".join(f"Opinion {i}" for i in range(101))
    preview = _split_review_comments(raw)
    assert len(preview) == 101
    app = create_app(tmp_path)
    service = app.state.studio
    # Existing fixture helper only operates in this test's isolated root.
    _, track_id, _ = create_studio(tmp_path)
    manuscript_id = service.create_manuscript(track_id, "Import fixture")["manuscript"][
        "manuscript_id"
    ]
    round_row = service.create_review_round(manuscript_id, round_number=1, venue=None)
    with TestClient(app) as client:
        result = client.post(
            "/api/review-comments/preview-file",
            files={"file": ("review.txt", raw.encode(), "text/plain")},
        )
        assert result.status_code == 200
        assert len(result.json()["comments"]) == 101
        endpoint = f"/api/review-rounds/{round_row['review_round_id']}/comments"
        rejected = client.post(
            endpoint, json={"source": "FILE_IMPORT", "comments": preview}
        )
        assert rejected.status_code == 422
        assert service.list_comments(manuscript_id) == []
        preview[0]["include"] = False
        preview[-1]["text"] = "Author edited the last opinion"
        response = client.post(
            endpoint,
            json={
                "source": "FILE_IMPORT",
                "comments": preview,
                "import_metadata": {"original_text": raw},
            },
        )
        assert response.status_code == 201, response.text
        imported = response.json()
        assert len(imported) == 100
        assert imported[-1]["original_text"] == "Opinion 100"
        assert imported[-1]["edited_text"] == "Author edited the last opinion"
        assert imported[-1]["import_metadata"]["original_index"] == 100
        assert imported[-1]["import_metadata"]["raw_import_text"] == raw
        assert len({row["import_metadata"]["import_batch_id"] for row in imported}) == 1


@pytest.mark.parametrize("invalid", ["archived", "other_manuscript"])
def test_save_refuses_invalid_comment_association_without_changing_document(
    tmp_path: Path, invalid: str
) -> None:
    service, track_id, manuscript_id = create_studio(tmp_path)
    owner = manuscript_id
    if invalid == "other_manuscript":
        owner = service.create_manuscript(track_id, "Other manuscript")["manuscript"][
            "manuscript_id"
        ]
    round_row = service.create_review_round(owner, round_number=1, venue=None)
    comment = service.import_comments(
        round_row["review_round_id"], [{"text": "Opinion"}], source="PASTED"
    )[0]
    if invalid == "archived":
        service.archive_comment(comment["comment_id"])
    workspace = service.get_workspace(manuscript_id)
    with pytest.raises(ValueError, match="comment"):
        service.save_document(
            manuscript_id,
            base_revision=0,
            operation_id="invalid-comment-link",
            document=complete_document(workspace),
            comment_ids=[comment["comment_id"]],
        )
    assert service.get_workspace(manuscript_id)["document_revision"] == 0
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM studio_operations").fetchone()[0] == 0


def test_single_blank_lines_and_multicomment_change_links_survive_context_end(
    tmp_path: Path,
) -> None:
    service, _, manuscript_id = create_studio(tmp_path)
    round_row = service.create_review_round(manuscript_id, round_number=1, venue=None)
    raw = "One single opinion\n\nwith a second paragraph."
    comments = service.import_comments(
        round_row["review_round_id"],
        [{"text": raw}, {"text": "Related opinion"}],
        source="SINGLE",
    )
    assert comments[0]["original_text"] == raw
    assert comments[0]["edited_text"] == raw
    document = complete_document(service.get_workspace(manuscript_id))
    service.save_document(
        manuscript_id,
        base_revision=0,
        operation_id="linked-edit",
        document=document,
        comment_ids=[row["comment_id"] for row in comments],
    )
    document["abstract"] = "A later ordinary edit"
    service.save_document(
        manuscript_id,
        base_revision=1,
        operation_id="ordinary-edit",
        document=document,
        comment_ids=[],
    )
    service.archive_comment(comments[0]["comment_id"])
    all_comments = service.list_comments(manuscript_id, include_archived=True)
    assert all(len(row["changes"]) == 1 for row in all_comments)
    assert all(
        row["changes"][0]["operation_id"] == "linked-edit" for row in all_comments
    )
