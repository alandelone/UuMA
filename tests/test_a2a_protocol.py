import pytest
from starlette.testclient import TestClient

from uuma.a2a_node import create_app
from uuma.auth import TokenRegistry
from uuma.node_journal import NodeJournal

pytest.importorskip("a2a", reason="Install the pinned distributed extra for protocol tests")


def test_official_sdk_agent_card_and_dispatch(tmp_path):
    class Control:
        status = "PENDING"

        def require_run(self, run):
            return {
                "task_id": "task",
                "agent_id": "brainstormer",
                "execution_epoch": 1,
                "status": self.status,
                "source": "orchestrator",
            }

        def require_task(self, task):
            return {
                "assignee": "brainstormer",
                "current_run_id": "run",
                "contract": {"objective": "Compare"},
            }

    control = Control()

    class Adapter:
        async def start(self, key, payload):
            control.status = "REVIEW"
            return "runtime"

        async def get(self, reference):
            return {"status": "completed"}

        async def cancel(self, reference):
            return {"status": "stopping"}

    tokens = TokenRegistry(tmp_path / "tokens.json")
    token = tokens.initialize()["orchestrator"]
    app = create_app(
        control,
        NodeJournal(tmp_path / "node.db"),
        tokens,
        {
            "brainstormer": {
                "adapter": Adapter(),
                "endpoint": "http://127.0.0.1:8768/agents/brainstormer",
            },
        },
    )
    with TestClient(app) as client:
        card_path = "/agents/brainstormer/.well-known/agent-card.json"
        assert client.get(card_path).status_code == 403
        headers = {
            "Authorization": "Bearer " + token,
            "X-Uuma-Identity": "orchestrator",
            "A2A-Version": "1.0",
        }
        card = client.get(card_path, headers=headers)
        assert card.status_code == 200
        assert card.json()["supportedInterfaces"][0]["protocolVersion"] == "1.0"
        assert (
            card.json()["securitySchemes"]["bearer"]["httpAuthSecurityScheme"]["scheme"] == "bearer"
        )
        assert (
            client.get(card_path, headers={"Authorization": "Bearer " + token}).status_code == 200
        )
        assert (
            client.get(
                card_path,
                headers={
                    "Authorization": "Bearer " + token,
                    "X-Uuma-Identity": "honc",
                },
            ).status_code
            == 403
        )
        response = client.post(
            "/agents/brainstormer/rpc",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": "request",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": "message",
                        "role": "ROLE_USER",
                        "parts": [{"text": "Run approved task"}],
                    },
                    "metadata": {"uuma_run_id": "run", "execution_epoch": 1},
                },
            },
        )
        assert response.status_code == 200, response.text
        assert "error" not in response.json(), response.text
        assert control.status == "REVIEW"
