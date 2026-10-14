from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from rstv4.database import transaction
from rstv4.service import NotFoundError, RevisionConflictError, RSTV4Error
from rstv4.studio_api import create_app
from test_writing_studio import complete_document, create_studio, wait_for_job


def generate(service, manuscript_id, revision, text, *, real_compiler=False):
    document = complete_document(service.get_workspace(manuscript_id))
    document["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = text
    service.save_document(
        manuscript_id,
        base_revision=revision - 1,
        operation_id=f"round-generate-{manuscript_id}-{revision}",
        document=document,
    )
    service.gateway.analyze = lambda task, payload: {
        "paragraph": payload["intents"][0]["thoughts"][0]["text"],
        "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_author_1"]}],
    }
    compiler = service._compile_artifacts
    if not real_compiler:
        service._compile_artifacts = lambda job, generated: []
    try:
        job = wait_for_job(
            service, service.create_job(manuscript_id, "GENERATE", input_revision=revision)
        )
        assert job["status"] == "SUCCEEDED", job
        return service.get_generated_version(manuscript_id, job["result"]["generated_version_id"])
    finally:
        service._compile_artifacts = compiler


def test_rounds_fix_original_version_and_explicit_selection_survives_new_generation(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    first = generate(service, manuscript_id, 1, "First reviewed fixture.")
    round1 = service.create_review_round(
        manuscript_id,
        round_number=1,
        venue="Fixture",
        baseline_manuscript_version_id=first["generated_version_id"],
        expected_document_revision=1,
    )
    second = generate(service, manuscript_id, 2, "Second reviewed fixture.")
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            f"/api/manuscripts/{manuscript_id}/review-rounds",
            json={
                "round_number": 2,
                "venue": "Fixture",
                "baseline_manuscript_version_id": second["generated_version_id"],
                "expected_document_revision": 2,
            },
        )
        assert response.status_code == 201, response.text
        round2 = response.json()
        rounds = client.get(f"/api/manuscripts/{manuscript_id}/review-rounds").json()
        assert rounds == [round1, round2]
    assert [item["baseline_manuscript_version_id"] for item in rounds] == [
        first["generated_version_id"],
        second["generated_version_id"],
    ]
    assert [item["baseline_document_revision"] for item in rounds] == [1, 2]
    assert service.create_review_round(manuscript_id, round_number=1, venue="Fixture") == round1
    with pytest.raises(RevisionConflictError, match="different fixed"):
        service.create_review_round(
            manuscript_id,
            round_number=1,
            venue="Fixture",
            baseline_manuscript_version_id=second["generated_version_id"],
        )
    assert service.list_review_rounds(manuscript_id) == rounds


