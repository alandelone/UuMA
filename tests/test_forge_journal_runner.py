from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from uuma.forge_journal import ForgeJournalStore
from uuma.forge_journal_runner import (
    ForgeJournalNotificationDispatcher,
    ForgeJournalRunner,
    HermesRouteResolver,
    _digest,
    load_notion_connection,
)


class FakeNotion:
    def __init__(self) -> None:
        self.pages: dict[str, dict[str, Any]] = {}
        self.blocks: dict[str, list[dict[str, Any]]] = {}
        self.deleted: list[str] = []
        self._sequence = 0
        self.snapshot_calls = 0

    def add_log(self, page_id: str = "page1", title: str = "Motor fault") -> dict[str, Any]:
        page = {
            "id": page_id,
            "url": f"https://notion.so/{page_id}",
            "last_edited_time": "2026-09-22T10:00:00Z",
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": title}]},
                "Project / System": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "UGV"}],
                },
                "Type": {"type": "select", "select": {"name": "Problem"}},
                "Sync Status": {"type": "select", "select": {"name": "Synced"}},
            },
        }
        self.pages[page_id] = page
        self.blocks[page_id] = [
            {
                "id": "original-1",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"plain_text": "Original note"}]},
            }
        ]
        return page

    def query_data_source(
        self, data_source_id: str, *, filter_body: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if data_source_id == "b68cd096-9176-4571-83f7-ddfa7c082bc7":
            return []
        pages = list(self.pages.values())
        if not filter_body:
            return pages
        expected = filter_body["title"]["equals"]
        property_name = filter_body["property"]
        return [
            page
            for page in pages
            if page["properties"][property_name]["title"][0]["plain_text"] == expected
        ]

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self.pages[page_id]

    def list_children(self, page_id: str) -> list[dict[str, Any]]:
        return [dict(block) for block in self.blocks[page_id]]

    def snapshot(self, page_id: str) -> dict[str, Any]:
        self.snapshot_calls += 1
        page = self.pages[page_id]
        properties = {
            key: value
            for key, value in page["properties"].items()
            if key != "Sync Status"
        }
        blocks = [
            {key: value for key, value in block.items() if key != "id"}
            for block in self.blocks[page_id]
        ]
        return {"properties": properties, "blocks": blocks}

    def page_record(self, page: dict[str, Any], journal_kind: str) -> dict[str, Any]:
        title_name = "Name" if journal_kind == "LOG" else "Statement"
        title = page["properties"][title_name]["title"][0]["plain_text"]
        return {
            "notion_page_id": page["id"],
            "notion_url": page["url"],
            "title": title,
            "project_system": "UGV" if journal_kind == "LOG" else "",
            "entry_type": "Problem" if journal_kind == "LOG" else "",
            "remote_edited_at": page["last_edited_time"],
            "journal_kind": journal_kind,
        }

    def append_children(
        self, page_id: str, children: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        appended = []
        for child in children:
            self._sequence += 1
            block = {**child, "id": f"added-{self._sequence}"}
            kind = block["type"]
            for rich_text in (block.get(kind) or {}).get("rich_text") or []:
                rich_text["plain_text"] = rich_text.get("text", {}).get("content", "")
            self.blocks[page_id].append(block)
            appended.append(block)
        return appended

    def delete_block(self, block_id: str) -> None:
        self.deleted.append(block_id)
        for page_id, blocks in self.blocks.items():
            self.blocks[page_id] = [block for block in blocks if block["id"] != block_id]

    def set_sync_status(self, page_id: str, status: str) -> None:
        self.pages[page_id]["properties"]["Sync Status"] = {
            "type": "select",
            "select": {"name": status},
        }

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        self.pages[page_id]["properties"].update(properties)
        return self.pages[page_id]

    def create_page(
        self,
        data_source_id: str,
        properties: dict[str, Any],
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        page_id = f"created-{len(self.pages) + 1}"
        page = {
            "id": page_id,
            "url": f"https://notion.so/{page_id}",
            "last_edited_time": "2026-09-22T10:01:00Z",
            "properties": properties,
        }
        self.pages[page_id] = page
        self.blocks[page_id] = []
        self.append_children(page_id, children)
        return page

    def find_by_marker(
        self, data_source_id: str, title_property: str, title: str, marker: str
    ) -> dict[str, Any] | None:
        for page in self.query_data_source(
            data_source_id,
            filter_body={"property": title_property, "title": {"equals": title}},
        ):
            if self.contains_marker(self.list_children(page["id"]), marker):
                return page
        return None

    @staticmethod
    def contains_marker(blocks: list[dict[str, Any]], marker: str) -> bool:
        return marker in json.dumps(blocks, ensure_ascii=False)


class FakeDispatcher:
    def __init__(self, store: ForgeJournalStore) -> None:
        self.store = store

    def dispatch_one(self) -> bool:
        notice = self.store.claim_notification("fake-dispatcher")
        if notice is None:
            return False
        self.store.finish_notification(
            notice["notification_id"], sent=True, worker_id="fake-dispatcher"
        )
        return True


def _runner(tmp_path: Path) -> tuple[ForgeJournalRunner, ForgeJournalStore, FakeNotion]:
    store = ForgeJournalStore(tmp_path / "lab.db")
    notion = FakeNotion()
    page = notion.add_log()
    snapshot = notion.snapshot("page1")
    store.register_snapshot(
        "page1",
        page["url"],
        "Motor fault",
        _digest(snapshot),
        project_system="UGV",
        entry_type="Problem",
        snapshot=snapshot,
    )
    runner = ForgeJournalRunner(store, notion, FakeDispatcher(store))
    return runner, store, notion


def test_runner_appends_visible_patch_and_records_remote_evidence(tmp_path: Path) -> None:
    runner, store, notion = _runner(tmp_path)
    page = store.status()["pages"][0]
    job = store.queue_write(
        "PATCH_LOG",
        {
            "change_summary": "Added measured current.",
            "change_reason": "Preserve bench evidence.",
            "observation": "2.4 A at stall.",
        },
        "patch-current-v1",
        journal_id=page["journal_id"],
    )

    result = runner.process_one()

    assert result is not None
    assert result["status"] == "SYNCED"
    assert result["appended_block_ids"]
    assert store.status()["counts"] == {"SYNCED": 1}
    rendered = json.dumps(notion.blocks["page1"], ensure_ascii=False)
    assert "LAB_BOT Enrichment" in rendered
    assert "Change Notice" in rendered
    assert f"LAB_BOT Sync: {job['idempotency_key']}" in rendered


def test_reconciliation_imports_remote_page_once(tmp_path: Path) -> None:
    store = ForgeJournalStore(tmp_path / "lab.db")
    notion = FakeNotion()
    notion.add_log()
    runner = ForgeJournalRunner(store, notion, FakeDispatcher(store))

    first = runner.reconcile()
    second = runner.reconcile()

    assert first == {"logs": 1, "candidates": 0, "conflicts": 0}
    assert second == first
    assert notion.snapshot_calls == 1
    assert store.status()["counts"] == {"SYNCED": 1}


def test_reversible_acceptance_restores_body_and_delivers_notice(tmp_path: Path) -> None:
    runner, store, notion = _runner(tmp_path)
    original = notion.snapshot("page1")

    result = runner.acceptance()

    assert result["write_status"] == "SYNCED"
    assert result["body_restored"] is True
    assert result["notification_status"] == "SENT"
    assert notion.snapshot("page1") == original
    assert len(notion.deleted) == 5
    assert store.status()["counts"] == {"SYNCED": 1}


def test_notification_dispatcher_uses_hermes_route_without_exposing_it(tmp_path: Path) -> None:
    _runner_instance, store, _notion = _runner(tmp_path)
    journal = store.status()["pages"][0]
    store.enqueue_notification(
        journal["journal_id"], "FAILED", "failed:test", {"reason": "fixture"}
    )
    calls: list[list[str]] = []

    def command_runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    dispatcher = ForgeJournalNotificationDispatcher(
        store,
        tmp_path / "hermes.exe",
        tmp_path / "profile",
        HermesRouteResolver([], explicit_target="telegram:fixture"),
        command_runner=command_runner,
    )

    assert dispatcher.dispatch_one() is True
    assert calls[0][1:5] == ["send", "--to", "telegram:fixture", "--quiet"]
    assert store.list_notifications()[0]["status"] == "SENT"


def test_connection_loader_reads_default_config_only(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    payload = {
        "mcp_servers": {
            "notion": {
                "env": {
                    "OPENAPI_MCP_HEADERS": json.dumps(
                        {"Authorization": "Bearer fixture", "Notion-Version": "2025-09-03"}
                    )
                }
            }
        }
    }
    yaml = YAML()
    with config.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle)

    headers = load_notion_connection(config)

    assert headers["Authorization"] == "Bearer fixture"
    assert headers["Notion-Version"] == "2025-09-03"


def test_windows_runner_scripts_use_event_driven_one_shot_contract() -> None:
    root = Path(__file__).parents[1] / "scripts"
    installer = (root / "install-forge-journal-runner.ps1").read_text(encoding="utf-8")
    manager = (root / "manage-forge-journal-runner.ps1").read_text(encoding="utf-8")

    assert "UuMA Forge Journal Runner" in installer
    assert "UuMA Forge Journal Watchdog" in installer
    assert "--reconcile-seconds" in installer
    assert '"--once"' in installer
    assert "New-ScheduledTaskTrigger" not in installer
    assert "-StartWhenAvailable" not in installer
    assert "Disable-ScheduledTask -TaskName $name" in installer
    assert "Export-ScheduledTask" in installer
    assert "-AllowStartIfOnBatteries" in installer
    assert "-DontStopIfGoingOnBatteries" in installer
    assert "-RestartCount" not in installer
    assert "-RestartInterval" not in installer
    assert "-MultipleInstances IgnoreNew" in installer
    assert "lab-before-forge-journal-runner" in installer
    assert '"acceptance"' in manager
    assert "--acceptance" in manager
    assert "Disable-ScheduledTask" in manager
    assert '"migrate"' in manager
    assert "Run migrate before start" in manager
    assert '"Armed"' in manager
    deploy = (root / "deploy-hermes.ps1").read_text(encoding="utf-8")
    forge_install = deploy.split('scripts\\install-forge-journal-runner.ps1', 1)[1]
    assert "-StartNow" not in forge_install.split("catch", 1)[0]
    assert not (root / "watch-forge-journal-runner.ps1").exists()
