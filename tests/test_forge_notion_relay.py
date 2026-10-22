"""The Forge relay exposes scoped semantics and durable receipts, never credentials."""

import json
import time
from uuid import uuid4

import httpx
import pytest
from starlette.testclient import TestClient

from uuma.forge_journal_runner import (
    DEFAULT_CANDIDATES_DATA_SOURCE as CANDIDATES,
)
from uuma.forge_journal_runner import (
    DEFAULT_LOGS_DATA_SOURCE as LOGS,
)
from uuma.forge_notion_relay import (
    UPSTREAM,
    JournalOperations,
    NotionRelayClient,
    NotionRelayError,
    create_app,
)

PAGE = "11342210-99b1-4b33-86c3-a558fba142a3"
BLOCK = "4366bdf4-bef6-455b-85c3-7702cd0b3a0e"


class Tokens:
    def verify(self, identity, token, role):
        return identity == "forge-lab-bot" and token == "fixture-forge" and role == "worker"


class Notion:
    def __init__(self):
        self.calls = []
        self.source = LOGS
        self.status = "Candidate"
        self.fail_after_write = False

    def retrieve_page(self, page_id):
        return {
            "id": page_id, "parent": {"data_source_id": self.source},
            "properties": {"Status": {"select": {"name": self.status}}},
        }

    def create_page(self, data_source_id, properties, children):
        self.calls.append((data_source_id, properties, children))
        if self.fail_after_write:
            raise TimeoutError("fixture response lost after write")
        return {"id": PAGE}

    def query_data_source(self, data_source_id, filter_body=None):
        return [{"id": PAGE}]

    def update_page(self, page_id, properties):
        self.calls.append((page_id, properties))
        return {"id": page_id}

    def _request(self, method, path):
        assert method == "GET" and path == "blocks/" + BLOCK
        return {"parent": {"page_id": PAGE}}

    def delete_block(self, block_id):
        self.calls.append(block_id)


def body(operation="create_page", arguments=None):
    return {
        "request_id": uuid4().hex, "operation": operation,
        "arguments": arguments if arguments is not None else {
            "data_source_id": LOGS, "properties": {}, "children": [],
        },
        "expires_at": time.time() + 300,
    }


def headers(identity="forge-lab-bot", token="fixture-forge"):
    return {"X-Uuma-Identity": identity, "Authorization": "Bearer " + token}


def client(tmp_path, notion):
    return TestClient(create_app(tokens=Tokens(), notion=notion, receipts=tmp_path / "relay.db"))


def test_missing_or_mismatched_identity_cannot_call(tmp_path):
    notion = Notion()
    with client(tmp_path, notion) as c:
        assert c.post("/call", json=body()).status_code == 403
        assert c.post("/call", json=body(), headers=headers("orchestrator")).status_code == 403
        assert c.post("/call", json=body(), headers=headers(token="other")).status_code == 403
    assert notion.calls == []


def test_duplicate_completed_request_returns_receipt_without_second_write(tmp_path):
    notion = Notion()
    request = body()
    with client(tmp_path, notion) as c:
        first = c.post("/call", json=request, headers=headers())
        second = c.post("/call", json=request, headers=headers())
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert c.get("/receipts/" + request["request_id"], headers=headers()).json() == first.json()
    assert len(notion.calls) == 1
    assert notion.api_root == UPSTREAM


def test_uncertain_write_survives_restart_without_blind_replay(tmp_path):
    notion = Notion()
    notion.fail_after_write = True
    request = body()
    with client(tmp_path, notion) as c:
        response = c.post("/call", json=request, headers=headers())
        assert response.status_code == 409
        assert response.json()["state"] == "UNCERTAIN"
    notion.fail_after_write = False
    with client(tmp_path, notion) as c:
        response = c.post("/call", json=request, headers=headers())
        assert response.status_code == 409
        assert response.json()["state"] == "UNCERTAIN"
    assert len(notion.calls) == 1


