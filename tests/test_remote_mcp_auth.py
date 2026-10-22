from starlette.applications import Starlette
from starlette.testclient import TestClient

from uuma.auth import TokenRegistry
from uuma.remote_mcp import AgentAuthentication, create_app


def test_semantic_mcp_rejects_wrong_roles_and_missing_bearer(tmp_path):
    registry = TokenRegistry(tmp_path / "tokens.json")
    tokens = registry.initialize()
    with TestClient(create_app(registry)) as client:
        assert client.post("/control/", json={}).status_code == 403
        assert (
            client.post(
                "/control/",
                json={},
                headers={
                    "Authorization": "Bearer " + tokens["wisdom-oldman"],
                    "X-Uuma-Identity": "wisdom-oldman",
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/knowledge/",
                json={},
                headers={
                    "Authorization": "Bearer " + tokens["honc"],
                    "X-Uuma-Identity": "honc",
                },
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/knowledge/",
                json={},
                headers={
                    "Authorization": tokens["orchestrator"],
                    "X-Uuma-Identity": "orchestrator",
                },
            ).status_code
            == 403
        )


def test_explicitly_empty_identity_allowlist_disables_access(tmp_path):
    registry = TokenRegistry(tmp_path / "tokens.json")
    token = registry.initialize()["orchestrator"]
    app = AgentAuthentication(Starlette(), registry, allowed=set())
    with TestClient(app) as client:
        assert client.get("/", headers={"Authorization": "Bearer " + token}).status_code == 403


def test_cli_uses_existing_identity_registry_separate_from_domain(tmp_path, monkeypatch):
    import sys

    import uvicorn

    from uuma import remote_mcp

    path = tmp_path / "control" / "tokens.json"
    path.parent.mkdir()
    token = TokenRegistry(path).initialize()["orchestrator"]
    domain = tmp_path / "domain"
    monkeypatch.setenv("UUMA_DATA_DIR", str(domain))
    monkeypatch.setattr(sys, "argv", ["remote_mcp", "--token-registry", str(path),
                                      "--services", "brainstormer"])
    observed = []

    def capture(app, **kwargs):
        observed.append(kwargs)
        # A valid identity reaches MCP's protocol checks, rather than auth rejection.
        with TestClient(app) as client:
            response = client.post("/brainstormer/", json={}, headers={
                "Authorization": "Bearer " + token, "X-Uuma-Identity": "orchestrator",
            })
            assert response.status_code != 403

    monkeypatch.setattr(uvicorn, "run", capture)
    remote_mcp.main()
    assert observed == [{"host": "127.0.0.1", "port": 8769}]
    assert not domain.exists()


def test_cli_refuses_missing_identity_registry(tmp_path, monkeypatch):
    import sys

    import pytest

    from uuma import remote_mcp

    path = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["remote_mcp", "--token-registry", str(path)])
    with pytest.raises(SystemExit) as exc:
        remote_mcp.main()
    assert exc.value.code == 2
    assert not path.exists()
