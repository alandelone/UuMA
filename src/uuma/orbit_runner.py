from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Self

from ruamel.yaml import YAML

from .kag_adapter import (
    KagProjectionWorker,
    KagUnavailableError,
    KnowledgeReasoner,
    OpenSpgKagBackend,
)
from .knowledge_construction import KnowledgeConstructor
from .knowledge_ingest import KnowledgeIngestor
from .knowledge_models import ReasoningMode, SatisfactionLevel
from .knowledge_runtime import ensure_knowledge_graph
from .knowledge_service import KnowledgeService
from .orbit_discovery import (
    CanonicalCitationProvider,
    DiscoveryArtifact,
    DiscoveryProvider,
    artifact_identity,
    configured_providers,
    urls_in_question,
)
from .question_orbit import QuestionOrbitService
from .safe_web import RetryAfterError, SafeWebFetcher
from .settings import Settings
from .wisdom_topics import TopicKnowledgeService, ensure_view_token

LOGGER = logging.getLogger(__name__)


class _RunnerInstanceLock:
    """Hold one process-wide runner lock for the configured UuMA data directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("Another Question Orbit runner process is already active.") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid()}).encode("utf-8"))
        handle.flush()
        self._handle = handle
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def load_profile_environment(profile_home: Path) -> None:
    """Load the deployed Knowledge MCP environment without printing or copying secrets."""
    config_path = profile_home / "config.yaml"
    if config_path.is_file():
        payload = YAML(typ="safe").load(config_path.read_text(encoding="utf-8")) or {}
        server = (payload.get("mcp_servers") or {}).get("wisdom-knowledge") or {}
        for key, value in (server.get("env") or {}).items():
            if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
                os.environ.setdefault(key, str(value))
    secrets_path = Path(
        os.environ.get("UUMA_KAG_SECRETS_FILE", profile_home / ".env")
    ).expanduser()
    if secrets_path.is_file():
        for raw_line in secrets_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"BRAVE_SEARCH_API_KEY", "UUMA_OPENALEX_MAILTO"}:
                os.environ.setdefault(key.strip(), value.strip().strip("\"").strip("'"))
    os.environ.setdefault("UUMA_AGENT_ID", "wisdom-oldman")


class OrbitNotificationDispatcher:
    def __init__(
        self,
        orbits: QuestionOrbitService,
        hermes_executable: Path,
        profile_home: Path,
        *,
        command_runner=subprocess.run,
    ) -> None:
        self.orbits = orbits
        self.hermes_executable = hermes_executable
        self.profile_home = profile_home
        self.command_runner = command_runner

    def dispatch_one(self) -> bool:
        notification = self.orbits.claim_notification(actor_id="orchestrator")
        if notification is None:
            return False
        route = notification["route"]
        target = self._target(route)
        if not target:
            self.orbits.finish_notification(
                notification["orbit_notification_id"],
                sent=False,
                error="Notification route does not identify a supported platform target.",
                actor_id="orchestrator",
            )
            return True
        message = self._message(notification)
        environment = os.environ.copy()
        environment["HERMES_HOME"] = str(self.profile_home)
        try:
            result = self.command_runner(
                [str(self.hermes_executable), "send", "--to", target, "--quiet", message],
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Hermes send failed.").strip()
                raise RuntimeError(detail[:2000])
        except Exception as exc:  # noqa: BLE001 - Delivery failures belong in the durable outbox.
            self.orbits.finish_notification(
                notification["orbit_notification_id"],
                sent=False,
                error=str(exc),
                actor_id="orchestrator",
            )
        else:
            self.orbits.finish_notification(
                notification["orbit_notification_id"],
                sent=True,
                actor_id="orchestrator",
            )
        return True

    @staticmethod
    def _target(route: dict[str, str]) -> str | None:
        platform = route.get("platform", "").strip()
        chat_id = route.get("chat_id", "").strip()
        thread_id = route.get("thread_id", "").strip()
        if not platform:
            return None
        parts = [platform]
        if chat_id:
            parts.append(chat_id)
        if thread_id:
            parts.append(thread_id)
        return ":".join(parts)

    @staticmethod
    def _message(notification: dict[str, Any]) -> str:
        payload = notification.get("payload") or {}
        topic = str(payload.get("topic_title") or "持续研究")
        status = str(payload.get("research_status") or notification["event_type"])
        lines = [f"Wisdom-Oldman 研究更新｜{topic}", f"状态：{status}"]
        if payload.get("summary"):
            lines.extend(["", str(payload["summary"]).strip()])
        if payload.get("change_summary"):
            lines.extend(["", f"本轮变化：{payload['change_summary']}"])
        sources = payload.get("sources") or []
        if sources:
            lines.extend(["", "来源："])
            for source in sources[:5]:
                if not isinstance(source, dict):
                    continue
                location = f"（{source['location']}）" if source.get("location") else ""
                lines.append(f"- {source.get('title') or '来源'}{location}: {source.get('locator')}")
        remaining = payload.get("remaining_questions") or []
        if remaining:
            lines.extend(["", "仍待研究："])
            lines.extend(f"- {item}" for item in remaining[:5])
        if payload.get("reason"):
            lines.extend(["", f"说明：{payload['reason']}"])
        if payload.get("document_url"):
            lines.extend(["", f"完整主题文档：{payload['document_url']}"])
        return "\n".join(lines)


class _Heartbeat:
    def __init__(
        self,
        orbits: QuestionOrbitService,
        cycle_id: str,
        owner_id: str,
        interval: float,
    ) -> None:
        self.orbits = orbits
        self.cycle_id = cycle_id
        self.owner_id = owner_id
        self.interval = interval
        self.stopped = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.interval <= 0:
            return
        self.thread = threading.Thread(target=self._run, name="uuma-orbit-heartbeat", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=max(1.0, self.interval + 1))

    def _run(self) -> None:
        while not self.stopped.wait(self.interval):
            try:
                self.orbits.heartbeat_cycle(
                    self.cycle_id, self.owner_id, lease_seconds=max(90, int(self.interval * 3))
                )
            except (KeyError, PermissionError, ValueError):
                return
            except Exception:
                LOGGER.exception("Orbit cycle heartbeat failed")


class OrbitRunner:
    BRAVE_MONTHLY_LIMIT = 950

    def __init__(
        self,
        knowledge: KnowledgeService,
        orbits: QuestionOrbitService,
        reasoner: KnowledgeReasoner,
        providers: list[DiscoveryProvider],
        ingestor: KnowledgeIngestor,
        constructor: KnowledgeConstructor,
        projection_worker: KagProjectionWorker,
        dispatcher: OrbitNotificationDispatcher,
        *,
        owner_id: str | None = None,
        heartbeat_interval: float = 45,
        sources_per_cycle: int = 2,
    ) -> None:
        self.knowledge = knowledge
        self.orbits = orbits
        self.reasoner = reasoner
        self.providers = providers
        self.ingestor = ingestor
        self.constructor = constructor
        self.projection_worker = projection_worker
        self.dispatcher = dispatcher
        self.owner_id = owner_id or f"{socket.gethostname()}:{os.getpid()}"
        self.heartbeat_interval = heartbeat_interval
        self.sources_per_cycle = max(1, min(sources_per_cycle, 5))
        self._idle_logged = False

    def run_once(self) -> bool:
        LOGGER.debug("Polling for a runnable Orbit cycle owner=%s", self.owner_id)
        cycle = self.orbits.acquire_cycle(
            self.owner_id, lease_seconds=max(180, int(self.heartbeat_interval * 3))
        )
        if cycle is None:
            if not self._idle_logged:
                LOGGER.info(
                    "No runnable Orbit cycle is currently available owner=%s queue=%s",
                    self.owner_id,
                    self._queue_snapshot(),
                )
                self._idle_logged = True
            self.dispatcher.dispatch_one()
            return False
        self._idle_logged = False
        LOGGER.info(
            "Claimed Orbit cycle orbit=%s cycle=%s attempt=%s",
            cycle["orbit_id"],
            cycle["orbit_cycle_id"],
            cycle["attempt"],
        )
        heartbeat = _Heartbeat(
            self.orbits,
            cycle["orbit_cycle_id"],
            self.owner_id,
            self.heartbeat_interval,
        )
        heartbeat.start()
        started = time.monotonic()
        try:
            self._process_cycle(cycle, started)
        except RetryAfterError as exc:
            heartbeat.stop()
            LOGGER.warning(
                "Orbit cycle requested retry orbit=%s cycle=%s retry_after=%s",
                cycle["orbit_id"],
                cycle["orbit_cycle_id"],
                exc.retry_after_seconds,
            )
            self.orbits.fail_cycle(
                cycle["orbit_cycle_id"],
                self.owner_id,
                str(exc),
                retry_after_seconds=exc.retry_after_seconds,
            )
        except PermissionError as exc:
            heartbeat.stop()
            LOGGER.warning(
                "Orbit cycle blocked orbit=%s cycle=%s reason=%s",
                cycle["orbit_id"],
                cycle["orbit_cycle_id"],
                str(exc)[:500],
            )
            self.orbits.fail_cycle(
                cycle["orbit_cycle_id"], self.owner_id, str(exc), recoverable=False, blocked=True
            )
        except Exception as exc:
            heartbeat.stop()
            LOGGER.exception("Question Orbit cycle failed")
            self.orbits.fail_cycle(cycle["orbit_cycle_id"], self.owner_id, str(exc))
        else:
            heartbeat.stop()
            LOGGER.info(
                "Completed Orbit cycle processing orbit=%s cycle=%s",
                cycle["orbit_id"],
                cycle["orbit_cycle_id"],
            )
        self.dispatcher.dispatch_one()
        return True

    def _queue_snapshot(self) -> dict[str, int | str]:
        now = datetime.now(UTC).isoformat()
        with self.knowledge.store.connect() as conn:
            active = conn.execute(
                "SELECT COUNT(*) AS count FROM orbit_cycles "
                "WHERE status = 'RUNNING' AND lease_expires_at > ?",
                (now,),
            ).fetchone()["count"]
            expired = conn.execute(
                "SELECT COUNT(*) AS count FROM orbit_cycles "
                "WHERE status IN ('RUNNING', 'RETRY') AND lease_expires_at <= ?",
                (now,),
            ).fetchone()["count"]
            queued = conn.execute(
                "SELECT COUNT(*) AS count FROM question_orbits WHERE status = 'QUEUED'"
            ).fetchone()["count"]
            total_cycles = conn.execute(
                "SELECT COUNT(*) AS count FROM orbit_cycles"
            ).fetchone()["count"]
            total_orbits = conn.execute(
                "SELECT COUNT(*) AS count FROM question_orbits"
            ).fetchone()["count"]
        return {
            "now": now,
            "active": active,
            "expired": expired,
            "queued": queued,
            "total_cycles": total_cycles,
            "total_orbits": total_orbits,
        }

    def _process_cycle(self, cycle: dict[str, Any], started: float) -> None:
        if not ensure_knowledge_graph("wisdom-oldman", recover=True)["ready"]:
            raise PermissionError("Knowledge graph unavailable; background research is blocked.")
        question = self.knowledge._require("questions", cycle["question_id"])["text"]
        orbit_state = self.orbits.get(cycle["orbit_id"])
        current = self.reasoner.answer(
            question,
            requested_mode=ReasoningMode.SIMPLE,
            actor_id="wisdom-oldman",
            recover=True,
        )
        if current.get("runtime_status") != "KAG":
            raise PermissionError("Graph reasoning failed; background text-only fallback is blocked.")
        current_level = SatisfactionLevel(current["satisfaction_level"])
        if current_level in {SatisfactionLevel.SUFFICIENT, SatisfactionLevel.STRONG}:
            self._complete(cycle, started, current, [], [], [], 0)
            return

        artifacts = urls_in_question(question)
        discovery_queries: list[str] = []
        brave_queries = 0
        retry_delays: list[int] = []
        for provider in self.providers:
            if provider.name == "brave":
                usage = self.orbits.discovery_usage(provider="brave")
                if usage["requests"] >= self.BRAVE_MONTHLY_LIMIT:
                    continue
            try:
                response = provider.discover(question, limit=5)
            except RetryAfterError as exc:
                retry_delays.append(exc.retry_after_seconds)
                continue
            except Exception as exc:  # noqa: BLE001 - One provider must not sink the Orbit.
                LOGGER.warning("Discovery provider %s failed: %s", provider.name, exc)
                continue
            discovery_queries.append(question)
            if provider.name == "brave":
                brave_queries += 1
            self.orbits.record_discovery_usage(
                cycle["orbit_id"],
                provider.name,
                result_count=len(response.artifacts),
                provider_request_id=response.request_id,
            )
            artifacts.extend(response.artifacts)

        deduped: list[DiscoveryArtifact] = []
        seen: set[str] = set()
        for artifact in artifacts:
            identity = artifact_identity(artifact)
            if identity in seen:
                continue
            seen.add(identity)
            deduped.append(artifact)

        budget = orbit_state["budget"]
        run = orbit_state["research_run"]
        source_capacity = max(0, int(budget["sources"]) - int(run["sources_used"]))
        source_ids: list[str] = []
        evidence_ids: list[str] = []
        model_input_characters = len(str(current.get("answer") or ""))
        used_source_ids = self.orbits.used_source_ids(cycle["orbit_id"])
        for artifact in deduped:
            if len(source_ids) >= min(self.sources_per_cycle, source_capacity):
                break
            try:
                ingested = self.ingestor.ingest_web(
                    artifact.locator, actor_id="wisdom-oldman"
                )
            except RetryAfterError as exc:
                retry_delays.append(exc.retry_after_seconds)
                continue
            except PermissionError as exc:
                self.orbits.enqueue_notification(
                    cycle["orbit_id"],
                    "USER_ACTION_REQUIRED",
                    {"reason": str(exc), "locator": artifact.locator},
                    dedupe_suffix=(
                        f"{cycle['cycle_key']}:"
                        f"{hashlib.sha256(artifact_identity(artifact).encode()).hexdigest()[:16]}"
                    ),
                )
                LOGGER.warning("Discovery artifact %s requires user action: %s", artifact.locator, exc)
                continue
            except (OSError, ValueError) as exc:
                LOGGER.warning("Discovery artifact %s was skipped: %s", artifact.locator, exc)
                continue
            source_id = ingested["source"]["source_id"]
            if source_id in used_source_ids or source_id in source_ids:
                continue
            source_ids.append(source_id)
            model_input_characters += sum(
                len(str(chunk.get("text") or "")) for chunk in ingested.get("chunks", [])
            )
            document_id = ingested["document"]["document_id"]
            extraction = self.constructor.extract_document(
                document_id,
                actor_id="wisdom-oldman",
                max_chunks=20,
                recover=True,
            )
            evidence_ids.extend(extraction["created"]["evidence"])
            evidence_ids.extend(extraction["reused"]["evidence"])

        if not source_ids and source_capacity > 0:
            if retry_delays:
                raise RetryAfterError(
                    "All available discovery providers requested retry later.", max(retry_delays)
                )
            raise PermissionError("No safe, publicly retrievable source was available for this cycle.")

        try:
            sync = self.projection_worker.sync(limit=200, recover=True)
        except KagUnavailableError as exc:
            raise PermissionError("Graph projection unavailable; research is blocked.") from exc
        final_answer = self.reasoner.answer(
            question,
            requested_mode=ReasoningMode.AUTO,
            actor_id="wisdom-oldman",
            recover=True,
        )
        if final_answer.get("runtime_status") != "KAG":
            raise PermissionError("Graph reasoning failed; no topic document was published.")
        final_answer = self._assess_satisfaction(
            final_answer, source_ids=source_ids, evidence_ids=evidence_ids
        )
        expanded = self.orbits.expand_frontier(
            cycle["orbit_id"], final_answer.get("remaining_gap_ids") or []
        )
        generated_question_ids = list(
            dict.fromkeys(item["question_id"] for item in expanded)
        )
        conflicts = final_answer.get("conflicts") or []
        completion = self._complete(
            cycle,
            started,
            final_answer,
            source_ids,
            evidence_ids,
            discovery_queries,
            int(sync.get("watermark", 0)),
            brave_queries=brave_queries,
            generated_question_ids=generated_question_ids,
            model_input_characters=model_input_characters,
        )
        version = completion.get("document_version") or {}
        section = next(
            (
                item
                for item in version.get("sections", [])
                if item.get("question_id") == cycle["question_id"]
            ),
            {},
        )
        digest_payload = {
            "topic_title": version.get("topic_title"),
            "summary": str(final_answer.get("answer") or "")[:2000],
            "change_summary": version.get("change_summary"),
            "document_url": version.get("document_url"),
            "sources": section.get("citations", [])[:8],
            "research_status": completion["orbit"]["status"],
        }
        if self._materially_changed(current, final_answer):
            self.orbits.enqueue_notification(
                cycle["orbit_id"],
                "MATERIAL_CONCLUSION_CHANGE",
                digest_payload,
                dedupe_suffix=cycle["cycle_key"],
            )
        if conflicts:
            self.orbits.enqueue_notification(
                cycle["orbit_id"],
                "EVIDENCE_CONFLICT",
                digest_payload | {"conflicts": conflicts[:10]},
                dedupe_suffix=cycle["cycle_key"],
            )

    def _complete(
        self,
        cycle: dict[str, Any],
        started: float,
        answer: dict[str, Any],
        source_ids: list[str],
        evidence_ids: list[str],
        discovery_queries: list[str],
        kag_watermark: int,
        *,
        brave_queries: int = 0,
        generated_question_ids: list[str] | None = None,
        model_input_characters: int = 0,
    ) -> dict[str, Any]:
        answer_text = str(answer.get("answer") or "")
        estimated_tokens = max(
            1,
            (
                len(answer_text)
                + model_input_characters
                + sum(map(len, discovery_queries))
            )
            // 4,
        )
        return self.orbits.complete_cycle(
            cycle["orbit_cycle_id"],
            self.owner_id,
            satisfaction_level=SatisfactionLevel(answer["satisfaction_level"]),
            satisfaction_rationale=answer["satisfaction_rationale"],
            active_seconds=max(0.0, time.monotonic() - started),
            source_ids=source_ids,
            evidence_ids=evidence_ids,
            generated_question_ids=generated_question_ids,
            discovery_queries=discovery_queries,
            search_queries_used=brave_queries,
            model_tokens_used=estimated_tokens,
            kag_watermark=kag_watermark,
            decision=(
                "COMPLETE"
                if answer["satisfaction_level"] in {"SUFFICIENT", "STRONG"}
                else "CONTINUE"
            ),
            answer=answer,
        )

    @staticmethod
    def _materially_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
        before_words = set(re.findall(r"\w+", str(before.get("answer") or "").casefold()))
        after_words = set(re.findall(r"\w+", str(after.get("answer") or "").casefold()))
        if not before_words or not after_words:
            return False
        overlap = len(before_words & after_words) / len(before_words | after_words)
        satisfaction_changed = before.get("satisfaction_level") != after.get(
            "satisfaction_level"
        )
        return overlap < 0.6 or (satisfaction_changed and overlap < 0.85)

    @staticmethod
    def _assess_satisfaction(
        answer: dict[str, Any], *, source_ids: list[str], evidence_ids: list[str]
    ) -> dict[str, Any]:
        level = SatisfactionLevel(answer["satisfaction_level"])
        if level in {SatisfactionLevel.SUFFICIENT, SatisfactionLevel.STRONG}:
            return answer
        cited_sources = {
            str(citation.get("source_id"))
            for citation in answer.get("citations", [])
            if isinstance(citation, dict) and citation.get("source_id")
        }
        independently_cited = cited_sources.intersection(source_ids)
        if (
            len(independently_cited) >= 2
            and len(set(evidence_ids)) >= 2
            and not answer.get("conflicts")
        ):
            return answer | {
                "satisfaction_level": SatisfactionLevel.SUFFICIENT.value,
                "satisfaction_rationale": (
                    "The current answer cites at least two independently acquired sources with "
                    "located evidence and no unresolved conflict."
                ),
            }
        return answer


def build_runner(profile_home: Path) -> OrbitRunner:
    load_profile_environment(profile_home)
    settings = Settings.from_env()
    settings.ensure_directories()
    knowledge = KnowledgeService(settings.knowledge_database_path())
    topics = TopicKnowledgeService(
        knowledge,
        view_base_url=os.environ.get("UUMA_WISDOM_VIEW_BASE_URL", "http://127.0.0.1:8767"),
        view_token=ensure_view_token(settings.data_dir),
    )
    orbits = QuestionOrbitService(knowledge, topics=topics)
    backend = OpenSpgKagBackend.from_env()
    fetcher = SafeWebFetcher()
    dispatcher = OrbitNotificationDispatcher(
        orbits, settings.hermes_executable, profile_home
    )
    return OrbitRunner(
        knowledge,
        orbits,
        KnowledgeReasoner(knowledge, backend),
        [CanonicalCitationProvider(knowledge), *configured_providers(fetcher)],
        KnowledgeIngestor(knowledge, settings.knowledge_content_path(), fetcher=fetcher),
        KnowledgeConstructor(knowledge, backend),
        KagProjectionWorker(knowledge, backend),
        dispatcher,
    )


def main() -> None:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    parser = argparse.ArgumentParser(description="Run governed Wisdom-Oldman Question Orbits.")
    parser.add_argument(
        "--profile-home",
        type=Path,
        default=local_app_data / "hermes" / "profiles" / "wisdom-oldman",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument(
        "--idle-timeout-seconds",
        type=float,
        default=float(os.environ.get("UUMA_ORBIT_IDLE_TIMEOUT_SECONDS", "0")),
        help="Exit automatically after remaining idle for N seconds (0 = run indefinitely).",
    )
    args = parser.parse_args()
    load_profile_environment(args.profile_home)
    enabled = os.environ.get("UUMA_QUESTION_ORBIT_ENABLED", "false").lower() in {
        "1", "true", "yes", "on"
    }
    if not enabled:
        raise SystemExit("Question Orbit runner is disabled by UUMA_QUESTION_ORBIT_ENABLED.")
    settings = Settings.from_env()
    settings.ensure_directories()
    log_path = settings.data_dir / "orbit-runner.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    try:
        with _RunnerInstanceLock(settings.data_dir / "orbit-runner.lock"):
            runner = build_runner(args.profile_home)
            LOGGER.info(
                "Question Orbit runner started owner=%s poll_seconds=%s profile=%s database=%s",
                runner.owner_id,
                max(1.0, min(args.poll_seconds, 60.0)),
                args.profile_home,
                runner.knowledge.store.path.resolve(),
            )
            if args.once:
                runner.run_once()
                return
            poll_seconds = max(1.0, min(args.poll_seconds, 60.0))
            last_work_time = time.monotonic()
            while True:
                had_work = runner.run_once()
                now = time.monotonic()
                if had_work:
                    last_work_time = now
                elif (
                    args.idle_timeout_seconds > 0
                    and (now - last_work_time) >= args.idle_timeout_seconds
                ):
                    LOGGER.info(
                        "Question Orbit runner idle timeout reached (%s seconds with no runnable cycles); exiting.",
                        args.idle_timeout_seconds,
                    )
                    break
                time.sleep(poll_seconds)
    except RuntimeError as exc:
        LOGGER.warning("Question Orbit runner did not start: %s", exc)
    except KeyboardInterrupt:
        LOGGER.warning("Question Orbit runner was interrupted by an external stop request.")
        raise SystemExit(130) from None
    except Exception:
        LOGGER.exception("Question Orbit runner terminated unexpectedly.")
        raise
    finally:
        LOGGER.info("Question Orbit runner process exiting.")


if __name__ == "__main__":
    main()
