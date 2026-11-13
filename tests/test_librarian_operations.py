import importlib.util
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from uuma.librarian_operations import backup_overview, check_source_freshness


def fixture_root(tmp_path):
    intake = tmp_path / "intake"
    intake.mkdir()
    manifest = {"device": "server", "source": "printer", "scheduled_date": "2026-11-05",
                "batch_id": "librarian:server:printer:2026-11-05", "revision": 1,
                "coverage": "PARTIAL", "entries": [{"status": "CAPTURED"},
                                                   {"status": "UNAVAILABLE"}]}
    with sqlite3.connect(intake / "recovery-intake.sqlite") as db:
        db.execute("CREATE TABLE manifest_revisions(batch_id,revision,sha256,raw)")
        db.execute("INSERT INTO manifest_revisions VALUES(?,?,?,?)",
                   (manifest["batch_id"], 1, "abc", json.dumps(manifest)))
    with sqlite3.connect(intake / "recovery-publication.sqlite") as db:
        db.execute("CREATE TABLE publications(batch_id,revision,sha256)")
        db.execute("INSERT INTO publications VALUES(?,?,?)", (manifest["batch_id"], 1, "wrong"))
    (tmp_path / "intake-policy.json").write_text(json.dumps({
        "devices": {"server": ["printer", "missing"]},
    }))
    return tmp_path


def test_receipts_require_digest_match_and_missing_is_explicit(tmp_path):
    root = fixture_root(tmp_path)
    result = backup_overview(root)
    assert result["nas_pending_revisions"] == 1
    rows = {s["source_id"]: s for s in result["sources"]}
    assert rows["printer"]["nas_publication_receipt"] is False
    assert rows["printer"]["unavailable_entries"] == 1
    assert rows["missing"]["coverage"] == "NO_RECEIVED_BACKUP"
    assert result["catalog"]["available"] is False
    with sqlite3.connect(root / "intake/recovery-publication.sqlite") as db:
        db.execute("UPDATE publications SET sha256='abc'")
    assert backup_overview(root)["nas_pending_revisions"] == 0


def test_missing_intake_is_not_created(tmp_path):
    with pytest.raises(ValueError):
        backup_overview(tmp_path)
    assert not list(tmp_path.iterdir())


