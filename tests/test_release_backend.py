import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_component_releases import commit

from uuma.release import ReleaseManager, preview
from uuma.release_backend import CommandReleaseBackend

pytest_plugins = ("test_component_releases",)


class Control:
    identity = "orchestrator"

    def __init__(self):
        self.requests = []
        self.runs = []

    def request(self, method, path, body):
        self.requests.append((method, path, body))

    def list_runs(self, *, agent_id=None, status=None):
        return [r for r in self.runs if r["agent_id"] == agent_id
                and (status is None or r["status"] == status)]


def configuration(root):
    return {
        "schema_version": 1,
        "node": "server",
        "release_root": str(root / "runtime-releases"),
        "components": {"wisdom": {"agents": ["wisdom-oldman"], "services": ["wisdom"]}},
        "services": {"wisdom": {phase: ["maintenance", phase]
                                  for phase in ["pause", "snapshot", "activate", "verify", "resume"]}},
    }


def runner(argv, **kwargs):
    assert kwargs["shell"] is False
    context = json.loads(kwargs["env"]["UUMA_DEPLOYMENT_CONTEXT"])
    evidence = {"plan_id": context["plan_id"]}
    phase = argv[1]
    if phase in {"pause", "snapshot"}:
        evidence.update(intake_paused=True, active=[], paused=[])
    if phase == "resume":
        evidence["intake_paused"] = False
    if phase == "verify":
        evidence.update(healthy=True, components={
            name: {"revision": context["revision"], "fingerprint": value}
            for name, value in context["fingerprints"].items()
        })
    return SimpleNamespace(returncode=0, stdout=json.dumps(evidence))


def change(repository):
    root, actual = repository
    (root / "wisdom.md").write_text("refined")
    revision = commit(root, "refine")
    state = root / "actual.json"
    state.write_text(json.dumps(actual))
    return root, actual, state, revision


def test_os_backend_materializes_fixed_revision_and_only_activates_changed_component(repository):
    root, actual, state, revision = change(repository)
    deployment = configuration(root)
    control = Control()
    plan = preview(root, revision, actual, deployment=deployment)
    result = ReleaseManager(root, state, CommandReleaseBackend(
        root, deployment, control=control, runner=runner
    )).apply(plan, "server")
    assert result["status"] == "VERIFIED"
    assert result["components"] == ["wisdom"]
    source = Path(result["prepared"]["source"])
    assert (source / "wisdom.md").read_text() == "refined"
    assert not (Path(deployment["release_root"]) / "current/honc.json").exists()
    assert json.loads(state.read_text())["components"]["honc"] == actual["components"]["honc"]
    assert [call[2]["paused"] for call in control.requests] == [True, False]


def test_os_hook_configuration_is_bound_to_preview(repository):
    root, actual, state, revision = change(repository)
    deployment = configuration(root)
    plan = preview(root, revision, actual, deployment=deployment)
    deployment["services"]["wisdom"]["activate"] = ["unexpected", "command"]
    control = Control()
    with pytest.raises(ValueError, match="stale"):
        ReleaseManager(root, state, CommandReleaseBackend(
            root, deployment, control=control, runner=runner
        )).apply(plan, "server")
    assert not control.requests


def test_runtime_work_defers_release_even_when_control_has_no_active_runs(repository):
    root, actual, state, revision = change(repository)
    deployment = configuration(root)

    def busy(argv, **kwargs):
        result = runner(argv, **kwargs)
        if argv[1] == "snapshot":
            body = json.loads(result.stdout)
            body["active"] = ["domain-job"]
            result.stdout = json.dumps(body)
        return result

    result = ReleaseManager(root, state, CommandReleaseBackend(
        root, deployment, control=Control(), runner=busy
    )).apply(preview(root, revision, actual, deployment=deployment), "server")
    assert result["status"] == "WAITING_FOR_TASKS"
    assert json.loads(state.read_text()) == actual


def test_paused_run_requires_retained_environment_and_resume_reference(repository):
    root, actual, state, revision = change(repository)
    deployment = configuration(root)
    control = Control()
    control.runs = [{"run_id": "paused-run", "agent_id": "wisdom-oldman", "status": "PAUSED"}]
    with pytest.raises(RuntimeError, match="no retained runtime environment"):
        ReleaseManager(root, state, CommandReleaseBackend(
            root, deployment, control=control, runner=runner
        )).apply(preview(root, revision, actual, deployment=deployment), "server")
    assert json.loads(state.read_text()) == actual
    assert [call[2]["paused"] for call in control.requests] == [True]


def test_failed_resume_cannot_leave_a_success_receipt(repository):
    root, actual, state, revision = change(repository)
    deployment = configuration(root)

    def failure(argv, **kwargs):
        if argv[1] == "resume":
            return SimpleNamespace(returncode=1, stdout="private output must not escape")
        return runner(argv, **kwargs)

    plan = preview(root, revision, actual, deployment=deployment)
    with pytest.raises(RuntimeError, match="hook failed"):
        ReleaseManager(root, state, CommandReleaseBackend(
            root, deployment, control=Control(), runner=failure
        )).apply(plan, "server")
    receipt = json.loads((root / "receipts" / (plan["plan_id"] + "-server.json")).read_text())
    assert receipt["status"] == "RECONCILIATION_REQUIRED"
