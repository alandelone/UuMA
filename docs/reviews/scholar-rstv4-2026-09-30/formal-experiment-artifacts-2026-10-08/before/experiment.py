from __future__ import annotations

import json
import subprocess
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
    ) -> ExperimentResult:
        run_id = new_id("run")
        start_time = time.time()
        cwd_path = Path(cwd) if cwd else self.db_path.parent
        cwd_path.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))

        with transaction(self.db_path) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)")}
            common = (
                run_id, f"experiment: {json.dumps(command, ensure_ascii=False)}", "RUNNING",
                json.dumps({"argv": command, "cwd": str(cwd_path)}), timestamp, timestamp,
            )
            if "project_id" in columns:
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
            stdout = (err.stdout or "") if isinstance(err.stdout, str) else ""
            stderr = (err.stderr or "") + f"\nTimed out after {timeout} seconds"
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
        if metrics_json_path:
            mp = Path(metrics_json_path)
            if not mp.is_absolute():
                mp = cwd_path / mp
            if mp.exists():
                try:
                    with mp.open("r", encoding="utf-8") as f:
                        metrics = json.load(f)
                    output_files.append(str(mp))
                except (OSError, TypeError, ValueError) as err:
                    stderr += f"\nFailed to parse metrics file: {err}"

        end_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        detail = {
            "argv": command,
            "exit_code": exit_code,
            "duration": duration,
            "metrics": metrics,
            "stdout_preview": stdout[:1000],
            "stderr_preview": stderr[:1000],
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
