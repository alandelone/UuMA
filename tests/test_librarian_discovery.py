import pytest

from uuma.librarian_discovery import discover, discover_page


def test_retains_cache_and_original_files_but_explicitly_excludes_dependencies(tmp_path):
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "attachment.png").write_bytes(b"fixture")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "dependency").write_bytes(b"fixture")
    (tmp_path / ".env").write_bytes(b"fixture")
    (tmp_path / "source.py").write_bytes(b"fixture")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = discover(tmp_path, verified_exclusions=frozenset({".venv"}))
    items = {item["relative_path"]: item["classification"] for item in result["files"]}
    assert items == {".cache/attachment.png": "UNCLASSIFIED", ".env": "RECOVERY_ONLY",
                     "source.py": "UNCLASSIFIED"}
    assert result["exclusions"] == [".venv"] and result["coverage"] == "DISCOVERED"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_dependencies_are_not_excluded_without_explicit_verification(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "possibly-unique").write_bytes(b"fixture")
    result = discover(tmp_path)
    assert result["exclusions"] == []
    assert result["files"][0]["relative_path"] == "node_modules/possibly-unique"
    with pytest.raises(ValueError):
        discover(tmp_path, verified_exclusions=frozenset({"../outside"}))


def test_inventory_bound_is_visible_in_coverage(tmp_path):
    for index in range(3):
        (tmp_path / str(index)).write_text("fixture")
    result = discover(tmp_path, max_files=1)
    assert len(result["files"]) == 1
    assert result["coverage"] == "PARTIAL"
    assert result["issues"][-1]["error_type"] == "INVENTORY_BOUND_REACHED"


def test_pages_cover_nested_sources_without_duplicates(tmp_path):
    (tmp_path / "nested").mkdir()
    for name in ["a", "z", "nested/1", "nested/2"]:
        (tmp_path / name).write_text("fixture")
    cursor, seen = None, []
    for _ in range(10):
        page = discover_page(tmp_path, cursor=cursor, max_entries=2)
        seen.extend(item["relative_path"] for item in page["files"])
        cursor = page["cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert sorted(seen) == ["a", "nested/1", "nested/2", "z"]


def test_changed_directory_invalidates_cursor_instead_of_skipping_files(tmp_path):
    (tmp_path / "a").write_text("fixture")
    (tmp_path / "b").write_text("fixture")
    cursor = discover_page(tmp_path, max_entries=1)["cursor"]
    assert cursor is not None
    (tmp_path / "new").write_text("fixture")
    # Windows directory timestamp updates can share one filesystem clock tick.
    import os

    stamp = tmp_path.stat()
    os.utime(tmp_path, ns=(stamp.st_atime_ns, cursor[0]["mtime_ns"] + 1_000_000))
    with pytest.raises(ValueError, match="changed"):
        discover_page(tmp_path, cursor=cursor, max_entries=1)


def test_traversal_cursor_rejected(tmp_path):
    with pytest.raises(ValueError, match="cursor path"):
        discover_page(tmp_path, cursor=[{"directory": "../outside", "after": "", "mtime_ns": 0}])


def test_parent_directory_change_is_detected_before_child_page(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "a").write_text("fixture")
    (nested / "b").write_text("fixture")
    cursor = discover_page(tmp_path, max_entries=1)["cursor"]
    assert cursor is not None
    (tmp_path / "new").write_text("fixture")
    with pytest.raises(ValueError, match="changed"):
        discover_page(tmp_path, cursor=cursor, max_entries=1)


def test_missing_or_wrong_root_does_not_create_directory(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        discover(missing)
    assert not missing.exists()
    source = tmp_path / "file"
    source.write_text("fixture")
    with pytest.raises(ValueError):
        discover(source)


def test_symlinks_are_reported_and_not_followed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "original").write_bytes(b"fixture")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "link").symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Creating a symlink is unavailable: {exc}")
    result = discover(root)
    assert result["files"] == []
    assert result["coverage"] == "PARTIAL"
    assert result["issues"] == [{"path": "link", "error_type": "SYMLINK_NOT_FOLLOWED"}]