@pytest.mark.parametrize(
    "defect", ["foreign_version", "stale_input", "venue", "zero", "negative", "boolean"]
)
def test_invalid_round_creation_preserves_original_baselines(tmp_path: Path, defect: str):
    service, track_id, manuscript_id = create_studio(tmp_path)
    first = generate(service, manuscript_id, 1, "Original reviewed fixture.")
    service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
    kwargs = {
        "round_number": 2,
        "venue": "Fixture",
        "baseline_manuscript_version_id": first["generated_version_id"],
        "expected_document_revision": 1,
    }
    expected = RevisionConflictError
    if defect == "foreign_version":
        other = service.create_manuscript(track_id, "Other fixture")["manuscript"]["manuscript_id"]
        foreign = generate(service, other, 1, "Foreign reviewed fixture.")
        kwargs["baseline_manuscript_version_id"] = foreign["generated_version_id"]
        expected = NotFoundError
    elif defect == "stale_input":
        kwargs["expected_document_revision"] = 0
    elif defect == "venue":
        kwargs.update(round_number=1, venue="Different")
    else:
        kwargs["round_number"] = {"zero": 0, "negative": -1, "boolean": True}[defect]
        expected = ValueError
    before = service.list_review_rounds(manuscript_id)
    with pytest.raises(expected):
        service.create_review_round(manuscript_id, **kwargs)
    assert service.list_review_rounds(manuscript_id) == before
    with transaction(service.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM studio_review_round_baselines").fetchone()[0] == 1


def test_concurrent_same_round_has_one_fixed_version_and_no_silent_overwrite(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    first = generate(service, manuscript_id, 1, "Original fixture.")
    second = generate(service, manuscript_id, 2, "New fixture.")
    barrier = Barrier(2)

    def create(version_id):
        barrier.wait(timeout=5)
        try:
            return service.create_review_round(
                manuscript_id,
                round_number=1,
                venue="Fixture",
                baseline_manuscript_version_id=version_id,
            )
        except RevisionConflictError:
            return "CONFLICT"

    with ThreadPoolExecutor(2) as workers:
        results = list(
            workers.map(create, [first["generated_version_id"], second["generated_version_id"]])
        )
    assert results.count("CONFLICT") == 1
    rounds = service.list_review_rounds(manuscript_id)
    assert len(rounds) == 1 and rounds[0] in results


def test_unresolved_round_never_uses_a_later_version_as_its_original_baseline(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    original = service.create_review_round(manuscript_id, round_number=1, venue=None)
    assert not original["baseline_available"]
    generate(service, manuscript_id, 1, "A later generated fixture.", real_compiler=True)
    assert service.list_review_rounds(manuscript_id) == [original]
    job = wait_for_job(
        service, service.create_job(manuscript_id, "SUBMISSION_PACKAGE", input_revision=1)
    )
    assert job["status"] == "FAILED"
    assert "no proven fixed baseline" in job["error"]["message"]
    assert not (service.storage_root / manuscript_id / "packages" / job["job_id"]).exists()


def test_legacy_round_resolves_only_exact_original_job_and_unknown_stays_unknown(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    first = generate(
        service, manuscript_id, 1, "Original legacy reviewed fixture.", real_compiler=True
    )
    round1 = service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
    with transaction(service.db_path) as conn:
        conn.execute(
            "DELETE FROM studio_review_round_baselines WHERE review_round_id=?",
            (round1["review_round_id"],),
        )
    generate(service, manuscript_id, 2, "Later generated fixture.")
    resolved = service.list_review_rounds(manuscript_id)[0]
    assert resolved["baseline_manuscript_version_id"] == first["generated_version_id"]
    assert resolved["baseline_origin"] == "legacy_exact_artifact_job"
    with transaction(service.db_path) as conn:
        conn.execute(
            "UPDATE review_rounds SET baseline_artifact_id=NULL WHERE review_round_id=?",
            (round1["review_round_id"],),
        )
    unresolved = service.list_review_rounds(manuscript_id)[0]
    assert unresolved["baseline_manuscript_version_id"] is None
    assert not unresolved["baseline_available"]


def test_tampered_fixed_baseline_is_rejected_instead_of_reset(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    first = generate(service, manuscript_id, 1, "Immutable reviewed fixture.")
    service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
    with transaction(service.db_path) as conn:
        conn.execute(
            "UPDATE manuscript_versions SET content=? WHERE manuscript_version_id=?",
            ("Tampered fixture", first["generated_version_id"]),
        )
    with pytest.raises(RSTV4Error, match="integrity"):
        service.list_review_rounds(manuscript_id)


def test_package_selects_actual_round_and_fixed_active_artifacts_and_diff(tmp_path: Path):
    service, _, manuscript_id = create_studio(tmp_path)
    first = generate(service, manuscript_id, 1, "Original reviewed fixture.", real_compiler=True)
    round1 = service.create_review_round(manuscript_id, round_number=1, venue="Fixture")
    opinion1 = service.import_comments(
        round1["review_round_id"], [{"text": "First round only", "include": True}], source="FIXTURE"
    )[0]
    second = generate(service, manuscript_id, 2, "Second reviewed fixture.", real_compiler=True)
    round2 = service.create_review_round(manuscript_id, round_number=2, venue="Fixture")
    opinion2 = service.import_comments(
        round2["review_round_id"],
        [{"text": "Second round only", "include": True}],
        source="FIXTURE",
    )[0]
    current = generate(service, manuscript_id, 3, "Current revised fixture.", real_compiler=True)
    # Mutating the old Markdown file cannot move the fixed database version.
    old_markdown = next(item for item in first["artifacts"] if item["artifact_kind"] == "MARKDOWN")
    Path(old_markdown["storage_path"]).write_text("Incorrect external baseline", encoding="utf-8")
    for round_row, baseline, included, excluded in [
        (round1, first, opinion1, opinion2),
        (round2, second, opinion2, opinion1),
    ]:
        job = wait_for_job(
            service,
            service.create_job(
                manuscript_id,
                "SUBMISSION_PACKAGE",
                input_revision=3,
                request={"review_round_id": round_row["review_round_id"]},
            ),
        )
        assert job["status"] == "SUCCEEDED", job
        directory = Path(job["result"]["directory"])
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["baseline_manuscript_version_id"] == baseline["generated_version_id"]
        assert manifest["generated_version_id"] == current["generated_version_id"]
        assert manifest["unresolved_comment_ids"] == [included["comment_id"]]
        response = (directory / "response-to-reviewers.md").read_text(encoding="utf-8")
        assert included["edited_text"] in response and excluded["edited_text"] not in response
        assert (directory / "clean-manuscript.md").read_text(encoding="utf-8") == current["content"]
        diff = (directory / "marked-comparison.md").read_text(encoding="utf-8")
        assert (
            "-" + ("Original" if round_row == round1 else "Second") + " reviewed fixture." in diff
        )
        assert "+Current revised fixture." in diff
        assert "Incorrect external baseline" not in diff


@pytest.mark.parametrize("invalid", ["foreign_round", "tampered_current"])
def test_package_rejects_wrong_round_or_changed_registered_artifact(tmp_path: Path, invalid: str):
    service, track_id, manuscript_id = create_studio(tmp_path)
    current = generate(service, manuscript_id, 1, "Package fixture.", real_compiler=True)
    round_row = service.create_review_round(manuscript_id, round_number=1, venue=None)
    if invalid == "foreign_round":
        other = service.create_manuscript(track_id, "Other")
        round_row = service.create_review_round(
            other["manuscript"]["manuscript_id"], round_number=1, venue=None
        )
    else:
        artifact = next(item for item in current["artifacts"] if item["artifact_kind"] == "PDF")
        Path(artifact["storage_path"]).write_bytes(b"tampered")
    job = wait_for_job(
        service,
        service.create_job(
            manuscript_id,
            "SUBMISSION_PACKAGE",
            input_revision=1,
            request={"review_round_id": round_row["review_round_id"]},
        ),
    )
    assert job["status"] == "FAILED"
    assert (
        service.list_review_rounds(manuscript_id)[0]["baseline_manuscript_version_id"]
        == current["generated_version_id"]
    )
