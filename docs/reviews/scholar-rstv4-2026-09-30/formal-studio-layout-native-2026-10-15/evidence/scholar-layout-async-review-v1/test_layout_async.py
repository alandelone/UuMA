"""Isolated service-level contracts: real compiler, local fixture realization only."""
from copy import deepcopy
import hashlib
import json
import shutil
import threading
from pathlib import Path

import pytest

from rstv4.database import transaction
from rstv4.service import RSTV4Error
from rstv4.studio import StudioService
from test_writing_studio import create_studio, complete_document, wait_for_job


def rows(service, table):
    with transaction(service.db_path) as conn:
        return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]


@pytest.fixture(scope="module")
def compiled_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("layout-source")
    service, _, ms = create_studio(root)
    doc = complete_document(service.get_workspace(ms))
    asset = service.store_asset(ms, "layout-fixture.csv", "text/csv", b"scope,qualification\nsoftware,fictional only\n")
    doc["sections"][0]["paragraphs"][0]["asset_ids"] = [asset["asset_id"]]
    service.save_document(ms, base_revision=0, operation_id="layout-source-save", document=doc)
    calls = []
    def local_realization(task, payload):
        assert task == "paragraph_realization"
        calls.append(payload)
        return {"paragraph": "The author decides the central scientific claim.",
                "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_author_1"]}]}
    service.gateway.analyze = local_realization
    job = wait_for_job(service, service.create_job(ms, "GENERATE", input_revision=1))
    assert job["status"] == "SUCCEEDED", job
    assert len(calls) == 1
    version = service.get_workspace(ms)["active_generated_version_id"]
    assert service.get_generated_version(ms, version)["input_revision"] == 1
    service._executor.shutdown(wait=True)
    return root, ms, version


@pytest.fixture
def branch(compiled_source, tmp_path):
    root, ms, version = compiled_source
    target = tmp_path / "branch"
    shutil.copytree(root, target)
    service = StudioService(target)
    with transaction(service.db_path) as conn:
        for row in conn.execute("SELECT artifact_id,storage_path FROM studio_artifacts").fetchall():
            path = target / Path(row["storage_path"]).relative_to(root)
            conn.execute("UPDATE studio_artifacts SET storage_path=? WHERE artifact_id=?", (str(path), row["artifact_id"]))
        for row in conn.execute("SELECT asset_id,storage_path FROM studio_assets").fetchall():
            path = target / Path(row["storage_path"]).relative_to(root)
            conn.execute("UPDATE studio_assets SET storage_path=? WHERE asset_id=?", (str(path), row["asset_id"]))
    def deny_model(*args, **kwargs):
        pytest.fail("Layout replay must not invoke a model")
    service.gateway.analyze = deny_model
    before = rows(service, "studio_model_calls")
    yield service, ms, version, before
    service._executor.shutdown(wait=True)
    assert rows(service, "studio_model_calls") == before


def save_margin(service, ms, value="narrow"):
    ws = service.get_workspace(ms)
    doc = deepcopy(ws["document"])
    doc["layout"] = {"page_margin": value}
    service.save_document(ms, base_revision=ws["document_revision"], operation_id=f"layout-save-{ws['document_revision']}",
                          document=doc, operation_kind="LAYOUT")
    return doc


def replay(service, ms, source):
    return wait_for_job(service, service.create_job(ms, "GENERATE",
        input_revision=service.get_workspace(ms)["document_revision"], request={"layout_replay_version_id": source}))


def version_inputs(service, version):
    with transaction(service.db_path) as conn:
        return json.loads(conn.execute("SELECT inputs_json FROM manuscript_versions WHERE manuscript_version_id=?", (version,)).fetchone()[0])


