import importlib.util
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location(
    "pool_worker_binding", Path(__file__).parents[1] / "scripts/configure-pool-worker.py"
)
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)


@pytest.fixture
def setup(tmp_path):
    profile = tmp_path / "profiles/brainstormer"
    template = tmp_path / "template"
    source = tmp_path / "source"
    pool = tmp_path / "pool"
    workspace = tmp_path / "workspace"
    for directory in (profile, template, source / "uuma", pool, workspace):
        directory.mkdir(parents=True)
    (source / "uuma/gemini_worker.py").write_text("# candidate\n", encoding="utf-8")
    (pool / "pool.json").write_text("{}", encoding="utf-8")
    wrapper = tmp_path / "agy-pool"
    wrapper.write_text("# pinned wrapper\n", encoding="utf-8")
    python = tmp_path / "python"
    python.write_text("# pinned interpreter\n", encoding="utf-8")
    (profile / "config.yaml").write_text(yaml.safe_dump({
        "model": {"default": "existing"}, "mcp_servers": {"uuma-worker": {"existing": True}},
    }), encoding="utf-8")
    (profile / "SOUL.md").write_text("Original role 角色", encoding="utf-8")
    (template / "config.yaml").write_text(yaml.safe_dump({"mcp_servers": {"gemini-worker": {
        "command": str(python), "args": ["-m", "uuma.mcp_gemini"], "timeout": 600,
        "env": {"UUMA_AGENT_ID": "brainstormer", "GEMINI_WORKER_APPROVAL_MODE": "plan",
                "UUMA_IDENTITY_TOKEN_FILE": "/server/brainstormer.token"},
    }}}), encoding="utf-8")
    return (profile, template, source, wrapper, pool, workspace, tmp_path / "receipts")


def test_manual_binding_preserves_role_identity_and_other_services(setup):
    original_soul = (setup[0] / "SOUL.md").read_bytes()
    original_config = (setup[0] / "config.yaml").read_bytes()
    result = binding.bind(*setup)
    actual = yaml.safe_load((setup[0] / "config.yaml").read_text(encoding="utf-8"))
    assert actual["model"] == {"default": "existing"}
    assert actual["mcp_servers"]["uuma-worker"] == {"existing": True}
    worker = actual["mcp_servers"]["gemini-worker"]
    assert worker["env"]["GEMINI_WORKER_BACKEND"] == "account_pool"
    assert worker["env"]["GEMINI_WORKER_APPROVAL_MODE"] == "plan"
    assert worker["env"]["UUMA_AGENT_ID"] == "brainstormer"
    assert worker["env"]["UUMA_IDENTITY_TOKEN_FILE"] == "/server/brainstormer.token"
    assert worker["env"]["GEMINI_WORKER_ALLOWED_ROOTS"] == str(setup[5])
    assert (setup[0] / "SOUL.md").read_bytes() == original_soul
    assert next(setup[0].glob("config.before-pool-worker-*.yaml")).read_bytes() == original_config
    assert result["new_login_required"] is False and result["services_restarted"] is False


@pytest.mark.parametrize("key,value", [("UUMA_AGENT_ID", "wisdom-oldman"),
                                      ("GEMINI_WORKER_APPROVAL_MODE", "auto_edit")])
def test_reject_wrong_identity_and_mode_before_mutation(setup, key, value):
    path = setup[1] / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["mcp_servers"]["gemini-worker"]["env"][key] = value
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    before = (setup[0] / "config.yaml").read_bytes()
    with pytest.raises(ValueError):
        binding.bind(*setup)
    assert (setup[0] / "config.yaml").read_bytes() == before
    assert not list(setup[0].glob("config.before-pool-worker-*"))
