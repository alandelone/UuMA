import json
import subprocess
from pathlib import Path

import pytest

from uuma.release import ReleaseManager, preview, validate_preview


def commit(root, message):
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            message,
        ],
        check=True,
        capture_output=True,
    )
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/components.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "components": {
                    "shared": {"node": "server", "paths": ["shared.py"]},
                    "wisdom": {"node": "server", "paths": ["wisdom.md"], "depends_on": ["shared"]},
                    "honc": {"node": "server", "paths": ["honc.md"], "depends_on": ["shared"]},
                },
            }
        )
    )
    for name in ["shared.py", "wisdom.md", "honc.md"]:
        (tmp_path / name).write_text("initial")
    revision = commit(tmp_path, "baseline")
    baseline = preview(tmp_path, revision, {})
    actual = {
        "components": {
            name: {"revision": revision, "fingerprint": value["fingerprint"]}
            for name, value in baseline["components"].items()
        }
    }
    return tmp_path, actual


def test_only_wisdom_changes_and_honc_keeps_older_commit(repository):
    root, actual = repository
    (root / "wisdom.md").write_text("refined")
    revision = commit(root, "refine wisdom")
    plan = preview(root, revision, actual)
    assert plan["affected_components"] == ["wisdom"]
    assert plan["components"]["honc"]["status"] == "CURRENT"
    assert plan["components"]["honc"]["actual_revision"] != revision


def test_shared_dependency_expands_update(repository):
    root, actual = repository
    (root / "shared.py").write_text("updated")
    plan = preview(root, commit(root, "shared"), actual)
    assert plan["affected_components"] == ["honc", "shared", "wisdom"]


def test_preview_is_bound_to_actual_state_and_content(repository):
    root, actual = repository
    plan = preview(root, "HEAD", actual)
    validate_preview(root, plan, actual)
    altered = {**plan, "affected_components": ["honc"]}
    with pytest.raises(ValueError, match="stale"):
        validate_preview(root, altered, actual)


def test_active_work_defers_activation(repository):
    root, actual = repository
    state = root / "actual.json"
    state.write_text(json.dumps(actual))
    (root / "wisdom.md").write_text("refined")
    plan = preview(root, commit(root, "refine"), actual)

    class Backend:
        def pause_intake(self, components):
            assert components == ["wisdom"]

        def active_work(self, components):
            return ["long-running-work"]

    result = ReleaseManager(root, state, Backend()).apply(plan, "server")
    assert result["status"] == "WAITING_FOR_TASKS"
    assert json.loads(state.read_text()) == actual


def test_concurrent_or_interrupted_activation_cannot_repeat(repository):
    root, actual = repository
    state = root / "actual.json"
    state.write_text(json.dumps(actual))
    (root / ".release-apply.lock").write_text("interrupted activation")
    with pytest.raises(RuntimeError, match="reconciliation"):
        ReleaseManager(root, state, object()).apply(preview(root, "HEAD", actual), "server")
    assert json.loads(state.read_text()) == actual


def test_non_ascii_component_inputs_are_fingerprinted(repository):
    root, _actual = repository
    manifest = json.loads((root / "deploy/components.json").read_text())
    manifest["components"]["wisdom"]["paths"].append("细节.md")
    (root / "deploy/components.json").write_text(json.dumps(manifest))
    (root / "细节.md").write_text("initial", encoding="utf-8")
    baseline = preview(root, commit(root, "unicode baseline"), {})
    actual = {
        "components": {
            name: {"revision": baseline["target_revision"], "fingerprint": entry["fingerprint"]}
            for name, entry in baseline["components"].items()
        }
    }
    (root / "细节.md").write_text("refined", encoding="utf-8")
    assert preview(root, commit(root, "refine unicode"), actual)["affected_components"] == [
        "wisdom"
    ]


