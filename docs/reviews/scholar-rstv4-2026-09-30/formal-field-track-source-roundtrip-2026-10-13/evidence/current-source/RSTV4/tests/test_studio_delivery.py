from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient
from rstv4.database import transaction
from rstv4.service import NotFoundError
from rstv4.studio import StudioService
from rstv4.studio_api import create_app
from rstv4.studio_delivery import PackageUnavailableError
from test_studio_revision_mapping import package_fixture


@pytest.fixture(scope="module")
def compiled_package(tmp_path_factory):
    root = tmp_path_factory.mktemp("compiled-delivery-fixture")
    service, manuscript_id, _, _, document, _, version, directory, _ = package_fixture(root)
    package = service.list_submission_packages(manuscript_id)[0]
    service._executor.shutdown(wait=True)
    return root, manuscript_id, document, version, directory, package


@pytest.fixture
def delivery(tmp_path, compiled_package):
    root, manuscript_id, document, version, _directory, package = compiled_package
    shutil.copytree(root, tmp_path, dirs_exist_ok=True)
    service = StudioService(tmp_path)
    new_directory = service.storage_root / manuscript_id / "packages" / package["job_id"]
    yield service, manuscript_id, document, version, new_directory, package
    service._executor.shutdown(wait=True)


def store_test_manifest(service, package, directory, manifest):
    # Deliberate corruption/legacy simulations live only in the copied test database.
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE studio_submission_packages SET manifest_json=? WHERE package_id=?",
                     (raw, package["package_id"]))
    (directory / "manifest.json").write_text(raw, encoding="utf-8")


