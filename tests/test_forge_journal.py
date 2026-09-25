from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest

from uuma.forge_journal import ForgeJournalStore, JournalSyncError, main


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture()
def journal(tmp_path):
    clock = MutableClock()
    store = ForgeJournalStore(tmp_path / "lab.db", clock=clock)
    return store, clock


def _snapshot(store: ForgeJournalStore, content_hash: str = "remote-v1") -> dict[str, object]:
    return store.register_snapshot(
        "notion-page-1",
        "https://notion.so/notion-page-1",
        "Motor driver fault",
        content_hash,
        remote_edited_at="2026-09-22T09:00:00Z",
        project_system="UGV",
        entry_type="Problem",
        snapshot={"raw_note": "Driver overheated."},
    )


def test_snapshot_queue_and_idempotency(journal) -> None:
    store, _clock = journal
    registered = _snapshot(store)
    assert registered["sync_status"] == "SYNCED"

    with pytest.raises(JournalSyncError, match="change_summary"):
        store.queue_write(
            "PATCH_LOG",
            {"change_reason": "Structure the observation."},
            "patch-1",
            journal_id=str(registered["journal_id"]),
        )

    payload = {
        "change_summary": "Added LAB_BOT Enrichment with separated observation and hypothesis.",
        "change_reason": "Preserve epistemic boundaries.",
        "append_blocks": ["LAB_BOT Enrichment", "Change Notice"],
    }
    first = store.queue_write(
        "PATCH_LOG", payload, "patch-1", journal_id=str(registered["journal_id"])
    )
    second = store.queue_write(
        "PATCH_LOG", payload, "patch-1", journal_id=str(registered["journal_id"])
    )
    assert first["sync_job_id"] == second["sync_job_id"]
    assert store.status()["counts"] == {"QUEUED": 1}

    with pytest.raises(JournalSyncError, match="different journal request"):
        store.queue_write(
            "PATCH_LOG",
            {**payload, "change_reason": "Different request."},
            "patch-1",
            journal_id=str(registered["journal_id"]),
        )


def test_concurrent_notion_edit_becomes_visible_conflict(journal) -> None:
    store, _clock = journal
    registered = _snapshot(store)
    store.queue_write(
        "PATCH_LOG",
        {"change_summary": "Add structured result.", "change_reason": "Improve traceability."},
        "patch-conflict",
        journal_id=str(registered["journal_id"]),
    )

    conflict = _snapshot(store, "remote-v2")

    assert conflict == {
        "journal_id": registered["journal_id"],
        "sync_status": "CONFLICT",
        "conflict": True,
    }
    status = store.status(notion_page_id="notion-page-1")
    assert status["pages"][0]["sync_status"] == "CONFLICT"
    assert status["pending_notifications"] == 1
    assert store.list_notifications()[0]["event_type"] == "CONFLICT"
    with pytest.raises(JournalSyncError, match="explicit human resolution"):
        store.request_resync("notion-page-1", "retry", "resync-conflict")


def test_unchanged_remote_snapshot_does_not_hide_queued_write(journal) -> None:
    store, _clock = journal
    registered = _snapshot(store)
    store.queue_write(
        "PATCH_LOG",
        {"change_summary": "Add result.", "change_reason": "Preserve the outcome."},
        "patch-still-queued",
        journal_id=str(registered["journal_id"]),
    )

    refreshed = _snapshot(store, "remote-v1")

    assert refreshed["sync_status"] == "QUEUED"
    assert store.status()["counts"] == {"QUEUED": 1}


def test_retry_then_verified_recovery_requires_remote_evidence(journal) -> None:
    store, clock = journal
    job = store.queue_write(
        "CREATE_LOG",
        {"title": "Bench note", "type": "Experiment"},
        "create-1",
        title="Bench note",
        entry_type="Experiment",
        offline=True,
    )
    leased = store.claim_write("openclaw-sync")
    assert leased is not None
    assert leased["sync_job_id"] == job["sync_job_id"]
    retry = store.finish_write(
        str(job["sync_job_id"]),
        succeeded=False,
        worker_id="openclaw-sync",
        error="Notion temporarily unavailable.",
    )
    assert retry == {"sync_job_id": job["sync_job_id"], "status": "QUEUED", "retrying": True}
    assert store.claim_write("openclaw-sync") is None

    clock.advance(seconds=60)
    leased_again = store.claim_write("openclaw-sync")
    assert leased_again is not None
    with pytest.raises(JournalSyncError, match="remote_content_hash"):
        store.finish_write(
            str(job["sync_job_id"]), succeeded=True, worker_id="openclaw-sync"
        )
    synced = store.finish_write(
        str(job["sync_job_id"]),
        succeeded=True,
        worker_id="openclaw-sync",
        remote_page_id="notion-created-1",
        remote_url="https://notion.so/notion-created-1",
        remote_edited_at="2026-09-22T10:01:00Z",
        remote_content_hash="notion-hash-1",
    )
    assert synced["status"] == "SYNCED"
    notices = store.list_notifications()
    assert {notice["event_type"] for notice in notices} == {
        "QUEUED_OFFLINE",
        "QUEUED_RETRY",
        "RECOVERED",
    }


