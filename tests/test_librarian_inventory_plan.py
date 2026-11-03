import pytest

import uuma.librarian_inventory_plan as planner
from uuma.librarian_discovery import discover_page


def test_large_tree_is_partitioned_without_claiming_capture(tmp_path):
    (tmp_path / "nested").mkdir()
    for name in ("a", "b", "c", "nested/d", "nested/e", "nested/f", "nested/g"):
        (tmp_path / name).write_text("fixture")
    result = planner.plan_inventory(tmp_path, "workstation-projects", page_size=2, shard_files=3)
    assert result["inventory_status"] == "DISCOVERED" and result["snapshot_consistency"] == "NON_ATOMIC"
    assert result["capture_status"] == "NOT_CAPTURED" and result["server_grants"] == "NOT_CHECKED"
    assert result["observed_files"] == 7 and [len(s["relative_paths"]) for s in result["shards"]] == [3, 3, 1]
    assert len({p for s in result["shards"] for p in s["relative_paths"]}) == 7
    assert [s["source_id"] for s in result["shards"]] == [
        "workstation-projects-p00001", "workstation-projects-p00002", "workstation-projects-p00003",
    ]


def test_page_and_shard_bounds_report_partial(tmp_path):
    for number in range(7):
        (tmp_path / str(number)).write_text("fixture")
    bounded = planner.plan_inventory(tmp_path, "projects", page_size=2, max_pages=1)
    assert bounded["inventory_status"] == "PARTIAL" and not bounded["finished"]
    assert bounded["issues"][-1]["error_type"] == "PAGE_BOUND_REACHED"
    limited = planner.plan_inventory(tmp_path, "projects", shard_files=2, max_shards=2)
    assert limited["inventory_status"] == "PARTIAL" and limited["observed_files"] == 4
    assert limited["issues"][-1]["error_type"] == "SHARD_BOUND_REACHED"


def test_live_directory_change_keeps_observed_files_but_is_partial(tmp_path, monkeypatch):
    for number in range(3):
        (tmp_path / str(number)).write_text("fixture")
    calls = []

    def changing(*args, **kwargs):
        calls.append(1)
        result = discover_page(*args, **kwargs)
        if len(calls) == 1:
            (tmp_path / "new").write_text("later")
        return result

    monkeypatch.setattr(planner, "discover_page", changing)
    result = planner.plan_inventory(tmp_path, "projects", page_size=1)
    assert result["inventory_status"] == "PARTIAL" and result["observed_files"] == 1
    assert result["issues"][-1]["error_type"] == "ValueError"
    assert result["capture_status"] == "NOT_CAPTURED"


def test_invalid_identity_and_duplicate_discovery_fail_closed(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        planner.plan_inventory(tmp_path, "../bad")
    record = {"relative_path": "same"}
    monkeypatch.setattr(planner, "discover_page", lambda *a, **kw: {
        "files": [record, record], "issues": [], "cursor": None,
    })
    with pytest.raises(ValueError, match="duplicate"):
        planner.plan_inventory(tmp_path, "projects")


def test_verified_exclusions_are_respected(tmp_path):
    (tmp_path / "included").mkdir()
    (tmp_path / "excluded").mkdir()
    (tmp_path / "included" / "code.py").write_text("code")
    (tmp_path / "excluded" / "junk.py").write_text("junk")
    result = planner.plan_inventory(
        tmp_path, "projects", verified_exclusions=frozenset({"excluded"})
    )
    assert result["inventory_status"] == "DISCOVERED"
    assert result["observed_files"] == 1
    assert result["shards"][0]["relative_paths"] == ["included/code.py"]