def load_commands():
    path = Path(__file__).parents[1] / "integrations/hermes/uuma_librarian_commands/__init__.py"
    spec = importlib.util.spec_from_file_location("librarian_commands_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_commands_stable_identity_paging_errors_and_scope(tmp_path):
    mod = load_commands()
    result = backup_overview(fixture_root(tmp_path))
    registered = {}
    ctx = SimpleNamespace(
        profile_name="librarian",
        call_mcp=lambda *a, **k: {"ok": True, "result": json.dumps(result)},
        get_config=lambda key, default: result["sources"],
        register_command=lambda name, handler, **k: registered.update({name: handler}),
    )
    mod.register(ctx)
    # Hermes' Telegram dispatcher normalizes underscores before looking up a plugin command.
    def dispatch(name):
        return registered[name.replace("_", "-")]()

    assert all("_" not in name for name in registered)
    assert "待发布 1" in dispatch("library")
    link = mod.source_command("server", "printer")
    assert len(link) <= 32
    assert link in dispatch("library_sources")
    assert "不可用 1" in dispatch(link)
    assert "没有匹配" in dispatch("library_sources_page_2")
    assert "待检查" in dispatch("library_issues")
    ctx.call_mcp = lambda *a, **k: {"ok": True, "truncated": True, "result": result}
    assert "查询未完成" in registered["library"]()
    ctx.profile_name = "forge-lab-bot"
    assert "仅供" in registered["library"]()


def test_backup_freshness_and_expiration_detection():
    tz = ZoneInfo("Asia/Singapore")
    # Reference: 2026-11-05 10:00:00 (MYT)
    now_morning = datetime(2026, 11, 5, 10, 0, 0, tzinfo=tz)
    # Reference: 2026-11-05 02:00:00 (MYT, early morning before 04:00)
    now_early = datetime(2026, 11, 5, 2, 0, 0, tzinfo=tz)

    # 1. Daily source - same day is FRESH
    res = check_source_freshness("codex-state", "2026-11-05", now_morning)
    assert res["freshness"] == "FRESH" and not res["is_expired"] and res["days_since"] == 0

    # 2. Daily source - yesterday (1 day ago) after 04:00 is OVERDUE (is_expired=True)
    res = check_source_freshness("antigravity-core", "2026-11-04", now_morning)
    assert res["freshness"] == "OVERDUE" and res["is_expired"] and res["days_since"] == 1

    # 3. Daily source - yesterday (1 day ago) before 04:00 is EXPIRING (is_expired=False)
    res = check_source_freshness("antigravity-core", "2026-11-04", now_early)
    assert res["freshness"] == "EXPIRING" and not res["is_expired"] and res["days_since"] == 1

    # 4. Daily source - 2+ days ago is EXPIRED
    res = check_source_freshness("scholar", "2026-11-03", now_morning)
    assert res["freshness"] == "EXPIRED" and res["is_expired"] and res["days_since"] == 2

    # 5. Missing date (never received)
    res = check_source_freshness("codex", None, now_morning)
    assert res["freshness"] == "NO_BACKUP" and res["is_expired"] and res["days_since"] is None

    # 6. Weekly source (printer-*)
    res_week_fresh = check_source_freshness("printer-vcore-config", "2026-10-30", now_morning)  # 6 days ago
    assert res_week_fresh["freshness"] == "FRESH" and not res_week_fresh["is_expired"]

    res_week_expiring = check_source_freshness("printer-vcore-config", "2026-10-28", now_morning)  # 8 days ago
    assert res_week_expiring["freshness"] == "EXPIRING" and not res_week_expiring["is_expired"]

    res_week_expired = check_source_freshness("printer-vcore-config", "2026-10-27", now_morning)  # 9 days ago
    assert res_week_expired["freshness"] == "EXPIRED" and res_week_expired["is_expired"]

    # 7. Snapshot sources (project-*, probe)
    res_snap = check_source_freshness("project-yonc-graph-p00001", "2026-10-20", now_morning)
    assert res_snap["freshness"] == "SNAPSHOT" and not res_snap["is_expired"]


def test_library_issues_filters_expired_sources(tmp_path):
    mod = load_commands()
    intake = tmp_path / "intake"
    intake.mkdir()
    today_str = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%Y-%m-%d")
    # Source A: COMPLETE and fresh
    mA = {"device": "workstation", "source": "srcA", "scheduled_date": today_str,
          "batch_id": f"librarian:workstation:srcA:{today_str}", "revision": 1,
          "coverage": "COMPLETE", "entries": [{"status": "CAPTURED"}]}
    # Source B: COMPLETE but EXPIRED (2026-10-20)
    mB = {"device": "workstation", "source": "srcB", "scheduled_date": "2026-10-20",
          "batch_id": "librarian:workstation:srcB:2026-10-20", "revision": 1,
          "coverage": "COMPLETE", "entries": [{"status": "CAPTURED"}]}
    with sqlite3.connect(intake / "recovery-intake.sqlite") as db:
        db.execute("CREATE TABLE manifest_revisions(batch_id,revision,sha256,raw)")
        db.execute("INSERT INTO manifest_revisions VALUES(?,?,?,?)", (mA["batch_id"], 1, "shaA", json.dumps(mA)))
        db.execute("INSERT INTO manifest_revisions VALUES(?,?,?,?)", (mB["batch_id"], 1, "shaB", json.dumps(mB)))
    with sqlite3.connect(intake / "recovery-publication.sqlite") as db:
        db.execute("CREATE TABLE publications(batch_id,revision,sha256)")
        db.execute("INSERT INTO publications VALUES(?,?,?)", (mA["batch_id"], 1, "shaA"))
        db.execute("INSERT INTO publications VALUES(?,?,?)", (mB["batch_id"], 1, "shaB"))
    (tmp_path / "intake-policy.json").write_text(json.dumps({
        "devices": {"workstation": ["srcA", "srcB"]},
    }))
    result = backup_overview(tmp_path)
    registered = {}
    ctx = SimpleNamespace(
        profile_name="librarian",
        call_mcp=lambda *a, **k: {"ok": True, "result": json.dumps(result)},
        get_config=lambda key, default: result["sources"],
        register_command=lambda name, handler, **k: registered.update({name: handler}),
    )
    mod.register(ctx)
    issues_text = registered["library-issues"]()
    # srcB is expired, so it must be included in issues!
    assert "srcB" in issues_text
    assert "已过期" in issues_text
    # srcA is fresh and COMPLETE, so it must NOT be in issues!
    assert "srcA" not in issues_text
