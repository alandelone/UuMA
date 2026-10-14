from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import transaction
from .models import EvidenceInput, EvidenceRelation, new_id


@dataclass
class ExperimentResult:
    run_id: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    output_files: list[str]
    metrics: dict[str, Any]
    execution_status: str | None = None


class ExperimentRunner:
    """Manages Phase 2: Experiment execution and evidence extraction."""

    def __init__(self, project_db_path: Path) -> None:
        self.db_path = project_db_path

    def run_script(
        self,
        command: list[str],
        *,
        track_id: str | None = None,
        project_id: str | None = None,
        cwd: str | Path | None = None,
        timeout: int = 600,
        env: dict[str, str] | None = None,
        metrics_json_path: str | Path | None = None,
        input_files: list[str] | None = None,
        artifact_paths: list[str] | None = None,
        prepared_run_id: str | None = None,
        recorded_environment: dict[str, str] | None = None,
    ) -> ExperimentResult:
        run_id = prepared_run_id or new_id("run")
        start_time = time.time()
        cwd_path = Path(cwd) if cwd else self.db_path.parent
        cwd_path.mkdir(parents=True, exist_ok=True)
        cwd_path = cwd_path.resolve()

        def owned_file(value):
            path = (cwd_path / value).resolve()
            if not path.is_relative_to(cwd_path):
                raise ValueError("Experiment input/artifact must remain inside its workspace")
            return path

        def manifest(path):
            if not path.resolve().is_relative_to(cwd_path):
                raise ValueError("Experiment artifact changed to a location outside its workspace")
            return {
                "path": str(path),
                "relative_path": str(path.relative_to(cwd_path)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
            }

        inputs = [manifest(owned_file(value)) for value in input_files or []]
        outputs = [owned_file(value) for value in artifact_paths or []]
        metrics_path = owned_file(str(metrics_json_path)) if metrics_json_path else None
        if metrics_path and metrics_path not in outputs:
            outputs.append(metrics_path)
        previous_artifacts = {
            str(path): manifest(path) if path.is_file() else None for path in outputs
        }
        runtime_env = dict(os.environ) if env is None else dict(env)
        executable = shutil.which(command[0], path=runtime_env.get("PATH")) if command else None
        environment = {
            "observer_python_version": sys.version,
            "observer_executable": sys.executable,
            "observer_platform": platform.platform(),
            "executable": executable,
            "explicit_environment": (
                dict(recorded_environment) if recorded_environment is not None
                else dict(env) if env is not None else None
            ),
            "path": runtime_env.get("PATH"),
            "pythonpath": runtime_env.get("PYTHONPATH"),
        }
        context = {
            "argv": command,
            "cwd": str(cwd_path),
            "timeout_seconds": timeout,
            "inputs": inputs,
            "environment": environment,
            "declared_artifacts": [str(path) for path in outputs],
            "previous_artifacts": previous_artifacts,
        }

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))

        with transaction(self.db_path) as conn:
            if prepared_run_id:
                row=conn.execute('SELECT * FROM pipeline_runs WHERE run_id=?',(prepared_run_id,)).fetchone()
                if (row is None or row['status']!='RUNNING' or row['track_id']!=track_id or row['project_id']!=project_id):
                    raise ValueError('Prepared execution does not match its running Track/Project request')
                original=json.loads(row['detail_json'])
                if original['argv']!=command or original['cwd']!=str(cwd_path):
                    raise ValueError('Prepared execution command or workspace changed')
                context={**original,**context}
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)")}
            common = (
                run_id,
                f"experiment: {json.dumps(command, ensure_ascii=False)}",
                "RUNNING",
                json.dumps(context),
                timestamp,
                timestamp,
            )
            if prepared_run_id:
                conn.execute('UPDATE pipeline_runs SET detail_json=? WHERE run_id=?',(json.dumps(context),run_id))
            elif "project_id" in columns:
                if not track_id:
                    raise ValueError("track_id is required for the global experiment store")
                conn.execute(
                    """INSERT INTO pipeline_runs(
                       run_id,track_id,project_id,operation,status,detail_json,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (run_id, track_id, project_id, *common[1:]),
                )
            else:
                conn.execute(
                    """INSERT INTO pipeline_runs(
                       run_id,operation,status,detail_json,created_at,updated_at) VALUES(?,?,?,?,?,?)""",
                    common,
                )

        try:
            process = subprocess.run(
                command,
                shell=False,
                cwd=str(cwd_path),
                timeout=timeout,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            duration = time.time() - start_time
            stdout = process.stdout or ""
            stderr = process.stderr or ""
            exit_code = process.returncode
            status = "COMPLETED" if exit_code == 0 else "FAILED"
        except subprocess.TimeoutExpired as err:
            duration = time.time() - start_time
            stdout = (
                err.stdout.decode("utf-8", errors="replace")
                if isinstance(err.stdout, bytes)
                else (err.stdout or "")
            )
            stderr = (
                err.stderr.decode("utf-8", errors="replace")
                if isinstance(err.stderr, bytes)
                else (err.stderr or "")
            ) + f"\nTimed out after {timeout} seconds"
            exit_code = -1
            status = "TIMEOUT"
        except OSError as err:
            duration = time.time() - start_time
            stdout = ""
            stderr = f"Execution error: {err}"
            exit_code = -2
            status = "ERROR"

        metrics: dict[str, Any] = {}
        output_files: list[str] = []
        if metrics_path:
            mp = metrics_path
            if mp.is_file():
                try:
                    if not mp.resolve().is_relative_to(cwd_path):
                        raise ValueError("Metrics file is outside the experiment workspace")
                    with mp.open("r", encoding="utf-8") as f:
                        metrics = json.load(f)
                    if not isinstance(metrics, dict):
                        raise TypeError("Experiment metrics must be a JSON object")
                    if (
                        previous_artifacts[str(mp)]
                        and previous_artifacts[str(mp)]["sha256"]
                        == hashlib.sha256(mp.read_bytes()).hexdigest()
                        and previous_artifacts[str(mp)]["mtime_ns"] == mp.stat().st_mtime_ns
                    ):
                        raise ValueError("Declared metrics did not change during this execution")
                    output_files.append(str(mp))
                except (OSError, TypeError, ValueError) as err:
                    metrics = {}
                    stderr += f"\nFailed to parse metrics file: {err}"
                    if status == "COMPLETED":
                        status = "METRICS_ERROR"
            elif status == "COMPLETED":
                status = "METRICS_ERROR"
                stderr += "\nDeclared metrics file was not produced"
        artifacts = []
        for path in outputs:
            if path.is_file():
                try:
                    entry = manifest(path)
                except (OSError, ValueError) as error:
                    stderr += "\nArtifact could not be recorded: " + str(error)
                    if status == "COMPLETED":
                        status = "ARTIFACT_ERROR"
                    continue
                entry["changed"] = (
                    previous_artifacts[str(path)] is None
                    or entry["sha256"] != previous_artifacts[str(path)]["sha256"]
                    or entry["mtime_ns"] != previous_artifacts[str(path)]["mtime_ns"]
                )
                artifacts.append(entry)
                if str(path) not in output_files:
                    output_files.append(str(path))
            elif status == "COMPLETED":
                status = "ARTIFACT_ERROR"
                stderr += "\nDeclared artifact was not produced: " + str(path.relative_to(cwd_path))
        changed_inputs = []
        for entry in inputs:
            path = Path(entry["path"])
            if (
                not path.resolve().is_relative_to(cwd_path)
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
            ):
                changed_inputs.append(entry["relative_path"])
        if changed_inputs and status == "COMPLETED":
            status = "INPUT_CHANGED"

        end_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        detail = {
            **context,
            "argv": command,
            "exit_code": exit_code,
            "duration": duration,
            "metrics": metrics,
            "stdout_preview": stdout[:1000],
            "stderr_preview": stderr[:1000],
            "stdout": stdout,
            "stderr": stderr,
            "output_files": output_files,
            "artifacts": artifacts,
            "changed_inputs": changed_inputs,
            "execution_status": status,
        }

        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, detail_json = ?, updated_at = ? WHERE run_id = ?",
                (status, json.dumps(detail), end_timestamp, run_id),
            )

        return ExperimentResult(
            run_id=run_id,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            output_files=output_files,
            metrics=metrics,
            execution_status=status,
        )

    def convert_result_to_evidence(
        self,
        result: ExperimentResult,
        *,
        statement: str,
        metric_key: str | None = None,
        confidence: float = 0.95,
        extractor_model: str = "rstv4-experiment-runner",
    ) -> EvidenceInput:
        if result.execution_status is not None and result.execution_status != "COMPLETED":
            raise ValueError(
                "An incomplete or invalid experiment execution cannot supply result Evidence"
            )
        if metric_key and metric_key not in result.metrics:
            raise ValueError("The requested metric was not recorded by this execution")
        excerpt = (
            f"Command argv: `{json.dumps(result.command, ensure_ascii=False)}` exited with code "
            f"{result.exit_code} in {result.duration_seconds:.2f}s."
        )
        if metric_key and metric_key in result.metrics:
            val = result.metrics[metric_key]
            excerpt += f" Metric '{metric_key}': {val}"
        elif result.metrics:
            excerpt += f" Metrics: {json.dumps(result.metrics)}"

        return EvidenceInput(
            paper_id=f"run:{result.run_id}",
            statement=statement,
            excerpt=excerpt,
            location=f"pipeline_runs.run_id={result.run_id}",
            relation=EvidenceRelation.SUPPORTS
            if result.exit_code == 0
            else EvidenceRelation.CONTRADICTS,
            confidence=confidence if result.exit_code == 0 else 0.5,
            extractor_model=extractor_model,
            prompt_version="experiment_v1",
        )
