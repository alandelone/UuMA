import hashlib
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from test_studio_context import generated_fixture
from test_writing_studio import complete_document, create_studio, wait_for_job

from rstv4.database import transaction
from rstv4.studio_api import create_app


def test_current_object_history_requires_original_type_and_revision(tmp_path: Path):
    service, _, manuscript = create_studio(tmp_path)
    document = complete_document(service.get_workspace(manuscript))
    service.save_document(manuscript, base_revision=0, operation_id="first", document=document)
    service.gateway.analyze = lambda task, payload: {"answer": "Fixture reply"}
    old = service.discuss(manuscript, content="Original question", anchor_type="thought",
                          anchor_id="thought_author_1", anchor_revision=1)
    changed = deepcopy(service.get_workspace(manuscript)["document"])
    changed["sections"][0]["paragraphs"][0]["intents"][0]["thoughts"][0]["text"] = "Changed"
    service.save_document(manuscript, base_revision=1, operation_id="second", document=changed)
    new = service.discuss(manuscript, content="New question", anchor_type="thought",
                          anchor_id="thought_author_1", anchor_revision=2)
    with TestClient(create_app(tmp_path)) as client:
        endpoint = f"/api/manuscripts/{manuscript}/chat"
        before = hashlib.sha256(service.db_path.read_bytes()).hexdigest()
        for revision, expected in [(1, old), (2, new)]:
            rows = client.get(endpoint, params={"anchor_id": "thought_author_1",
                              "anchor_type": "thought", "anchor_revision": revision}).json()
            assert {row["message_id"] for row in rows} == {
                expected["author"]["message_id"], expected["agent"]["message_id"]}
        assert client.get(endpoint, params={"anchor_id": "thought_author_1",
                          "anchor_type": "intent", "anchor_revision": 1}).json() == []
        assert len(client.get(endpoint, params={"anchor_id": "thought_author_1"}).json()) == 4
        assert client.get(endpoint, params={"anchor_revision": -1}).status_code == 422
        assert hashlib.sha256(service.db_path.read_bytes()).hexdigest() == before


def test_generated_history_requires_the_exact_version_even_with_same_author_revision(tmp_path: Path):
    service, _, manuscript = create_studio(tmp_path)
    first = generated_fixture(service, manuscript)
    block = next(item for item in first["blocks"] if item["kind"] == "paragraph")
    service.gateway.analyze = lambda task, payload: {"answer": "Fixture discussion"}
    original = service.discuss(manuscript, content="Old generated question",
                               anchor_type="generated_paragraph", anchor_id=block["anchor_id"],
                               anchor_revision=1, quote={"generated_version_id": first["generated_version_id"]})
    service.gateway.analyze = lambda task, payload: {"paragraph": "New generated wording.",
                                                   "sentence_mappings": [{"sentence": 0, "thought_ids": ["thought_author_1"]}]}
    job = wait_for_job(service, service.create_job(manuscript, "GENERATE", input_revision=1))
    assert job["status"] == "SUCCEEDED", job
    second = service.get_generated_version(manuscript, job["result"]["generated_version_id"])
    second_block = next(item for item in second["blocks"] if item["kind"] == "paragraph")
    service.gateway.analyze = lambda task, payload: {"answer": "Fixture discussion"}
    current = service.discuss(manuscript, content="New generated question",
                              anchor_type="generated_paragraph", anchor_id=second_block["anchor_id"],
                              anchor_revision=1, quote={"generated_version_id": second["generated_version_id"]})
    for version, expected in [(first, original), (second, current)]:
        rows = service.list_chat(manuscript, anchor_type="generated_paragraph", anchor_revision=1,
                                 generated_version_id=version["generated_version_id"])
        assert {row["message_id"] for row in rows} == {
            expected["author"]["message_id"], expected["agent"]["message_id"]}
    assert service.get_chat_context(manuscript, original["author"]["message_id"])["generated"] == first


def test_message_cursor_preserves_tied_times_and_rejects_other_manuscript(tmp_path: Path):
    service, track, manuscript = create_studio(tmp_path)
    service.gateway.analyze = lambda task, payload: {"answer": "Fixture reply"}
    for index in range(4):
        service.discuss(manuscript, content=f"Question {index}", anchor_type="paper",
                        anchor_id=None, anchor_revision=0)
    foreign = service.create_manuscript(track, "Other manuscript")["manuscript"]["manuscript_id"]
    other = service.discuss(foreign, content="Other question", anchor_type="paper",
                            anchor_id=None, anchor_revision=0)
    timestamp = "2000-01-01T00:00:00+00:00"
    with transaction(service.db_path) as connection:
        connection.execute("UPDATE studio_chat_messages SET created_at=? WHERE manuscript_id=?",
                           (timestamp, manuscript))
    with TestClient(create_app(tmp_path)) as client:
        endpoint = f"/api/manuscripts/{manuscript}/chat"
        original = client.get(endpoint).json()
        page, collected = client.get(endpoint, params={"limit": 3}).json(), []
        while page:
            collected = page + collected
            cursor = page[0]
            page = client.get(endpoint, params={"limit": 3, "before": cursor["created_at"],
                              "before_message_id": cursor["message_id"]}).json()
        assert len(collected) == 8 and collected == original
        assert len({row["message_id"] for row in collected}) == 8
        assert client.get(endpoint, params={"before_message_id": other["author"]["message_id"]}).status_code == 404
        wrong = client.get(endpoint, params={"before_message_id": original[0]["message_id"],
                           "before": "wrong-time"})
        assert wrong.status_code == 422, wrong.text
