from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from uuma.specialist_file_guard import file_read_decision

PLUGIN_PATH = Path(__file__).parents[1] / "integrations/hermes/uuma_control_guard/__init__.py"
SPEC = importlib.util.spec_from_file_location("file_roots_guard_test_plugin", PLUGIN_PATH)
assert SPEC and SPEC.loader
PLUGIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLUGIN
SPEC.loader.exec_module(PLUGIN)


@pytest.fixture
def files(tmp_path, monkeypatch):
    own, workspace, other, credentials = [tmp_path / name for name in (
        "brainstormer", "workspace", "wisdom-oldman", "private-credentials"
    )]
    for directory in (own, workspace, other, credentials):
        directory.mkdir()
    for filename in (workspace / "project.md", other / "SOUL.md", credentials / "tokens.json",
                     credentials / "brainstormer.token", credentials / "pool.json",
                     own / "auth.json", own / ".env"):
        filename.write_text("fixture", encoding="utf-8")
    policy = json.dumps({"brainstormer": [str(own), str(workspace)]})
    monkeypatch.setenv("HERMES_PROFILE", "brainstormer")
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("UUMA_SPECIALIST_FILE_ROOTS_JSON", policy)
    monkeypatch.setattr(PLUGIN, "_profile", lambda: "brainstormer")
    PLUGIN._SESSIONS.clear()
    PLUGIN._state("registered").direct_run_id = "fixture-run"
    return own, workspace, other, credentials, policy


@pytest.mark.parametrize("tool", ["read_file", "search_files"])
def test_registered_run_allows_own_project_file_only(files, tool):
    _own, workspace, _other, _credentials, _policy = files
    assert PLUGIN._pre_tool_call(tool_name=tool, args={"path": str(workspace / "project.md")},
                                 session_id="registered") is None


@pytest.mark.parametrize("target", ["tokens.json", "brainstormer.token", "pool.json"])
@pytest.mark.parametrize("tool", ["read_file", "search_files"])
def test_registered_run_does_not_allow_other_identity_or_pool_credentials(files, target, tool):
    _own, _workspace, _other, credentials, _policy = files
    decision = PLUGIN._pre_tool_call(tool_name=tool, args={"path": str(credentials / target)},
                                    session_id="registered")
    assert decision["action"] == "block"


def test_other_profile_parent_traversal_and_proc_paths_are_denied(files):
    _own, workspace, other, _credentials, policy = files
    for path in (other / "SOUL.md", workspace / ".." / other.name / "SOUL.md",
                 Path("/proc/self/environ"), Path(workspace.anchor)):
        assert file_read_decision("brainstormer", "read_file", {"path": str(path)}, policy)[
            "action"
        ] == "block"


@pytest.mark.parametrize("config", ["", "bad", "null", "[]", "{}", '{"yonc": []}',
                                   '{"brainstormer": ["relative"]}'])
def test_invalid_or_missing_identity_roots_fail_closed(files, config):
    _own, workspace, _other, _credentials, _policy = files
    assert file_read_decision("brainstormer", "read_file",
                              {"path": str(workspace / "project.md")}, config)["action"] == "block"


@pytest.mark.parametrize("args", [None, {}, {"path": ""}, {"path": "."}, {"path": []}])
def test_omitted_and_ambiguous_paths_fail_closed(files, args):
    _own, _workspace, _other, _credentials, policy = files
    assert file_read_decision("brainstormer", "search_files", args, policy)["action"] == "block"


def test_nonexistent_multi_root_search_string_cannot_escape(files):
    _own, workspace, _other, credentials, policy = files
    for separator in (",", " "):
        value = str(workspace) + separator + str(credentials)
        assert file_read_decision("brainstormer", "search_files", {"path": value}, policy)[
            "action"
        ] == "block"


@pytest.mark.parametrize("filename", ["auth.json", ".env"])
def test_native_sensitive_file_denies_are_preserved(files, filename):
    own, _workspace, _other, _credentials, policy = files
    assert file_read_decision("brainstormer", "read_file", {"path": str(own / filename)}, policy)[
        "action"
    ] == "block"


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation requires a Windows privilege")
def test_symlink_escape_is_denied(files):
    _own, workspace, _other, credentials, policy = files
    (workspace / "alias").symlink_to(credentials, target_is_directory=True)
    decision = file_read_decision("brainstormer", "read_file",
                                 {"path": str(workspace / "alias/tokens.json")}, policy)
    assert decision["action"] == "block"


def test_unset_policy_preserves_existing_behavior_and_other_tools_are_unchanged(files, monkeypatch):
    _own, _workspace, _other, credentials, _policy = files
    monkeypatch.delenv("UUMA_SPECIALIST_FILE_ROOTS_JSON")
    assert PLUGIN._pre_tool_call(
        tool_name="read_file", args={"path": str(credentials / "pool.json")},
        session_id="registered"
    ) is None
    monkeypatch.setenv("UUMA_SPECIALIST_FILE_ROOTS_JSON", "invalid")
    assert PLUGIN._pre_tool_call(tool_name="mcp__uuma_worker__brainstormer_get_context", args={},
                                 session_id="registered") is None
