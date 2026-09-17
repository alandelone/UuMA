from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .kag_lifecycle import runtime_lock
from .knowledge_models import (
    AnswerCitation,
    ClaimStatus,
    KnowledgeAnswer,
    ReasoningMode,
    ReasoningStep,
    ReasoningTraceRecord,
    SatisfactionLevel,
)
from .knowledge_service import KnowledgeService


class KagUnavailableError(RuntimeError):
    """Raised when the disposable OpenSPG/KAG projection cannot serve a request."""


class KagBackend(Protocol):
    def health(self) -> dict[str, Any]: ...

    def recover(self) -> dict[str, Any]: ...

    def apply(self, job: dict[str, Any]) -> dict[str, Any]: ...

    def retrieve(self, query: str, mode: ReasoningMode) -> dict[str, Any]: ...

    def extract(self, chunks: list[dict[str, Any]]) -> dict[str, Any]: ...


class JsonHttpClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds if timeout_seconds is None else timeout_seconds,
            ) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise KagUnavailableError(str(exc)) from exc
        parsed = json.loads(body) if body else {}
        if not isinstance(parsed, dict):
            raise KagUnavailableError("KAG bridge returned a non-object response.")
        return parsed


@dataclass
class KagRuntimeManager:
    bridge_url: str
    compose_file: Path | None = None
    bridge_python: Path | None = None
    kag_config: Path | None = None
    secrets_file: Path | None = None
    auto_recover: bool = True
    recovery_timeout_seconds: int = 120

    def _ensure_docker_engine(self) -> None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        probe = ["docker", "info", "--format", "{{.ServerVersion}}"]
        try:
            result = subprocess.run(
                probe,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=creation_flags,
            )
        except OSError as exc:
            raise KagUnavailableError(f"Docker CLI is unavailable: {exc}") from exc
        except subprocess.TimeoutExpired:
            result = None
        if result is not None and result.returncode == 0:
            return
        if os.name != "nt":
            detail = "Docker engine probe timed out." if result is None else (
                result.stderr or result.stdout
            ).strip()
            raise KagUnavailableError(detail)
        program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        desktop = program_files / "Docker" / "Docker" / "Docker Desktop.exe"
        if not desktop.is_file():
            raise KagUnavailableError("Docker Desktop is not installed at its standard path.")
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen(
                [str(desktop)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags | detached | new_group,
            )
        except OSError as exc:
            raise KagUnavailableError(f"Docker Desktop could not be started: {exc}") from exc
        deadline = time.monotonic() + min(60, self.recovery_timeout_seconds)
        while time.monotonic() < deadline:
            try:
                result = subprocess.run(
                    probe,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                    creationflags=creation_flags,
                )
            except (OSError, subprocess.TimeoutExpired):
                time.sleep(2)
                continue
            if result.returncode == 0:
                return
            time.sleep(2)
        raise KagUnavailableError("Docker Desktop did not become ready within 60 seconds.")

    def recover(self) -> dict[str, Any]:
        if not self.auto_recover:
            raise KagUnavailableError("KAG automatic recovery is disabled.")
        if self.compose_file is None:
            raise KagUnavailableError("UUMA_KAG_COMPOSE_FILE is not configured.")
        compose_file = self.compose_file.expanduser().resolve()
        if not compose_file.is_file():
            raise KagUnavailableError(f"KAG compose file does not exist: {compose_file}")
        try:
            with runtime_lock(compose_file):
                try:
                    health = JsonHttpClient(self.bridge_url, timeout_seconds=3).request("/health")
                    if health.get("ready") is True:
                        return health
                except KagUnavailableError:
                    pass
                return self._recover_locked(compose_file)
        except TimeoutError as exc:
            raise KagUnavailableError(str(exc)) from exc

    def _recover_locked(self, compose_file: Path) -> dict[str, Any]:
        command = [
            "docker",
            "compose",
            "-p",
            "uuma-wisdom-kag",
            "-f",
            str(compose_file),
            "up",
            "-d",
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._ensure_docker_engine()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.recovery_timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise KagUnavailableError(f"KAG recovery command failed: {exc}") from exc
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).strip()
            raise KagUnavailableError(f"KAG recovery failed: {message[-1000:]}")
        self._ensure_bridge_process()
        client = JsonHttpClient(self.bridge_url, timeout_seconds=3)
        deadline = time.monotonic() + self.recovery_timeout_seconds
        last_error = "health check did not run"
        while time.monotonic() < deadline:
            try:
                health = client.request("/health")
                if health.get("ready") is True:
                    return health
                last_error = str(health)
            except KagUnavailableError as exc:
                last_error = str(exc)
            time.sleep(2)
        raise KagUnavailableError(f"KAG did not become ready: {last_error}")

    def _ensure_bridge_process(self) -> None:
        try:
            health = JsonHttpClient(self.bridge_url, timeout_seconds=3).request("/health")
            if health.get("ready") is True:
                return
        except KagUnavailableError:
            pass
        if self.kag_config is None:
            return
        config = self.kag_config.expanduser().resolve()
        if not config.is_file():
            raise KagUnavailableError(f"UUMA_KAG_CONFIG does not exist: {config}")
        python = (self.bridge_python or Path(sys.executable)).expanduser().resolve()
        if not python.is_file():
            raise KagUnavailableError(f"UUMA_KAG_PYTHON does not exist: {python}")
        environment = self._bridge_environment(config)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen(
                [str(python), "-m", "uuma.kag_bridge"],
                cwd=str(config.parent),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except OSError as exc:
            raise KagUnavailableError(f"KAG bridge could not be started: {exc}") from exc

    def _bridge_environment(self, config: Path) -> dict[str, str]:
        environment = dict(os.environ)
        environment["UUMA_KAG_CONFIG"] = str(config)
        if environment.get("OPENAI_API_KEY"):
            return environment
        if environment.get("OPENROUTER_API_KEY"):
            environment["OPENAI_API_KEY"] = environment["OPENROUTER_API_KEY"]
            return environment
        if self.secrets_file is None:
            return environment
        secrets_file = self.secrets_file.expanduser().resolve()
        try:
            lines = secrets_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise KagUnavailableError(f"KAG secrets file is unavailable: {secrets_file}") from exc
        values: dict[str, str] = {}
        for line in lines:
            name, separator, value = line.strip().partition("=")
            if separator and name in {"OPENAI_API_KEY", "OPENROUTER_API_KEY"}:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                values[name] = value
        key = values.get("OPENAI_API_KEY") or values.get("OPENROUTER_API_KEY")
        if not key:
            raise KagUnavailableError(f"KAG API key is missing from: {secrets_file}")
        environment["OPENAI_API_KEY"] = key
        return environment


class OpenSpgKagBackend:
    """Semantic HTTP boundary around an OpenSPG KAG v0.8 projection runtime."""

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:8891",
        *,
        runtime: KagRuntimeManager | None = None,
    ) -> None:
        self.client = JsonHttpClient(bridge_url)
        self.runtime = runtime or KagRuntimeManager(bridge_url=bridge_url)

    @classmethod
    def from_env(cls) -> OpenSpgKagBackend:
        bridge_url = os.environ.get("UUMA_KAG_BRIDGE_URL", "http://127.0.0.1:8891")
        compose_value = os.environ.get("UUMA_KAG_COMPOSE_FILE")
        bridge_python = os.environ.get("UUMA_KAG_PYTHON")
        kag_config = os.environ.get("UUMA_KAG_CONFIG")
        secrets_file = os.environ.get("UUMA_KAG_SECRETS_FILE")
        auto_recover = os.environ.get("UUMA_KAG_AUTO_RECOVER", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        runtime = KagRuntimeManager(
            bridge_url=bridge_url,
            compose_file=Path(compose_value) if compose_value else None,
            bridge_python=Path(bridge_python) if bridge_python else None,
            kag_config=Path(kag_config) if kag_config else None,
            secrets_file=Path(secrets_file) if secrets_file else None,
            auto_recover=auto_recover,
        )
        return cls(bridge_url, runtime=runtime)

    def health(self) -> dict[str, Any]:
        return self.client.request("/health", timeout_seconds=5)

    def recover(self) -> dict[str, Any]:
        return self.runtime.recover()

    def apply(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.client.request(
            "/project", method="POST", payload=job, timeout_seconds=300
        )

    def retrieve(self, query: str, mode: ReasoningMode) -> dict[str, Any]:
        return self.client.request(
            "/retrieve",
            method="POST",
            payload={"query": query, "mode": mode.value},
            timeout_seconds=90 if mode == ReasoningMode.SIMPLE else 600,
        )

    def extract(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        return self.client.request(
            "/extract", method="POST", payload={"chunks": chunks}, timeout_seconds=600
        )


class KagProjectionWorker:
    def __init__(
        self,
        service: KnowledgeService,
        backend: KagBackend,
        *,
        max_attempts: int = 5,
        running_lease_seconds: float = 900,
    ) -> None:
        self.service = service
        self.backend = backend
        self.max_attempts = max_attempts
        self.running_lease_seconds = running_lease_seconds

    def sync(self, *, limit: int = 100, recover: bool = True) -> dict[str, Any]:
        jobs = self.service.store.pending_projection_jobs(
            limit, running_lease_seconds=self.running_lease_seconds
        )
        eligible = [job for job in jobs if int(job["attempts"]) < self.max_attempts]
        if not eligible:
            return {"processed": 0, "applied": 0, "failed": 0, **self.service.projection_health()}
        try:
            health = self.backend.health()
            if health.get("ready") is not True:
                raise KagUnavailableError(str(health))
        except KagUnavailableError:
            if not recover:
                raise
            self.backend.recover()
        applied = 0
        failed = 0
        for job in eligible:
            job_id = job["projection_job_id"]
            self.service.store.mark_projection_job(job_id, status="RUNNING")
            try:
                result = self.backend.apply(job)
                if result.get("applied") is False:
                    raise KagUnavailableError(result.get("error", "projection rejected"))
                self.service.store.mark_projection_job(job_id, status="APPLIED")
                applied += 1
            except Exception as exc:  # noqa: BLE001 -- Persist each backend failure for retry/audit.
                self.service.store.mark_projection_job(
                    job_id, status="FAILED", error=str(exc)[:8000]
                )
                failed += 1
                if isinstance(exc, KagUnavailableError):
                    break
        return {
            "processed": applied + failed,
            "applied": applied,
            "failed": failed,
            **self.service.projection_health(),
        }


class KnowledgeReasoner:
    DEEP_MARKERS: ClassVar[set[str]] = {
        "why", "how", "compare", "difference", "cause", "mechanism", "conflict",
        "trend", "calculate", "derive", "explain", "为什么", "如何", "比较", "区别",
        "原因", "机制", "冲突", "趋势", "计算", "推导", "解释",
    }

    def __init__(self, service: KnowledgeService, backend: KagBackend) -> None:
        self.service = service
        self.backend = backend

    def answer(
        self,
        question: str,
        *,
        requested_mode: ReasoningMode = ReasoningMode.AUTO,
        actor_id: str = "wisdom-oldman",
        recover: bool = True,
    ) -> dict[str, Any]:
        selected = self._select_mode(question, requested_mode)
        health = self.service.projection_health()
        degraded = False
        try:
            backend_health = self.backend.health()
            if backend_health.get("ready") is not True:
                raise KagUnavailableError(str(backend_health))
            health = self._sync_projection(health)
            response = self.backend.retrieve(question, selected)
            answer = self._normalize_kag_answer(response, question, selected, health)
            steps = self._normalize_steps(response, question)
        except KagUnavailableError:
            if recover:
                try:
                    self.backend.recover()
                    health = self._sync_projection(self.service.projection_health())
                    response = self.backend.retrieve(question, selected)
                    answer = self._normalize_kag_answer(response, question, selected, health)
                    steps = self._normalize_steps(response, question)
                except KagUnavailableError:
                    degraded = True
                    answer, steps = self._degraded_answer(question, selected, health)
            else:
                degraded = True
                answer, steps = self._degraded_answer(question, selected, health)
        trace = ReasoningTraceRecord(
            question=question,
            requested_mode=requested_mode,
            selected_mode=selected,
            steps=steps,
            projection_watermark=health["watermark"],
            degraded=degraded,
        )
        self.service.record_reasoning_trace(trace, actor_id=actor_id)
        answer = answer.model_copy(update={"reasoning_trace_id": trace.reasoning_trace_id})
        return answer.model_dump(mode="json")

    def _sync_projection(self, health: dict[str, Any]) -> dict[str, Any]:
        if not health["lag"]:
            return health
        worker = KagProjectionWorker(self.service, self.backend)
        while health["lag"]:
            result = worker.sync(limit=1000, recover=False)
            health = self.service.projection_health()
            if result["processed"] == 0 or result["failed"]:
                break
        if health["lag"]:
            raise KagUnavailableError("KAG projection is behind the canonical knowledge store.")
        return health

    def _select_mode(self, question: str, requested: ReasoningMode) -> ReasoningMode:
        if requested != ReasoningMode.AUTO:
            return requested
        lowered = question.casefold()
        if any(marker in lowered for marker in self.DEEP_MARKERS) or len(question) > 180:
            return ReasoningMode.DEEP
        return ReasoningMode.SIMPLE

    @staticmethod
    def _normalize_steps(response: dict[str, Any], question: str) -> list[ReasoningStep]:
        raw_steps = response.get("steps")
        if not isinstance(raw_steps, list):
            return [
                ReasoningStep(
                    step=1,
                    operator="SEMANTIC",
                    query=question,
                    result_refs=[str(item) for item in response.get("result_refs", [])],
                    summary="OpenSPG KAG hybrid retrieval and reasoning.",
                )
            ]
        steps: list[ReasoningStep] = []
        for index, item in enumerate(raw_steps, 1):
            if isinstance(item, dict):
                steps.append(
                    ReasoningStep.model_validate(
                        {
                            "step": item.get("step", index),
                            "operator": item.get("operator", "SEMANTIC"),
                            "query": item.get("query", question),
                            "result_refs": item.get("result_refs", []),
                            "summary": item.get("summary"),
                        }
                    )
                )
        return steps

    def _normalize_kag_answer(
        self,
        response: dict[str, Any],
        question: str,
        selected: ReasoningMode,
        health: dict[str, Any],
    ) -> KnowledgeAnswer:
        refs = response.get("result_refs", [])
        citations = [AnswerCitation.model_validate(item) for item in response.get("citations", [])]
        if not citations:
            citations = self._citations_for_refs(refs)
        canonical = self._canonical_context_for_refs(refs)
        return KnowledgeAnswer(
            answer=str(response.get("answer") or response.get("summary") or f"No answer for: {question}"),
            citations=citations,
            conditions=list(
                dict.fromkeys(
                    [str(item) for item in response.get("conditions", [])]
                    + canonical["conditions"]
                )
            ),
            conflicts=list(
                dict.fromkeys(
                    [str(item) for item in response.get("conflicts", [])]
                    + canonical["conflicts"]
                )
            ),
            satisfaction_level=SatisfactionLevel(
                response.get("satisfaction_level", SatisfactionLevel.PROVISIONAL.value)
            ),
            satisfaction_rationale=str(
                response.get("satisfaction_rationale")
                or "Returned by the OpenSPG KAG projection; canonical evidence remains in wisdom.db."
            ),
            remaining_gap_ids=list(
                dict.fromkeys(
                    [str(item) for item in response.get("remaining_gap_ids", [])]
                    + canonical["remaining_gap_ids"]
                )
            ),
            reasoning_trace_id="pending",
            selected_mode=selected,
            runtime_status="KAG",
            projection_watermark=health["watermark"],
        )

    def _citations_for_refs(self, refs: list[Any]) -> list[AnswerCitation]:
        citations: list[AnswerCitation] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for raw_ref in refs:
            ref = str(raw_ref)
            try:
                details = self.service.get(ref)
            except KeyError:
                continue
            record = details["record"]
            candidates: list[AnswerCitation] = []
            if details["kind"] == "claim":
                links = {
                    link["evidence_id"]: link for link in details.get("evidence_links", [])
                }
                for evidence in details.get("evidence", []):
                    source = self.service.get(evidence["evidence_id"])["source"]
                    link = links.get(evidence["evidence_id"], {})
                    candidates.append(
                        AnswerCitation(
                            source_id=source["source_id"],
                            evidence_id=evidence["evidence_id"],
                            claim_id=record["claim_id"],
                            locator=source["locator"],
                            location=evidence.get("location"),
                            stance=link.get("stance"),
                            rationale=link.get("rationale"),
                        )
                    )
            elif details["kind"] == "evidence":
                source = details["source"]
                candidates.append(
                    AnswerCitation(
                        source_id=source["source_id"],
                        evidence_id=record["evidence_id"],
                        locator=source["locator"],
                        location=record.get("location"),
                    )
                )
            elif details["kind"] == "chunk":
                source = details["source"]
                candidates.append(
                    AnswerCitation(
                        source_id=source["source_id"],
                        document_id=record["document_id"],
                        chunk_id=record["chunk_id"],
                        locator=source["locator"],
                        location=record.get("location"),
                    )
                )
            for citation in candidates:
                key = (citation.source_id, citation.evidence_id, citation.chunk_id)
                if key not in seen:
                    citations.append(citation)
                    seen.add(key)
        return citations

    def _canonical_context_for_refs(self, refs: list[Any]) -> dict[str, list[str]]:
        claim_ids: set[str] = set()
        for raw_ref in refs:
            try:
                details = self.service.get(str(raw_ref))
            except KeyError:
                continue
            if details["kind"] == "claim":
                claim_ids.add(details["record"]["claim_id"])
            elif details["kind"] == "chunk":
                claim_ids.update(
                    link["target_id"]
                    for link in details.get("knowledge_links", [])
                    if link["target_kind"] == "claim"
                )
        return self._canonical_context_for_claims(claim_ids)

    def _canonical_context_for_claims(self, claim_ids: set[str]) -> dict[str, list[str]]:
        conditions: list[str] = []
        for claim_id in sorted(claim_ids):
            claim = self.service.get(claim_id)["record"]
            qualifiers = claim.get("qualifiers") or {}
            if qualifiers:
                rendered = ", ".join(
                    f"{key}={json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}"
                    for key, value in sorted(qualifiers.items())
                )
                conditions.append(f"{claim_id}: {rendered}")

        conflicts = []
        for conflict in self.service.list_records("conflict", limit=500)["records"]:
            if conflict.get("status") == "OPEN" and claim_ids.intersection(conflict["claim_ids"]):
                conflicts.append(f"{conflict['conflict_id']}: {conflict['description']}")

        gaps = []
        for gap in self.service.list_records("gap", limit=500)["records"]:
            if gap.get("status") in {"OPEN", "IN_PROGRESS"} and claim_ids.intersection(
                gap.get("related_claim_ids", [])
            ):
                gaps.append(gap["gap_id"])
        return {
            "conditions": conditions,
            "conflicts": conflicts,
            "remaining_gap_ids": gaps,
        }

    def _degraded_answer(
        self, question: str, selected: ReasoningMode, health: dict[str, Any]
    ) -> tuple[KnowledgeAnswer, list[ReasoningStep]]:
        results = self.service.search(question, 20)["results"]
        statements: list[str] = []
        citations: list[AnswerCitation] = []
        refs: list[str] = []
        accepted_claim_ids: set[str] = set()
        accepted = 0
        for result in results:
            record = result["record"]
            refs.append(record.get(f"{result['kind']}_id", ""))
            if result["kind"] == "claim":
                if record.get("status") != ClaimStatus.ACCEPTED.value:
                    continue
                accepted += 1
                accepted_claim_ids.add(record["claim_id"])
                statements.append(record["statement"])
                details = self.service.get(record["claim_id"])
                links = {
                    link["evidence_id"]: link for link in details.get("evidence_links", [])
                }
                for evidence in details.get("evidence", []):
                    source = self.service.get(evidence["evidence_id"])["source"]
                    link = links.get(evidence["evidence_id"], {})
                    citations.append(
                        AnswerCitation(
                            source_id=source["source_id"],
                            evidence_id=evidence["evidence_id"],
                            claim_id=record["claim_id"],
                            locator=source["locator"],
                            location=evidence.get("location"),
                            stance=link.get("stance"),
                            rationale=link.get("rationale"),
                        )
                    )
            elif result["kind"] == "evidence" and len(statements) < 5:
                source = self.service.get(record["evidence_id"])["source"]
                statements.append(record["excerpt"])
                citations.append(
                    AnswerCitation(
                        source_id=source["source_id"],
                        evidence_id=record["evidence_id"],
                        locator=source["locator"],
                        location=record.get("location"),
                    )
                )
            elif result["kind"] == "chunk" and len(statements) < 5:
                details = self.service.get(record["chunk_id"])
                source = details["source"]
                statements.append(record["text"])
                citations.append(
                    AnswerCitation(
                        source_id=source["source_id"],
                        document_id=record["document_id"],
                        chunk_id=record["chunk_id"],
                        locator=source["locator"],
                        location=record.get("location"),
                    )
                )
            if len(statements) >= 5:
                break
        if statements:
            body = "\n".join(f"- {statement}" for statement in statements)
            rationale = (
                "OpenSPG KAG was unavailable. This is an extractive answer from wisdom.db "
                f"with {accepted} accepted matching claim(s); graph/vector reasoning was not used."
            )
            level = SatisfactionLevel.PROVISIONAL
        else:
            body = "No relevant accepted knowledge was retrieved from the canonical store."
            rationale = (
                "OpenSPG KAG was unavailable and the canonical text fallback found no sufficient evidence."
            )
            level = SatisfactionLevel.INSUFFICIENT
        citations_by_key: dict[tuple[str, str | None, str | None], AnswerCitation] = {}
        for citation in citations:
            key = (citation.source_id, citation.evidence_id, citation.chunk_id)
            existing = citations_by_key.get(key)
            if existing is None or (existing.stance is None and citation.stance is not None):
                citations_by_key[key] = citation
        citations = list(citations_by_key.values())
        canonical = self._canonical_context_for_claims(accepted_claim_ids)
        answer = KnowledgeAnswer(
            answer=body,
            citations=citations,
            conditions=[
                "DEGRADED_KAG: text retrieval only; no graph/vector/logic-form reasoning.",
                *canonical["conditions"],
            ],
            conflicts=canonical["conflicts"],
            satisfaction_level=level,
            satisfaction_rationale=rationale,
            remaining_gap_ids=canonical["remaining_gap_ids"],
            reasoning_trace_id="pending",
            selected_mode=selected,
            runtime_status="DEGRADED_KAG",
            projection_watermark=health["watermark"],
        )
        steps = [
            ReasoningStep(
                step=1,
                operator="TEXT",
                query=question,
                result_refs=[ref for ref in refs if ref],
                summary="Canonical FTS fallback because the KAG projection was unavailable.",
            )
        ]
        return answer, steps