def test_real_async_replay_compiles_readback_materials_and_context(branch):
    service, ms, source, _ = branch
    original = service.get_generated_version(ms, source)
    old_inputs = version_inputs(service, source)
    review = service.create_review_round(ms, round_number=1, venue="Software fixture", baseline_manuscript_version_id=source,
                                         expected_document_revision=1)
    comment = service.import_comments(review["review_round_id"], [{"text": "Adjust only the page margin.", "include": True}], source="PASTED")[0]
    ws = service.get_workspace(ms)
    doc = deepcopy(ws["document"])
    doc["layout"] = {"page_margin": "narrow"}
    service.save_document(ms, base_revision=1, operation_id="layout-comment-linked", document=doc,
                          operation_kind="LAYOUT", comment_ids=[comment["comment_id"]])
    job = replay(service, ms, source)
    assert job["status"] == "SUCCEEDED", job
    target = service.get_workspace(ms)["active_generated_version_id"]
    current = service.get_generated_version(ms, target)
    inputs = version_inputs(service, target)
    assert current["content"] == original["content"]
    assert inputs["generated"]["sections"] == old_inputs["generated"]["sections"]
    assert inputs["generated"]["references"] == old_inputs["generated"]["references"]
    assert current["layout"] == {"page_margin": "narrow"}
    old_dir = service.storage_root / ms / "generated" / old_inputs["job_id"]
    new_dir = service.storage_root / ms / "generated" / inputs["job_id"]
    assert (new_dir / "manuscript.pdf").is_file()
    assert hashlib.sha256((new_dir / "manuscript.pdf").read_bytes()).hexdigest() != hashlib.sha256((old_dir / "manuscript.pdf").read_bytes()).hexdigest()
    for section in inputs["generated"]["sections"]:
        for paragraph in section["paragraphs"]:
            for asset in paragraph.get("assets", []):
                for key in ("source_file", "render_file"):
                    if key in asset:
                        assert (old_dir / asset[key]).read_bytes() == (new_dir / asset[key]).read_bytes()
    context = service.response_review_context(ms, comment["comment_id"])
    assert len(context["evidence"]) == 1, context
    row = context["evidence"][0]
    assert row["status"] == "LAYOUT_ONLY" and row["changed_text"] == ""
    assert not row["supports_scientific_text_modification"]
    assert row["boxes"] != row["baseline_boxes"]
    # Verify a second replay follows the original validated model lineage recursively.
    save_margin(service, ms, "standard")
    second = replay(service, ms, target)
    assert second["status"] == "SUCCEEDED", second
    last = service.get_workspace(ms)["active_generated_version_id"]
    assert service.get_generated_version(ms, last)["content"] == original["content"]


@pytest.mark.parametrize("action", ["cancel", "author_change"])
def test_during_real_compile_cancel_or_edit_never_promotes(branch, action):
    service, ms, source, _ = branch
    save_margin(service, ms)
    entered, release = threading.Event(), threading.Event()
    real_compile = service._compile_artifacts
    def delayed(job, generated):
        artifacts = real_compile(job, generated)
        entered.set()
        assert release.wait(20), "Test must release the real compile barrier"
        return artifacts
    service._compile_artifacts = delayed
    job = service.create_job(ms, "GENERATE", input_revision=2, request={"layout_replay_version_id": source})
    try:
        assert entered.wait(20), service.get_job(job["job_id"])
        if action == "cancel":
            service.cancel_job(job["job_id"])
        else:
            doc = deepcopy(service.get_workspace(ms)["document"])
            doc["title"] += " Current author change"
            service.save_document(ms, base_revision=2, operation_id="during-layout-compile", document=doc)
    finally:
        release.set()
    terminal = wait_for_job(service, service.get_job(job["job_id"]))
    assert terminal["status"] == ("CANCELLED" if action == "cancel" else "FAILED"), terminal
    assert service.get_workspace(ms)["active_generated_version_id"] == source
    assert len(rows(service, "manuscript_versions")) == 1


