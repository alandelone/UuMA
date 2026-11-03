import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from uuma.librarian_catalog_publish import publish_catalog
from uuma.librarian_read import LibrarianReader

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Catalog publication requires POSIX")


@pytest.fixture
def example(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / "test-fixtures/librarian/archive"
    catalog = json.loads((fixture / "catalog.json").read_text(encoding="utf-8"))
    versions = frozenset((r["record_id"], r["version_id"]) for r in catalog["records"])
    sources = {r["content_sha256"]: fixture / "objects" / r["content_sha256"][:2] / r["content_sha256"]
               for r in catalog["records"]}
    root = tmp_path / "archive"
    root.mkdir(mode=0o700)
    return root, catalog, versions, sources


def test_publication_preserves_versions_and_enforces_readers(example):
    root, catalog, versions, sources = example
    copied_sources = {}
    for digest, source in sources.items():
        copy_path = root.parent / digest
        copy_path.write_bytes(source.read_bytes())
        copied_sources[digest] = copy_path
    first = publish_catalog(root, catalog, approved_versions=versions, object_sources=copied_sources,
                            expected_current_sha256=None)
    assert first["record_versions"] == 3
    assert LibrarianReader(root, "yonc").search_records()["total"] == 3
    assert LibrarianReader(root, "honc").search_records()["total"] == 0
    for source in copied_sources.values():
        source.unlink()
    old_catalog = (root / "catalog.json").read_bytes()
    updated = copy.deepcopy(catalog)
    updated["snapshot_id"] = "fixture-next"
    additional = copy.deepcopy(updated["records"][0])
    additional["version_id"] = "v3"
    additional["title"] = "New fixture version"
    updated["records"].append(additional)
    second = publish_catalog(root, updated, approved_versions=versions | {("example-question", "v3")},
                             object_sources={}, expected_current_sha256=hashlib.sha256(old_catalog).hexdigest())
    assert second["record_versions"] == 4
    assert (root / "catalogs" / (catalog["snapshot_id"] + ".json")).read_bytes() == old_catalog
    assert LibrarianReader(root, "yonc").read_record("example-question", "v1")["content_verified"]
    assert len(list((root / "objects").glob("*/*"))) == len(sources)


def test_unclassified_or_changed_history_cannot_publish(example):
    root, catalog, versions, sources = example
    with pytest.raises(PermissionError, match="explicit retrieval"):
        publish_catalog(root, catalog, approved_versions=frozenset(), object_sources=sources,
                        expected_current_sha256=None)
    assert not (root / "catalog.json").exists()
    first = publish_catalog(root, catalog, approved_versions=versions, object_sources=sources,
                            expected_current_sha256=None)
    altered = copy.deepcopy(catalog)
    altered["snapshot_id"] = "rewritten"
    altered["records"][0]["original_status"] = "ACCEPTED"
    with pytest.raises(ValueError, match="cannot be removed or rewritten"):
        publish_catalog(root, altered, approved_versions=versions, object_sources={},
                        expected_current_sha256=first["catalog_sha256"])
    assert hashlib.sha256((root / "catalog.json").read_bytes()).hexdigest() == first["catalog_sha256"]


def test_invalid_object_or_stale_publication_never_becomes_current(example, tmp_path):
    root, catalog, versions, sources = example
    bad_sources = dict(sources)
    key = next(iter(bad_sources))
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("incorrect fixture data", encoding="utf-8")
    bad_sources[key] = wrong
    with pytest.raises(ValueError, match="failed its declared digest"):
        publish_catalog(root, catalog, approved_versions=versions, object_sources=bad_sources,
                        expected_current_sha256=None)
    assert not (root / "catalog.json").exists()
    first = publish_catalog(root, catalog, approved_versions=versions, object_sources=sources,
                            expected_current_sha256=None)
    with pytest.raises(ValueError, match="changed since"):
        publish_catalog(root, catalog, approved_versions=versions, object_sources=sources,
                        expected_current_sha256="0" * 64)
    assert hashlib.sha256((root / "catalog.json").read_bytes()).hexdigest() == first["catalog_sha256"]


def test_existing_record_access_can_be_revoked_but_not_widened(example):
    root, catalog, versions, sources = example
    first = publish_catalog(root, catalog, approved_versions=versions, object_sources=sources,
                            expected_current_sha256=None)
    changed = copy.deepcopy(catalog)
    changed["snapshot_id"] = "narrowed"
    for record in changed["records"]:
        record["readers"].remove("yonc")
    second = publish_catalog(root, changed, approved_versions=versions, object_sources={},
                             expected_current_sha256=first["catalog_sha256"])
    assert LibrarianReader(root, "yonc").search_records()["total"] == 0
    widened = copy.deepcopy(changed)
    widened["snapshot_id"] = "widened"
    widened["records"][0]["readers"].append("yonc")
    with pytest.raises(ValueError, match="cannot be removed or rewritten"):
        publish_catalog(root, widened, approved_versions=versions, object_sources={},
                        expected_current_sha256=second["catalog_sha256"])
    assert LibrarianReader(root, "yonc").search_records()["total"] == 0
