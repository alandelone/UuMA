import json
import sqlite3

import pytest

from uuma import brainstormer_migration
from uuma.brainstormer_migration import create_snapshot, snapshot_file_list


def fixture_roots(tmp_path):
    profile, data = tmp_path / "profile", tmp_path / "data"
    profile.mkdir()
    (data / "brainstormer/projects/project-one").mkdir(parents=True)
    (profile / "SOUL.md").write_text("original role", encoding="utf-8")
    (profile / ".env").write_text("MODEL_KEY=not-for-copy", encoding="utf-8")
    (profile / "auth.json").write_text('{"token":"not-for-copy"}', encoding="utf-8")
    (profile / "config.yaml").write_text("api_key: not-for-copy", encoding="utf-8")
    (data / "brainstormer/projects/project-one/state.json").write_text(
        '{"revision":3}', encoding="utf-8"
    )
    with sqlite3.connect(profile / "state.db") as conn:
        conn.execute("CREATE TABLE sessions (message TEXT)")
        conn.execute("INSERT INTO sessions VALUES ('keep session')")
    return profile, data


def test_candidate_copies_reviewed_domain_and_consistent_sessions_without_credentials(tmp_path):
    profile, data = fixture_roots(tmp_path)
    before = (profile / "state.db").read_bytes()
    files = snapshot_file_list(profile, data)
    result = create_snapshot(profile_root=profile, data_root=data,
                             destination=tmp_path / "snapshot", files=files)
    assert result["snapshot_kind"] == "candidate"
    assert result["production_cutover_ready"] is False
    assert result["config_requires_regeneration"] is True
    assert (profile / "state.db").read_bytes() == before
    records = {r["path"]: r for r in result["files"]}
    assert records["profile/state.db"]["table_rows"]["sessions"] == 1
    assert "profile/SOUL.md" in records
    assert "data/brainstormer/projects/project-one/state.json" in records
    assert not any("not-for-copy" in p.read_text(encoding="utf-8", errors="ignore")
                   for p in (tmp_path / "snapshot").rglob("*") if p.is_file())


@pytest.mark.parametrize("name", [
    ".env", "auth.json", "config.yaml", "../outside.json", "uuma.db",
])
def test_explicit_credentials_escape_or_control_database_cannot_be_copied(tmp_path, name):
    profile, data = fixture_roots(tmp_path)
    files = {"profile": [], "data": []}
    files["data" if name == "uuma.db" else "profile"] = [name]
    with pytest.raises(ValueError):
        create_snapshot(profile_root=profile, data_root=data,
                        destination=tmp_path / "snapshot", files=files)
    assert not (tmp_path / "snapshot").exists()


def test_final_requires_matching_freeze_evidence_and_never_overwrites(tmp_path):
    profile, data = fixture_roots(tmp_path)
    proof = tmp_path / "freeze.json"
    proof.write_text(json.dumps({"all_writers_stopped": True,
                                 "source_receiver_stopped": True,
                                 "profile_root": str(profile), "data_root": str(data),
                                 "verified_at": "2026-10-22T00:00:00Z",
                                 "verification_method": "owned process and gateway inspection"}),
                     encoding="utf-8")
    args = {"profile_root": profile, "data_root": data, "destination": tmp_path / "snapshot",
            "files": snapshot_file_list(profile, data), "freeze_receipt": proof}
    result = create_snapshot(**args)
    assert result["production_cutover_ready"] is True
    assert len(result["freeze_evidence"]["receipt_sha256"]) == 64
    with pytest.raises(FileExistsError):
        create_snapshot(**args)
    proof.write_text('{}', encoding="utf-8")
    args["destination"] = tmp_path / "bad-snapshot"
    with pytest.raises(ValueError, match="freeze evidence"):
        create_snapshot(**args)


def test_snapshot_cannot_be_nested_in_source(tmp_path):
    profile, data = fixture_roots(tmp_path)
    with pytest.raises(ValueError, match="separate"):
        create_snapshot(profile_root=profile, data_root=data, destination=data / "backup",
                        files=snapshot_file_list(profile, data))


def test_source_symlinks_cannot_be_followed(tmp_path):
    profile, data = fixture_roots(tmp_path)
    external = tmp_path / "external.md"
    external.write_text("outside", encoding="utf-8")
    try:
        (profile / "linked.md").symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is not available for this Windows account")
    with pytest.raises(ValueError, match="symbolic links"):
        create_snapshot(profile_root=profile, data_root=data, destination=tmp_path / "snapshot",
                        files={"profile": ["linked.md"], "data": []})


def test_final_detects_live_wal_changes_and_keeps_failed_receipt(tmp_path, monkeypatch):
    profile, data = fixture_roots(tmp_path)
    proof = tmp_path / "freeze.json"
    proof.write_text(json.dumps({"all_writers_stopped": True,
                                 "source_receiver_stopped": True,
                                 "profile_root": str(profile), "data_root": str(data),
                                 "verified_at": "2026-10-22T00:00:00Z",
                                 "verification_method": "test simulated controller"}),
                     encoding="utf-8")
    original = brainstormer_migration._backup_database
    writer = sqlite3.connect(profile / "state.db")
    writer.execute("PRAGMA journal_mode=WAL")

    def concurrent_write(source, destination):
        result = original(source, destination)
        writer.execute("INSERT INTO sessions VALUES ('late write')")
        writer.commit()
        return result

    monkeypatch.setattr(brainstormer_migration, "_backup_database", concurrent_write)
    destination = tmp_path / "snapshot"
    try:
        with pytest.raises(ValueError, match="frozen source changed"):
            create_snapshot(profile_root=profile, data_root=data, destination=destination,
                            files=snapshot_file_list(profile, data), freeze_receipt=proof)
    finally:
        writer.close()
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["production_cutover_ready"] is False