def test_unrelated_engine_pin_does_not_restart_agents(repository):
    root, _actual = repository
    manifest = json.loads((root / "deploy/components.json").read_text())
    manifest["engine_versions"] = {"unused": "version-one"}
    (root / "deploy/components.json").write_text(json.dumps(manifest))
    baseline = preview(root, commit(root, "engine baseline"), {})
    actual = {
        "components": {
            name: {"revision": baseline["target_revision"], "fingerprint": entry["fingerprint"]}
            for name, entry in baseline["components"].items()
        }
    }
    manifest["engine_versions"]["unused"] = "version-two"
    (root / "deploy/components.json").write_text(json.dumps(manifest))
    assert preview(root, commit(root, "unrelated engine"), actual)["affected_components"] == []


def test_missing_engine_pin_is_not_a_publishable_preview(repository):
    root, actual = repository
    manifest = json.loads((root / "deploy/components.json").read_text())
    manifest["components"]["shared"]["engines"] = ["missing-engine"]
    (root / "deploy/components.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unpinned"):
        preview(root, commit(root, "missing engine"), actual)


@pytest.fixture
def configured_components(tmp_path):
    """Exercise the real manifest against isolated, versioned component inputs."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "deploy/components.json").read_text(
            encoding="utf-8"
        )
    )
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy/components.json").write_text(json.dumps(manifest), encoding="utf-8")
    for component in manifest["components"].values():
        for pattern in component["paths"]:
            path = tmp_path / pattern.replace("*", "fixture")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("initial", encoding="utf-8")
    revision = commit(tmp_path, "component fixture baseline")
    baseline = preview(tmp_path, revision, {})
    actual = {
        "components": {
            name: {"revision": revision, "fingerprint": entry["fingerprint"]}
            for name, entry in baseline["components"].items()
        }
    }
    return tmp_path, actual


@pytest.mark.parametrize("source", ["src/uuma/gemini_worker.py", "src/uuma/mcp_gemini.py"])
def test_bounded_worker_updates_only_its_five_callers(configured_components, source):
    root, actual = configured_components
    (root / source).write_text("updated worker", encoding="utf-8")
    plan = preview(root, commit(root, "bounded worker update"), actual)
    assert plan["affected_components"] == [
        "brainstormer", "forge-lab-bot", "orchestrator", "scholar", "wisdom-oldman"
    ]
    assert plan["components"]["bounded-worker"]["status"] == "INPUT"
    for name in ("yonc", "honc", "control", "server-gateway", "workstation-gateway"):
        assert plan["components"][name]["status"] == "CURRENT"


@pytest.mark.parametrize("source", [
    "scripts/prepare-wisdom-cpu.py", "scripts/prepare-wisdom-bridge-deps.py",
    "deploy/wisdom/requirements-cpu.lock", "src/uuma/kag_llm_runtime.py",
    "src/uuma/kag_bridge.py",
])
def test_cpu_preparation_updates_only_knowledge_and_wisdom(configured_components, source):
    root, actual = configured_components
    (root / source).write_text("updated CPU preparation", encoding="utf-8")
    plan = preview(root, commit(root, "CPU preparation update"), actual)
    assert plan["affected_components"] == ["knowledge", "wisdom-oldman"]
    assert plan["components"]["scholar"]["status"] == "CURRENT"
    assert plan["components"]["server-gateway"]["status"] == "CURRENT"


def test_pool_worker_binding_discloses_shared_server_gateway_restart(configured_components):
    root, actual = configured_components
    (root / "scripts/configure-pool-worker.py").write_text("updated binding", encoding="utf-8")
    plan = preview(root, commit(root, "pool worker binding update"), actual)
    assert plan["affected_components"] == [
        "brainstormer", "forge-lab-bot", "honc", "server-gateway", "wisdom-oldman", "yonc"
    ]
    assert plan["components"]["server-gateway"]["status"] == "UPDATE"
    assert plan["components"]["server-gateway"]["restart_group"] == "server-gateway"
    for name in ("brainstormer", "forge-lab-bot", "honc", "wisdom-oldman", "yonc"):
        assert plan["components"][name]["status"] == "CURRENT"
    for name in ("orchestrator", "scholar", "workstation-gateway"):
        assert plan["components"][name]["status"] == "CURRENT"
