import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def binder():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bind-server-provider-pool.py"
    spec = importlib.util.spec_from_file_location("pool_binding", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def profile(tmp_path):
    plugin = tmp_path / "plugins" / "antigravity-oauth"
    plugin.mkdir(parents=True)
    files = {
        "process.py": ('from pathlib import Path\nimport os\n'
                       'def resolve_real_token_path():\n    """Original contract."""\n'
                       '    return Path("original")\n'),
        "account_pool.py": ('import os\n'
                            'def rotate_on_quota_error():\n    return "original"\n'
                            'def maybe_restore_primary_account():\n    return True\n'),
        "auth.py": ('from __future__ import annotations\n'
                    'def _run_login(agy):\n    return 0\n'),
        "client.py": ('import os\nclass Client:\n'
                      '    def _create_chat_completion_raw(self):\n'
                      '        resolved_model = "fake"\n'
                      '        effort, messages_list, effective_timeout = None, [], 10\n'
                      '        tools, tool_choice, stream = None, None, True\n'
                      '        worker_acquired = self._worker_lock.acquire(blocking=False)\n'
                      '        return worker_acquired\n'),
    }
    for name, body in files.items():
        (plugin / name).write_text(body, encoding="utf-8")
    (tmp_path / "config.yaml").write_text("model: original\nmcp_servers: original\n")
    (tmp_path / "SOUL.md").write_text("Keep role and approval rules.")
    return tmp_path


def test_binding_preserves_role_and_mcp_configuration(binder, profile):
    before = {name: (profile / name).read_bytes() for name in ["config.yaml", "SOUL.md"]}
    receipt = binder.bind(profile)
    assert set(receipt["files"]) == {"process.py", "account_pool.py", "auth.py", "client.py"}
    for name, body in before.items():
        assert (profile / name).read_bytes() == body
    assert "_run_oneshot_completion" in (
        profile / "plugins/antigravity-oauth/client.py"
    ).read_text()
    with pytest.raises(ValueError, match="already bound"):
        binder.bind(profile)


def test_binding_rejects_private_or_live_profile(binder, profile):
    (profile / ".env").write_text("PRIVATE=not-a-real-credential")
    with pytest.raises(ValueError, match="credential-free"):
        binder.bind(profile)


def test_changed_worker_contract_does_not_partially_patch_profile(binder, profile):
    plugin = profile / "plugins/antigravity-oauth"
    original = (plugin / "process.py").read_bytes()
    (plugin / "client.py").write_text("class Unexpected: pass\n")
    with pytest.raises(ValueError, match="worker layout changed"):
        binder.bind(profile)
    assert (plugin / "process.py").read_bytes() == original