@pytest.mark.parametrize("tamper", ["source_hash", "self_parent", "binding", "author_text", "model_call", "material_bytes"])
def test_readback_rejects_tampered_replay_or_original_provenance(branch, tamper):
    service, ms, source, _ = branch
    save_margin(service, ms)
    job = replay(service, ms, source)
    assert job["status"] == "SUCCEEDED", job
    target = service.get_workspace(ms)["active_generated_version_id"]
    assert service.get_generated_version(ms, target)["input_revision"] == 2
    with transaction(service.db_path) as conn:
        inputs = version_inputs(service, target)
        if tamper == "source_hash":
            inputs["generated"]["layout_replay"]["source_generated_sha256"] = "0" * 64
        elif tamper == "self_parent":
            inputs["generated"]["layout_replay"]["source_generated_version_id"] = target
        elif tamper == "binding":
            inputs["scientific_binding"] = {"not": "the original binding"}
        elif tamper == "author_text":
            doc = deepcopy(service.get_workspace(ms)["document"])
            doc["title"] += " Tampered retained revision"
            conn.execute("UPDATE studio_documents SET document_json=? WHERE manuscript_id=?", (json.dumps(doc), ms))
        elif tamper == "model_call":
            # Corrupt the ORIGINAL version's pointer, leaving the validated call ledger untouched.
            parent = version_inputs(service, source)
            parent["generated"]["sections"][0]["paragraphs"][0]["model_call_id"] = "missing-call"
            conn.execute("UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?", (json.dumps(parent), source))
        else:
            asset = inputs["generated"]["sections"][0]["paragraphs"][0]["assets"][0]
            file = service.storage_root / ms / "generated" / inputs["job_id"] / asset["source_file"]
            file.write_bytes(b"corrupted fixture bytes")
        conn.execute("UPDATE manuscript_versions SET inputs_json=? WHERE manuscript_version_id=?", (json.dumps(inputs), target))
    with pytest.raises((RSTV4Error, ValueError)):
        service.get_generated_version(ms, target)


def test_semantic_change_is_rejected_before_compile_and_model(branch):
    service, ms, source, _ = branch
    save_margin(service, ms)
    doc = deepcopy(service.get_workspace(ms)["document"])
    doc["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] += " Different claim."
    service.save_document(ms, base_revision=2, operation_id="layout-semantic-change", document=doc)
    def deny_compile(*args):
        pytest.fail("Semantic differences must fail before compilation")
    service._compile_artifacts = deny_compile
    terminal = replay(service, ms, source)
    assert terminal["status"] == "FAILED", terminal
    assert service.get_workspace(ms)["active_generated_version_id"] == source
    assert len(rows(service, "manuscript_versions")) == 1


@pytest.mark.parametrize("phase", ["queued", "compiled"])
def test_scientific_withdrawal_blocks_layout_promotion(branch, phase):
    service, ms, source, _ = branch
    save_margin(service, ms)
    def withdrawal():
        with transaction(service.db_path) as conn:
            conn.execute("UPDATE manuscripts SET needs_scientific_review=1 WHERE manuscript_id=?", (ms,))
    service.run_job = lambda job_id: None
    job = service.create_job(ms, "GENERATE", input_revision=2, request={"layout_replay_version_id": source})
    if phase == "queued":
        withdrawal()
        def deny_compile(*args):
            pytest.fail("A withdrawn scientific basis must stop before compilation")
        service._compile_artifacts = deny_compile
    else:
        real_compile = service._compile_artifacts
        def compile_then_withdraw(job, generated):
            result = real_compile(job, generated)
            withdrawal()
            return result
        service._compile_artifacts = compile_then_withdraw
    service._execute_job(job["job_id"])
    terminal = service.get_job(job["job_id"])
    assert terminal["status"] == "FAILED", terminal
    assert "cientific" in str(terminal)
    assert service.get_workspace(ms)["active_generated_version_id"] == source
    assert len(rows(service, "manuscript_versions")) == 1