def test_zip_and_individual_files_deliver_exact_fixed_compiler_bytes(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    rows = service.list_submission_packages(manuscript_id)
    assert rows[0]["integrity_status"] == "RECORDED_AT_PACKAGING"
    assert rows[0]["generated_version_number"] == 2 and rows[0]["round_number"] == 1
    assert "directory" not in rows[0] and "storage_path" not in json.dumps(rows)
    raw, name, kind = service.submission_package_content(manuscript_id, package["package_id"])
    assert kind == "application/zip" and name.endswith(".zip")
    assert service.submission_package_content(manuscript_id, package["package_id"])[0] == raw
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert set(archive.namelist()) == {file["name"] for file in rows[0]["files"]}
        for file in rows[0]["files"]:
            content = archive.read(file["name"])
            assert content == (directory / file["name"]).read_bytes()
            assert service.submission_package_content(manuscript_id, package["package_id"], file["name"])[0] == content
            if file["name"] != "manifest.json":
                assert hashlib.sha256(content).hexdigest() == file["sha256"]
                assert len(content) == file["size_bytes"]


def test_actual_api_delivers_attachment_headers_and_owned_file_routes(delivery):
    service, manuscript_id, _, _, _, package = delivery
    app = create_app(service.root)
    with TestClient(app) as client:
        path = f"/api/manuscripts/{manuscript_id}/packages"
        assert client.get(path).json()[0]["package_id"] == package["package_id"]
        response = client.get(f"{path}/{package['package_id']}/download")
        assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert client.get(f"{path}/{package['package_id']}/files/clean-manuscript.pdf").headers["content-type"] == "application/pdf"
        assert client.get(f"{path}/{package['package_id']}/files/not-in-manifest.txt").status_code == 404
        assert client.get(f"/api/manuscripts/unknown/packages/{package['package_id']}/download").status_code == 404


def test_same_size_tampering_refuses_whole_package_and_unmodified_individual_file(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    target = directory / "clean-manuscript.md"
    raw = target.read_bytes()
    target.write_bytes(b"!" + raw[1:])
    for filename in [None, "clean-manuscript.pdf"]:
        with pytest.raises(PackageUnavailableError, match="integrity"):
            service.submission_package_content(manuscript_id, package["package_id"], filename)
    app = create_app(service.root)
    with TestClient(app) as client:
        response = client.get(f"/api/manuscripts/{manuscript_id}/packages/{package['package_id']}/download")
        assert response.status_code == 410 and "integrity" in response.json()["detail"]


def test_missing_fixed_file_is_not_recreated_or_omitted(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    target = directory / "references.bib"
    target.unlink()  # Copied declared test fixture only.
    assert not next(f for f in service.list_submission_packages(manuscript_id)[0]["files"] if f["name"] == "references.bib")["available"]
    with pytest.raises(PackageUnavailableError, match="missing"):
        service.submission_package_content(manuscript_id, package["package_id"])
    assert not target.exists()


def test_manifest_file_must_match_original_record_exactly(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    with (directory / "manifest.json").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(PackageUnavailableError, match="manifest"):
        service.submission_package_content(manuscript_id, package["package_id"])


def test_unsafe_manifest_names_cannot_read_or_zip_outside_package(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"].append("../outside.txt")
    store_test_manifest(service, package, directory, manifest)
    with pytest.raises(PackageUnavailableError, match="file list"):
        service.submission_package_content(manuscript_id, package["package_id"])


def test_legacy_package_delivery_preserves_unknown_digest_status_without_backfill(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    del manifest["file_integrity"]
    manifest["files"].remove("manifest.json")  # Actual earlier manifest convention.
    store_test_manifest(service, package, directory, manifest)
    before = (directory / "manifest.json").read_bytes()
    row = service.list_submission_packages(manuscript_id)[0]
    assert row["integrity_status"] == "LEGACY_ORIGINAL_DIGEST_UNAVAILABLE"
    assert all(file["sha256"] is None for file in row["files"])
    raw, _, _ = service.submission_package_content(manuscript_id, package["package_id"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.read("manifest.json") == before
    assert (directory / "manifest.json").read_bytes() == before


def test_failed_package_job_cannot_be_delivered_as_complete(delivery):
    service, manuscript_id, _, _, _, package = delivery
    with transaction(service.db_path) as conn:
        conn.execute("UPDATE studio_jobs SET status='FAILED' WHERE job_id=?", (package["job_id"],))
    assert not service.list_submission_packages(manuscript_id)
    with pytest.raises(PackageUnavailableError, match="not complete"):
        service.submission_package_content(manuscript_id, package["package_id"])


def test_fixed_author_structure_and_actual_call_records_survive_later_author_edit(delivery):
    service, manuscript_id, document, version, _, package = delivery
    before = service.submission_package_content(manuscript_id, package["package_id"])[0]
    author = json.loads(service.submission_package_content(manuscript_id, package["package_id"], "author-structure.json")[0])
    assert author["input_revision"] == 2 and author["document"] == document
    calls = json.loads(service.submission_package_content(manuscript_id, package["package_id"], "generation-model-calls.json")[0])
    assert calls["generated_version_id"] == version["generated_version_id"]
    assert calls["provenance_status"] == "RECORDED_ACTUAL_CALLS" and len(calls["calls"]) == 1
    assert calls["calls"][0]["status"] == "VALIDATED"
    document["title"] = "Later unrelated fixture edit"
    service.save_document(manuscript_id, base_revision=2, operation_id="delivery-later-edit", document=document)
    assert service.get_workspace(manuscript_id)["generated_is_stale"]
    assert service.submission_package_content(manuscript_id, package["package_id"])[0] == before


def test_existing_other_manuscript_cannot_read_package_or_manifest(delivery):
    service, manuscript_id, _, _, _, package = delivery
    track_id = service.get_workspace(manuscript_id)["manuscript"]["track_id"]
    other_id = service.create_manuscript(track_id, "Other isolated owner")["manuscript"]["manuscript_id"]
    assert service.list_submission_packages(other_id) == []
    with pytest.raises(NotFoundError, match="belong"):
        service.submission_package_content(other_id, package["package_id"])


def test_invalid_recorded_digest_inventory_is_rejected(delivery):
    service, manuscript_id, _, _, directory, package = delivery
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["file_integrity"]["clean-manuscript.pdf"] = {"sha256": "not-a-digest", "size_bytes": True}
    store_test_manifest(service, package, directory, manifest)
    with pytest.raises(PackageUnavailableError, match="inventory"):
        service.submission_package_content(manuscript_id, package["package_id"])
