"""Reviewed experiment manifests and durable, single-execution request receipts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from .database import transaction
from .experiment import ExperimentResult, ExperimentRunner
from .fieldkg import digest
from .models import (
    DecisionProposalInput,
    ExperimentPlanInput,
    ResearchType,
    StrictModel,
    TrackFirstProjectInput,
    new_id,
)
from .research_types import REQUIRED_BLOCKS, validate_type_payload
from .research_views import parse_record, require, rows
from .research_workspace import WorkspaceError
from .track_first import _json, _now
from .track_scientific_workspace import (
    TrackScientificWorkspace,
    dependency_stamp,
    scientific_context,
)


class ExperimentAction(StrictModel):
    request_id: str = Field(min_length=8, max_length=200)
    track_id: str
    expected_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]


class CreateProject(ExperimentAction):
    operation: Literal["CREATE_PROJECT"]
    project: TrackFirstProjectInput


class ProposePlan(ExperimentAction):
    operation: Literal["PROPOSE_PLAN"]
    project_id: str | None = None
    plan: ExperimentPlanInput
    input_files: list[str] = Field(default_factory=list, max_length=200)
    artifact_paths: list[str] = Field(default_factory=list, max_length=200)
    environment: dict[str, str] = Field(default_factory=dict, max_length=100)
    expected_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ApplyPlan(ExperimentAction):
    operation: Literal["APPLY_PLAN"]
    plan_id: str
    expected_revision: int = Field(ge=1)


class StartPlan(ExperimentAction):
    operation: Literal["START_PLAN"]
    plan_id: str
    expected_revision: int = Field(ge=1)


class RecordResult(ExperimentAction):
    operation: Literal["RECORD_RESULT"]
    run_id: str
    statement: str = Field(min_length=1, max_length=16000)
    metric_key: str | None = None


ExperimentWorkspaceAction = Annotated[
    CreateProject | ProposePlan | ApplyPlan | StartPlan | RecordResult,
    Field(discriminator="operation"),
]


class ManifestPreview(StrictModel):
    project_id: str | None = None
    plan: ExperimentPlanInput
    input_files: list[str] = Field(default_factory=list, max_length=200)
    artifact_paths: list[str] = Field(default_factory=list, max_length=200)
    environment: dict[str, str] = Field(default_factory=dict, max_length=100)


class ExperimentWorkspace(TrackScientificWorkspace):
    def _read(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise WorkspaceError(503, "Catalog database is unavailable")
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        return conn

    @staticmethod
    def _method(context: dict[str, Any], method_id: str) -> dict[str, Any]:
        node = next((n for n in context["nodes"] if n["node_id"] == method_id), None)
        if node is None or node["node_type"] != "method" or node["status"] != "APPROVED":
            raise WorkspaceError(409, "Choose a currently approved Method in this Track")
        proposal = DecisionProposalInput(
            kind="method",
            statement=node["statement"],
            rationale=node["rationale"] or "Method",
            evidence_ids=node["payload"].get("evidence_ids", []),
            upstream_node_ids=[method_id],
        )
        TrackScientificWorkspace._validate_dependencies(context, proposal)
        return dependency_stamp(context, proposal)

    @staticmethod
    def _receipts(conn: sqlite3.Connection, track_id: str) -> list[dict[str, Any]]:
        return [
            json.loads(r[0])
            for r in conn.execute(
                """SELECT result_json FROM research_workspace_actions
               WHERE object_type LIKE 'experiment_%' ORDER BY action_seq"""
            )
            if json.loads(r[0]).get("track_id") == track_id
        ]

    def context(self, track_id: str) -> dict[str, Any]:
        with closing(self._read()) as conn:
            science = scientific_context(conn, track_id)
            projects = [
                parse_record(p)
                for p in rows(
                    conn,
                    "SELECT * FROM projects WHERE track_id=? ORDER BY created_at,project_id",
                    (track_id,),
                )
            ]
            plans = [
                parse_record(p)
                for p in rows(
                    conn,
                    "SELECT * FROM experiment_plans WHERE track_id=? ORDER BY created_at,plan_id",
                    (track_id,),
                )
            ]
            runs = [
                parse_record(r)
                for r in rows(
                    conn,
                    "SELECT * FROM pipeline_runs WHERE track_id=? ORDER BY created_at,run_id",
                    (track_id,),
                )
            ]
            receipts = self._receipts(conn, track_id)
            for plan in plans:
                original = next(
                    (
                        r
                        for r in receipts
                        if r["operation"] == "PROPOSE_PLAN" and r["object_id"] == plan["plan_id"]
                    ),
                    None,
                )
                plan["reviewed_manifest"] = original.get("manifest") if original else None
                plan["approval_phrase"] = f"APPROVE {plan['proposal_id']}"
                plan["grant_available"] = bool(
                    conn.execute(
                        """SELECT 1 FROM approval_grants WHERE proposal_id=?
                       AND proposal_type='experiment_plan' AND proposal_revision=?
                       AND consumed_at IS NULL""",
                        (plan["proposal_id"], plan["revision"]),
                    ).fetchone()
                )
                plan["run_id"] = next(
                    (r["run_id"] for r in runs if r["detail"].get("plan_id") == plan["plan_id"]),
                    None,
                )
            content = {"science": science, "projects": projects, "plans": plans, "runs": runs}
            # Approval ingress changes grant availability, not the reviewed content stamp.
            content["context_sha256"] = digest(
                {
                    **content,
                    "plans": [
                        {k: v for k, v in p.items() if k != "grant_available"} for p in plans
                    ],
                }
            )
            content["receipts"] = receipts
            content["python_executable"] = sys.executable
            content["project_types"] = {k.value: list(v) for k, v in REQUIRED_BLOCKS.items()}
            return content

    def manifest(self, track_id: str, payload: ManifestPreview) -> dict[str, Any]:
        with closing(self._read()) as conn:
            context = scientific_context(conn, track_id)
            self._method(context, payload.plan.method_node_id)
            return self._manifest(conn, track_id, payload)

    def _manifest(
        self, conn: sqlite3.Connection, track_id: str, payload: ManifestPreview
    ) -> dict[str, Any]:
        if payload.project_id:
            project = conn.execute(
                "SELECT * FROM projects WHERE project_id=? AND track_id=?",
                (payload.project_id, track_id),
            ).fetchone()
            if project is None:
                raise WorkspaceError(404, "Project does not belong to this Track")
            base = self.root / "projects" / project["slug"]
            owner_root = (self.root / "projects").resolve()
        else:
            base = self.artifacts_root / track_id / "experiments"
            owner_root = self.artifacts_root.resolve()
        base = base.resolve()
        cwd = (base / payload.plan.working_directory).resolve()
        if not base.is_relative_to(owner_root) or not cwd.is_relative_to(base):
            raise WorkspaceError(409, "Experiment workspace is outside its Track/Project")
        if not cwd.is_dir():
            raise WorkspaceError(409, "Create the selected experiment working directory first")

        def path(value: str) -> Path:
            selected = (cwd / value).resolve()
            if not selected.is_relative_to(cwd):
                raise WorkspaceError(
                    409, "Selected file must remain inside the experiment workspace"
                )
            return selected

        def file(value: str) -> dict[str, Any]:
            selected = path(value)
            if not selected.is_file():
                raise WorkspaceError(409, f"Selected input is unavailable: {value}")
            return {
                "path": str(selected),
                "relative_path": str(selected.relative_to(cwd)),
                "sha256": hashlib.sha256(selected.read_bytes()).hexdigest(),
                "size": selected.stat().st_size,
            }

        if not payload.plan.script_path:
            raise WorkspaceError(409, "Select the script whose contents will be reviewed")
        script = file(payload.plan.script_path)
        script["source_text"] = Path(script["path"]).read_text(encoding="utf-8", errors="replace")
        if payload.plan.script_sha256 != script["sha256"]:
            raise WorkspaceError(409, "Selected script digest changed")
        argv = payload.plan.argv
        if not any(str((cwd / arg).resolve()) == script["path"] for arg in argv[1:]):
            raise WorkspaceError(
                409, "The reviewed script must be an argument of the execution command"
            )
        if any(
            not key or "=" in key or "\0" in key or "\0" in value
            for key, value in payload.environment.items()
        ):
            raise WorkspaceError(409, "Selected environment contains an invalid name or value")
        executable = shutil.which(
            argv[0], path=payload.environment.get("PATH", os.environ.get("PATH"))
        )
        if not executable or not Path(executable).is_file():
            raise WorkspaceError(409, "Selected execution environment is unavailable")
        # Windows does not use the child env PATH to resolve a bare executable.
        # Freeze the executable actually reviewed, then invoke that exact path.
        argv = [str(Path(executable).resolve()), *argv[1:]]
        if len(payload.input_files) != len(set(payload.input_files)):
            raise WorkspaceError(409, "Select each input once")
        manifest = {
            "cwd": str(cwd),
            "script": script,
            "argv": argv,
            "timeout_seconds": payload.plan.timeout_seconds,
            "inputs": [file(value) for value in payload.input_files],
            "artifacts": [str(path(value)) for value in payload.artifact_paths],
            "metrics_path": str(path(payload.plan.metrics_json_path))
            if payload.plan.metrics_json_path
            else None,
            "executable": {
                "path": str(Path(executable).resolve()),
                "sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
            },
            "environment_overrides": payload.environment,
            "inherited_environment": "Runtime process environment; only overrides are stored",
        }
        manifest["manifest_sha256"] = digest(manifest)
        return manifest

    def files(
        self, track_id: str, project_id: str | None = None, working_directory: str = "."
    ) -> dict[str, Any]:
        with closing(self._read()) as conn:
            require(conn, "track", track_id)
            if project_id:
                p = conn.execute(
                    "SELECT slug FROM projects WHERE project_id=? AND track_id=?",
                    (project_id, track_id),
                ).fetchone()
                if p is None:
                    raise WorkspaceError(404, "Project does not belong to this Track")
                base = (self.root / "projects" / p[0]).resolve()
                owner = (self.root / "projects").resolve()
            else:
                base = (self.artifacts_root / track_id / "experiments").resolve()
                owner = self.artifacts_root.resolve()
            cwd = (base / working_directory).resolve()
            if not base.is_relative_to(owner) or not cwd.is_relative_to(base):
                raise WorkspaceError(409, "Working directory is outside its owner workspace")
            files = []
            if cwd.is_dir():
                for item in sorted(cwd.rglob("*")):
                    if item.is_file() and item.resolve().is_relative_to(cwd):
                        files.append(
                            {
                                "path": str(item.relative_to(cwd)),
                                "size": item.stat().st_size,
                                "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                            }
                        )
            return {"cwd": str(cwd), "exists": cwd.is_dir(), "files": files}

    def _original(
        self, conn: sqlite3.Connection, track_id: str, plan_id: str | None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        plan = conn.execute(
            "SELECT * FROM experiment_plans WHERE plan_id=? AND track_id=?", (plan_id, track_id)
        ).fetchone()
        if plan is None:
            raise WorkspaceError(404, "Plan does not belong to this Track")
        original = next(
            (
                r
                for r in self._receipts(conn, track_id)
                if r["operation"] == "PROPOSE_PLAN" and r["object_id"] == plan_id
            ),
            None,
        )
        if original is None:
            raise WorkspaceError(
                409, "Legacy plan has no reviewed input manifest; propose a new plan"
            )
        context = scientific_context(conn, track_id)
        if digest(self._method(context, plan["method_node_id"])) != digest(
            original["method_basis"]
        ):
            raise WorkspaceError(409, "Method or its recursive scientific sources changed")
        manifest = self._manifest(
            conn, track_id, ManifestPreview.model_validate(original["selection"])
        )
        if manifest != original["manifest"]:
            raise WorkspaceError(
                409, "Reviewed script, inputs, environment or execution workspace changed"
            )
        return dict(plan), original

    @staticmethod
    def _save(
        conn: sqlite3.Connection, action: ExperimentWorkspaceAction, result: dict[str, Any]
    ) -> None:
        conn.execute(
            """INSERT INTO research_workspace_actions
            (request_id,request_json,object_type,object_id,result_json,created_at)
            VALUES(?,?,?,?,?,?)""",
            (
                action.request_id,
                _json(action.model_dump(mode="json")),
                result["object_type"],
                result["object_id"],
                _json(result),
                _now(),
            ),
        )

    def act(self, action: ExperimentWorkspaceAction) -> dict[str, Any]:
        execution = None
        with transaction(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                "SELECT * FROM research_workspace_actions WHERE request_id=?", (action.request_id,)
            ).fetchone()
            if old:
                if old["request_json"] != _json(action.model_dump(mode="json")):
                    raise WorkspaceError(409, "Original request ID belongs to another action")
                result = json.loads(old["result_json"])
            else:
                if (
                    self.context(action.track_id)["context_sha256"]
                    != action.expected_context_sha256
                ):
                    raise WorkspaceError(409, "Experiment context changed; compare and refresh")
                context = scientific_context(conn, action.track_id)
                result = {
                    "request_id": action.request_id,
                    "operation": action.operation,
                    "track_id": action.track_id,
                    "object_type": "experiment_plan",
                }
                if isinstance(action, CreateProject):
                    p = action.project
                    if p.track_id != action.track_id:
                        raise WorkspaceError(404, "Project owner does not match this Track")
                    research_type = p.research_type or ResearchType(
                        context["track"]["research_type"]
                    )
                    validate_type_payload(research_type, p.type_payload)
                    pid = new_id("project")
                    conn.execute(
                        "INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            pid,
                            action.track_id,
                            p.slug,
                            p.title,
                            research_type.value,
                            _json(p.type_payload),
                            p.scope,
                            "ACTIVE",
                            1,
                            _now(),
                            _now(),
                        ),
                    )
                    result.update(object_type="experiment_project", object_id=pid)
                elif isinstance(action, ProposePlan):
                    selection = ManifestPreview.model_validate(
                        action.model_dump(
                            exclude={
                                "operation",
                                "request_id",
                                "track_id",
                                "expected_context_sha256",
                                "expected_manifest_sha256",
                                "confirmed",
                            }
                        )
                    )
                    manifest = self._manifest(conn, action.track_id, selection)
                    if manifest["manifest_sha256"] != action.expected_manifest_sha256:
                        raise WorkspaceError(409, "File manifest changed after preview")
                    basis = self._method(context, action.plan.method_node_id)
                    pid = self._propose_experiment_plan(
                        conn,
                        action.track_id,
                        action.plan.model_copy(update={"argv": manifest["argv"]}),
                        action.project_id,
                    )
                    result.update(
                        object_id=pid,
                        manifest=manifest,
                        method_basis=basis,
                        selection=selection.model_dump(mode="json"),
                    )
                elif isinstance(action, (ApplyPlan, StartPlan)):
                    plan, original = self._original(conn, action.track_id, action.plan_id)
                    if plan["revision"] != action.expected_revision:
                        raise WorkspaceError(409, "Reviewed plan revision changed")
                    result["object_id"] = action.plan_id
                    if isinstance(action, ApplyPlan):
                        self._approve_experiment_plan(
                            conn, action.plan_id, action.expected_revision
                        )
                    else:
                        if plan["status"] != "APPROVED":
                            raise PermissionError(
                                "Approve the reviewed plan through trusted user ingress first"
                            )
                        if any(
                            json.loads(r[0]).get("plan_id") == action.plan_id
                            for r in conn.execute(
                                "SELECT detail_json FROM pipeline_runs WHERE track_id=?",
                                (action.track_id,),
                            )
                        ):
                            raise WorkspaceError(
                                409, "Plan already has an execution; reconcile its original request"
                            )
                        run_id = new_id("run")
                        detail = {
                            "plan_id": action.plan_id,
                            "request_id": action.request_id,
                            "argv": original["manifest"]["argv"],
                            "cwd": original["manifest"]["cwd"],
                            "reviewed_manifest": original["manifest"],
                            "method_basis": original["method_basis"],
                        }
                        conn.execute(
                            "INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,?)",
                            (
                                run_id,
                                action.track_id,
                                plan["project_id"],
                                "experiment",
                                "RUNNING",
                                _json(detail),
                                _now(),
                                _now(),
                            ),
                        )
                        result.update(
                            object_type="experiment_execution",
                            object_id=run_id,
                            plan_id=action.plan_id,
                        )
                        execution = (plan, original, run_id)
                else:
                    run = conn.execute(
                        "SELECT * FROM pipeline_runs WHERE run_id=? AND track_id=?",
                        (action.run_id, action.track_id),
                    ).fetchone()
                    if run is None:
                        raise WorkspaceError(404, "Run does not belong to this Track")
                    if run["status"] != "COMPLETED":
                        raise WorkspaceError(
                            409, "Only a valid completed run can supply result Evidence"
                        )
                    detail = json.loads(run["detail_json"])
                    self._original(conn, action.track_id, detail.get("plan_id"))
                    for artifact in detail.get("artifacts", []):
                        path = Path(artifact["path"])
                        if not path.resolve().is_relative_to(Path(detail["cwd"]).resolve()) or (
                            not path.is_file()
                            or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]
                        ):
                            raise WorkspaceError(
                                409, "Recorded result artifact changed or is unavailable"
                            )
                    evidence = ExperimentRunner(self.db_path).convert_result_to_evidence(
                        ExperimentResult(
                            action.run_id,
                            detail["argv"],
                            detail["exit_code"],
                            detail["stdout"],
                            detail["stderr"],
                            detail["duration"],
                            detail["output_files"],
                            detail["metrics"],
                            run["status"],
                        ),
                        statement=action.statement,
                        metric_key=action.metric_key,
                    )
                    location = {
                        "pipeline_run_id": action.run_id,
                        "plan_id": detail["plan_id"],
                        "artifacts": detail["artifacts"],
                        "method_basis": detail["method_basis"],
                    }
                    eid = new_id("evidence")
                    conn.execute(
                        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            eid,
                            "TRACK",
                            context["track"]["field_id"],
                            action.track_id,
                            None,
                            None,
                            action.run_id,
                            evidence.statement,
                            evidence.excerpt,
                            _json(location),
                            evidence.relation.value,
                            evidence.confidence,
                            evidence.extractor_model,
                            evidence.prompt_version,
                            digest([evidence.statement, evidence.excerpt, location]),
                            _now(),
                        ),
                    )
                    result.update(
                        object_type="experiment_evidence", object_id=eid, run_id=action.run_id
                    )
                self._save(conn, action, result)
        if execution:
            plan, original, run_id = execution
            selection = original["selection"]
            try:
                # Recheck after reservation, before invoking the selected command.
                with closing(self._read()) as conn:
                    self._original(conn, action.track_id, plan["plan_id"])
                env = {**os.environ, **selection["environment"]}
                ExperimentRunner(self.db_path).run_script(
                    original["manifest"]["argv"],
                    track_id=action.track_id,
                    project_id=plan["project_id"],
                    cwd=original["manifest"]["cwd"],
                    timeout=plan["timeout_seconds"],
                    metrics_json_path=plan["metrics_json_path"],
                    input_files=selection["input_files"],
                    artifact_paths=selection["artifact_paths"],
                    env=env if selection["environment"] else None,
                    prepared_run_id=run_id,
                    recorded_environment=selection["environment"],
                )
                with closing(self._read()) as conn:
                    self._original(conn, action.track_id, plan["plan_id"])
            except (WorkspaceError, ValueError, OSError) as error:
                with transaction(self.db_path) as conn:
                    row = conn.execute(
                        "SELECT detail_json FROM pipeline_runs WHERE run_id=?", (run_id,)
                    ).fetchone()
                    detail = json.loads(row[0])
                    detail["validation_error"] = str(error)
                    conn.execute(
                        "UPDATE pipeline_runs SET status='SOURCE_INVALIDATED',detail_json=?,updated_at=? WHERE run_id=?",
                        (_json(detail), _now(), run_id),
                    )
        if result["object_type"] == "experiment_execution":
            with closing(self._read()) as conn:
                result = {
                    **result,
                    "run": parse_record(
                        dict(
                            conn.execute(
                                "SELECT * FROM pipeline_runs WHERE run_id=? AND track_id=?",
                                (result["object_id"], action.track_id),
                            ).fetchone()
                        )
                    ),
                }
        return result
