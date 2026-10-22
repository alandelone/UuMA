import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from ruamel.yaml import YAML


def test_completion_deployment_preserves_other_settings_and_rejects_repeat(tmp_path, monkeypatch):
    source = Path(__file__).parents[1] / "scripts/deploy-honc-completion.py"
    spec = importlib.util.spec_from_file_location("honc_completion_deploy_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = tmp_path / "profiles/honc"
    plugin = profile / "plugins/honc_life"
    plugin.mkdir(parents=True)
    other = tmp_path / "profiles/yonc"
    other.mkdir()
    yaml = YAML()
    original = {
        "model": {"provider": "preserved", "default": "preserved-model"},
        "mcp_servers": {
            "honc-execution": {"env": {"ORIGINAL": "keep"}},
            "uuma-worker": {"unchanged": True},
        },
        "plugins": {"enabled": ["honc_life", "uuma_honc_commands"]},
        "platforms": {"telegram": {"unchanged": True}},
    }
    with (profile / "config.yaml").open("w", encoding="utf-8") as stream:
        yaml.dump(original, stream)
    with (other / "config.yaml").open("w", encoding="utf-8") as stream:
        yaml.dump(
            {"mcp_servers": {"yonc-project": {"env": {"YONC_API_URL": "http://127.0.0.1:8766"}}}},
            stream,
        )
    runtime = {
        "profile": "honc",
        "owner_id": "owner",
        "database_path": str(tmp_path / "honc.db"),
        "scheduler_job_id": "existing-job",
        "delivery_binding": {"platform": "telegram", "chat_id": "chat"},
    }
    (plugin / "runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
    (plugin / "__init__.py").write_bytes(b"# existing plugin\r\n")
    (plugin / "plugin.yaml").write_bytes(b"name: honc_life\r\n")
    (profile / "SOUL.md").write_text("Existing custom user instructions\n", encoding="utf-8")
    (profile / ".env").write_bytes(b"preserve fixture credentials\r\n")
    before = (profile / "config.yaml").read_bytes()
    monkeypatch.setattr(
        module.httpx,
        "get",
        lambda url, **kw: httpx.Response(
            200, json={"database_id": "isolated-db"}, request=httpx.Request("GET", url)
        ),
    )
    result = module.deploy(profile, tmp_path / "backup")
    after = yaml.load((profile / "config.yaml").read_text(encoding="utf-8"))
    assert after["model"] == original["model"]
    assert after["plugins"] == original["plugins"] and after["platforms"] == original["platforms"]
    assert after["mcp_servers"]["uuma-worker"] == original["mcp_servers"]["uuma-worker"]
    assert after["mcp_servers"]["honc-execution"]["env"] == {
        "ORIGINAL": "keep",
        "YONC_GRAPH_URL": "http://127.0.0.1:8766",
        "YONC_GRAPH_DATABASE_ID": "isolated-db",
    }
    assert result["existing_life_runtime_fields_preserved"]
    saved_runtime = json.loads((plugin / "runtime.json").read_text(encoding="utf-8"))
    assert all(saved_runtime[k] == v for k, v in runtime.items())
    assert saved_runtime["work_completion"]["enabled"]
    assert (tmp_path / "backup/config.yaml").read_bytes() == before
    assert (profile / ".env").read_bytes() == b"preserve fixture credentials\r\n"
    assert "Existing custom user instructions" in (profile / "SOUL.md").read_text(encoding="utf-8")
    frozen = {p: p.read_bytes() for p in profile.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="already installed"):
        module.deploy(profile, tmp_path / "second-backup")
    assert all(p.read_bytes() == content for p, content in frozen.items())
    assert not (tmp_path / "second-backup").exists()
