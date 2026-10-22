import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from uuma.auth import TokenRegistry
from uuma.chatgpt_bridge import BridgeStore


@pytest.fixture
def preparation(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/prepare-workstation-node.py"
    spec = importlib.util.spec_from_file_location("workstation_node_prepare_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    existing = tmp_path / "existing-workstation"
    local_registry = TokenRegistry(existing / "tokens.json")
    local_tokens = local_registry.initialize()
    registry = tmp_path / "new-control" / "tokens.json"
    new_tokens = TokenRegistry(registry).initialize()
    identities = registry.parent / "identities"
    identities.mkdir()
    for identity, token in new_tokens.items():
        (identities / (identity + ".token")).write_text(token, encoding="utf-8")
    arguments = {
        "destination": tmp_path / "preview", "data_dir": existing,
        "bridge_database": tmp_path / "chatgpt.db", "token_registry": registry,
        "identity_token_dir": identities, "control_url": "http://127.0.0.1:18765",
        "python": Path("isolated-python"), "source_root": path.parents[1],
    }
    return module, arguments, local_tokens, new_tokens


def test_preview_preserves_two_hops_and_never_serializes_credentials(preparation):
    module, arguments, local_tokens, new_tokens = preparation
    BridgeStore(arguments["bridge_database"]).add_account("existing", "test-identity", "Personal")
    before = hashlib.sha256(arguments["bridge_database"].read_bytes()).hexdigest()
    result = module.prepare(**arguments)
    assert result["status"] == "PREPARED"
    assert result["credentials_copied"] is False
    assert result["services_started"] is False
    assert result["history_not_restored"] is False
    destination = arguments["destination"]
    environment = json.loads((destination / "node-environment.json").read_text())
    assert environment["UUMA_DATA_DIR"] == str(arguments["data_dir"])
    assert environment["UUMA_IDENTITY_TOKEN_DIR"] == str(arguments["identity_token_dir"])
    assert environment["UUMA_CHATGPT_DATABASE_PATH"] == str(arguments["bridge_database"])
    assert result["inner_bridge_api_token_registry"] == str(arguments["data_dir"] / "tokens.json")
    assert result["server_chatgpt_remote_mcp_url"] == "http://127.0.0.1:8770/mcp"
    assert result["stt_proxy_available"] is False
    combined = "\n".join(path.read_text() for path in destination.glob("*.json"))
    for token in [*local_tokens.values(), *new_tokens.values()]:
        assert token not in combined
    assert hashlib.sha256(arguments["bridge_database"].read_bytes()).hexdigest() == before


def test_corrupt_bridge_blocks_without_creating_an_empty_replacement(preparation):
    module, arguments, _, _ = preparation
    source = arguments["bridge_database"]
    source.write_bytes(b"preserve this corrupt sqlite original")
    before = source.read_bytes()
    result = module.prepare(**arguments)
    assert result["status"] == "BLOCKED"
    assert "BRIDGE_DATABASE_UNREADABLE" in result["blockers"]
    assert source.read_bytes() == before
    assert not (arguments["destination"] / "node-config.json").exists()
    assert not (arguments["destination"] / "state").exists()


def test_explicit_empty_bridge_candidate_preserves_corrupt_source_and_browser_paths(preparation):
    module, arguments, _, _ = preparation
    source = arguments["bridge_database"]
    source.write_bytes(b"preserve this corrupt sqlite original")
    before = source.read_bytes()
    result = module.prepare(**arguments, allow_empty_bridge=True)
    assert result["status"] == "PREPARED"
    assert result["history_not_restored"] is True
    assert result["account_routes_require_onboarding"] is True
    assert source.read_bytes() == before
    candidate = Path(result["bridge_database"])
    assert candidate != source
    assert candidate.name == "chatgpt.db"
    assert module.inspect_bridge(candidate)["usable"] is True
    assert set(module.inspect_bridge(candidate)["rows"].values()) == {0}
    assert result["browser_and_extension_data_dir"] == str(arguments["data_dir"])


def test_shared_control_database_is_never_used_as_new_bridge_owner(preparation):
    module, arguments, _, _ = preparation
    arguments["bridge_database"] = arguments["data_dir"] / "uuma.db"
    BridgeStore(arguments["bridge_database"])
    result = module.prepare(**arguments)
    assert result["status"] == "BLOCKED"
    assert "BRIDGE_REQUIRES_INDEPENDENT_DATABASE" in result["blockers"]


def test_bad_outer_identity_cannot_be_replaced_with_old_local_auth(preparation):
    module, arguments, _, _ = preparation
    (arguments["identity_token_dir"] / "brainstormer.token").write_text("incorrect")
    result = module.prepare(**arguments, allow_empty_bridge=True)
    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["OUTER_NODE_AND_CONTROL_CREDENTIALS_UNAVAILABLE"]
    assert not (arguments["destination"] / "node-config.json").exists()


def test_preparation_refuses_existing_preview(preparation):
    module, arguments, _, _ = preparation
    arguments["destination"].mkdir()
    marker = arguments["destination"] / "preserve.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        module.prepare(**arguments)
    assert marker.read_text() == "keep"