def test_candidate_write_cannot_cross_review_boundary(journal) -> None:
    store, _clock = journal
    candidate = store.queue_write(
        "UPSERT_CANDIDATE",
        {"statement": "Use a strain relief.", "status": "Candidate"},
        "candidate-1",
        journal_kind="KNOWLEDGE_CANDIDATE",
    )
    assert candidate["operation"] == "UPSERT_CANDIDATE"

    with pytest.raises(PermissionError, match="only write Candidate"):
        store.queue_write(
            "UPSERT_CANDIDATE",
            {"statement": "Use a strain relief.", "status": "Accepted"},
            "candidate-accepted",
            journal_kind="KNOWLEDGE_CANDIDATE",
        )


def test_manual_resync_is_idempotent(journal) -> None:
    store, _clock = journal
    _snapshot(store)
    first = store.request_resync("notion-page-1", "Operator requested refresh.", "resync-1")
    second = store.request_resync("notion-page-1", "Operator requested refresh.", "resync-1")
    assert first["sync_job_id"] == second["sync_job_id"]
    assert first["direction"] == "PULL"
    assert first["operation"] == "REFRESH_PAGE"


def test_notification_outbox_retries_and_records_delivery(journal) -> None:
    store, clock = journal
    store.queue_write(
        "CREATE_LOG",
        {"title": "Offline note"},
        "offline-note",
        title="Offline note",
        offline=True,
    )
    notice = store.claim_notification("hermes-notifier")
    assert notice is not None
    retry = store.finish_notification(
        str(notice["notification_id"]),
        sent=False,
        worker_id="hermes-notifier",
        error="Route unavailable.",
    )
    assert retry["status"] == "QUEUED"
    assert store.claim_notification("hermes-notifier") is None

    clock.advance(seconds=60)
    claimed_again = store.claim_notification("hermes-notifier")
    assert claimed_again is not None
    sent = store.finish_notification(
        str(notice["notification_id"]), sent=True, worker_id="hermes-notifier"
    )
    assert sent == {
        "notification_id": notice["notification_id"],
        "status": "SENT",
        "retrying": False,
    }


def test_jsonl_import_cli_hashes_and_reconciles_snapshots(tmp_path) -> None:
    database = tmp_path / "lab.db"
    record = {
        "notion_page_id": "page-cli-1",
        "notion_url": "https://notion.so/page-cli-1",
        "title": "CLI imported log",
        "project_system": "Fixture",
        "entry_type": "Problem",
        "snapshot": {"body": "Original text"},
    }
    output = StringIO()

    result = main(
        ["--database", str(database), "import-snapshots"],
        stdin=StringIO(json.dumps(record) + "\n"),
        stdout=output,
    )

    assert result == 0
    assert json.loads(output.getvalue()) == {"conflicts": 0, "imported": 1}
    page = ForgeJournalStore(database).status()["pages"][0]
    assert page["notion_page_id"] == "page-cli-1"
    assert page["remote_content_hash"]

    second = {**record, "notion_page_id": "page-cli-2", "notion_url": "https://notion.so/2"}
    encoded = base64.b64encode(json.dumps(second).encode()).decode()
    chunked = "\n".join(encoded[index : index + 20] for index in range(0, len(encoded), 20))
    chunk_output = StringIO()
    assert main(
        [
            "--database",
            str(database),
            "import-snapshots",
            "--base64-chunks",
            "--expected-count",
            "1",
        ],
        stdin=StringIO(chunked + "\n.\n"),
        stdout=chunk_output,
    ) == 0
    assert json.loads(chunk_output.getvalue()) == {"conflicts": 0, "imported": 1}


def test_bootstrap_merges_hyphenated_and_compact_notion_page_ids(tmp_path) -> None:
    database = tmp_path / "lab.db"
    store = ForgeJournalStore(database)
    compact_id = "7cb9179db63a44c8b33c79c17e3dad14"
    store.register_snapshot(
        compact_id,
        f"https://notion.so/{compact_id}",
        "Original",
        "hash-old",
        snapshot={"body": "original"},
    )
    hyphenated_id = "7cb9179d-b63a-44c8-b33c-79c17e3dad14"
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO forge_journal_pages(
                journal_id, notion_page_id, notion_url, journal_kind, title,
                remote_content_hash, synced_remote_content_hash, snapshot_json,
                sync_status, last_synced_at, created_at, updated_at
            ) VALUES (
                'journal_duplicate', ?, ?, 'LOG', 'Latest', 'hash-new', 'hash-new',
                    '{"body":"latest"}', 'SYNCED', '2099-09-22T12:00:00+00:00',
                    '2026-09-22T11:00:00+00:00', '2099-09-22T12:00:00+00:00'
            )
            """,
            (hyphenated_id, f"https://notion.so/{hyphenated_id}"),
        )
        connection.execute(
            """
            INSERT INTO forge_journal_sync_events(
                event_id, journal_id, event_type, actor_id, occurred_at
            ) VALUES ('duplicate-event', 'journal_duplicate', 'FIXTURE', 'test',
                      '2026-09-22T12:00:00+00:00')
            """
        )

    migrated = ForgeJournalStore(database)

    status = migrated.status()
    assert len(status["pages"]) == 1
    assert status["pages"][0]["notion_page_id"] == compact_id
    assert status["pages"][0]["title"] == "Latest"
    with migrated.connect() as connection:
        event = connection.execute(
            "SELECT journal_id FROM forge_journal_sync_events WHERE event_id = 'duplicate-event'"
        ).fetchone()
    assert event["journal_id"] == status["pages"][0]["journal_id"]