def test_request_id_cannot_be_rebound_to_different_arguments(tmp_path):
    notion = Notion()
    request = body()
    with client(tmp_path, notion) as c:
        assert c.post("/call", json=request, headers=headers()).status_code == 200
        request["arguments"]["properties"] = {"Name": {"title": []}}
        assert c.post("/call", json=request, headers=headers()).status_code == 409
    assert len(notion.calls) == 1


@pytest.mark.parametrize("expiry", [-10, 1900])
def test_expired_or_excessive_lifetime_is_rejected(tmp_path, expiry):
    notion = Notion()
    request = body()
    request["expires_at"] = time.time() + expiry
    with client(tmp_path, notion) as c:
        assert c.post("/call", json=request, headers=headers()).status_code == 409
    assert notion.calls == []


def test_unknown_operation_and_arbitrary_upstream_cannot_be_used(tmp_path):
    notion = Notion()
    with client(tmp_path, notion) as c:
        assert c.post("/call", json=body("_request", {"method": "POST", "path": "anything"}),
                      headers=headers()).status_code == 403
        request = body()
        request["url"] = "https://example.invalid"
        assert c.post("/call", json=request, headers=headers()).status_code == 422
    assert notion.calls == []


def test_unrelated_source_and_non_candidate_write_are_denied():
    notion = Notion()
    service = JournalOperations(notion, logs_data_source=LOGS, candidates_data_source=CANDIDATES)
    with pytest.raises(PermissionError):
        service.call("create_page", {"data_source_id": str(uuid4()), "properties": {}, "children": []})
    with pytest.raises(PermissionError):
        service.call("create_page", {
            "data_source_id": CANDIDATES,
            "properties": {"Status": {"select": {"name": "Accepted"}}}, "children": [],
        })
    notion.source, notion.status = CANDIDATES, "Accepted"
    with pytest.raises(PermissionError):
        service.call("update_page", {"page_id": PAGE, "properties": {"Scope": {"rich_text": []}}})
    with pytest.raises(PermissionError):
        service.call("delete_block", {"block_id": BLOCK})
    assert notion.calls == []


def test_client_sends_once_and_does_not_follow_redirects():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(307, headers={"Location": "https://example.invalid/steal"})

    relay = NotionRelayClient("http://127.0.0.1:8775", "fixture-forge",
                             transport=httpx.MockTransport(handler))
    with pytest.raises(NotionRelayError) as exc:
        relay.retrieve_page(PAGE)
    assert len(seen) == 1
    assert len(exc.value.request_id) == 32


def test_client_transport_failure_never_retries():
    seen = []

    def handler(request):
        seen.append(request)
        raise httpx.ReadTimeout("fixture", request=request)

    relay = NotionRelayClient("http://127.0.0.1:8775", "fixture-forge",
                             transport=httpx.MockTransport(handler))
    with pytest.raises(NotionRelayError):
        relay.retrieve_page(PAGE)
    assert len(seen) == 1


def test_new_client_retry_of_same_job_reuses_mutation_identity():
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(409, json={"state": "UNCERTAIN"})

    for _ in range(2):
        relay = NotionRelayClient("http://127.0.0.1:8775", "fixture-forge",
                                 transport=httpx.MockTransport(handler))
        with relay.execution("same-sync-job"), pytest.raises(NotionRelayError):
            relay.create_page(LOGS, {}, [])
    assert seen[0]["request_id"] == seen[1]["request_id"]


def test_completed_receipt_survives_renewed_transport_expiry(tmp_path):
    notion = Notion()
    request = body()
    with client(tmp_path, notion) as c:
        assert c.post("/call", json=request, headers=headers()).status_code == 200
        request["expires_at"] = time.time() + 1700
        assert c.post("/call", json=request, headers=headers()).status_code == 200
    assert len(notion.calls) == 1
