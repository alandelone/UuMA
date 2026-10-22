from uuid import uuid4

import pytest

from uuma.models import ResultContract, RunRegistration, TaskContract, VerificationDecision
from uuma.service import ControlPlane, PolicyDeniedError
from uuma.settings import Settings


@pytest.fixture
def control(tmp_path):
    instance = ControlPlane(
        Settings(
            data_dir=tmp_path,
            database_path=tmp_path / "uuma.db",
            artifact_dir=tmp_path / "artifacts",
            ingest_spool_dir=tmp_path / "spool",
            hermes_executable=tmp_path / "unused-hermes.exe",
        )
    )
    instance.bootstrap()
    return instance


def test_user_only_result_waits_even_without_automatic_acceptance_checks(control):
    task = control.create_task(
        TaskContract(
            title="Deliver project work",
            objective="Return a report for the user",
            required_capabilities={"brainstorming"},
            acceptance_authority="USER",
        ),
        actor_id="orchestrator",
    )
    control.assign_task(task.task_id, "brainstormer")
    run = control.register_run(
        RunRegistration(
            task_id=task.task_id,
            agent_id="brainstormer",
            execution_class="INTERACTIVE",
            source="orchestrator",
        ),
        actor_id="orchestrator",
    )
    control.submit_result(
        ResultContract(
            task_id=task.task_id,
            run_id=run.run_id,
            agent_id="brainstormer",
            outcome="COMPLETED",
            summary="The report is ready",
        ),
        actor_id="brainstormer",
    )
    context = control.verification_context(run.run_id)
    decision = VerificationDecision(
        task_id=task.task_id,
        run_id=run.run_id,
        approved=True,
        result_digest=context["result_digest"],
        acceptance_digest=context["acceptance_digest"],
    )
    assert context["acceptance_checks"] == []
    for actor in ("orchestrator", "scholar"):
        with pytest.raises(PolicyDeniedError, match="actual user"):
            control.verify_result(decision, actor_id=actor)
    assert control.require_run(run.run_id)["status"] == "REVIEW"
    control.verify_result(decision, actor_id="user")
    assert control.require_task(task.task_id)["status"] == "COMPLETED"


def test_legacy_task_idempotency_and_event_history_survive_new_acceptance_default(control):
    task = TaskContract(
        title="Older task",
        objective="Keep its original semantics",
        idempotency_key="before-user-review-field",
    )
    legacy = task.model_dump(mode="json", exclude={"acceptance_authority"})
    control.events.append(
        event_type="TASK_CREATED",
        aggregate_type="task",
        aggregate_id=task.task_id,
        actor_type="agent",
        actor_id="orchestrator",
        payload={"contract": legacy},
    )
    replay = TaskContract.model_validate({**legacy, "task_id": "task_" + uuid4().hex})
    assert control.create_task(replay, actor_id="orchestrator").task_id == task.task_id
    control.events.rebuild_projections()
    assert control.create_task(replay, actor_id="orchestrator").task_id == task.task_id
    assert control.events.verify_chain()[0]
