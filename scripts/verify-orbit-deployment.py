from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from uuma.knowledge_models import GapRecord, GapType, SatisfactionLevel
from uuma.knowledge_service import KnowledgeService
from uuma.orbit_runner import load_profile_environment
from uuma.question_orbit import QuestionOrbitService
from uuma.settings import Settings

QUESTION = (
    "Question Orbit deployment acceptance: compare RFC 9112 and RFC 7230 handling when both "
    "Transfer-Encoding and Content-Length are present, using "
    "https://www.rfc-editor.org/rfc/rfc9112.txt and "
    "https://www.rfc-editor.org/rfc/rfc7230.txt"
)
OBJECTIVE = "Verify restart-safe unattended research with two public sources and located evidence."


def _latest_telegram_route(profile_home: Path) -> dict[str, str]:
    state_path = profile_home / "state.db"
    with sqlite3.connect(state_path) as conn:
        row = conn.execute(
            "SELECT chat_id, thread_id, id FROM sessions "
            "WHERE source = ? AND chat_id IS NOT NULL "
            "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 1",
            ("telegram",),
        ).fetchone()
    if row is None:
        raise RuntimeError("No Wisdom-Oldman Telegram route is available for acceptance.")
    route = {"platform": "telegram", "chat_id": str(row[0]), "session_id": str(row[2])}
    if row[1] is not None:
        route["thread_id"] = str(row[1])
    return route


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def seed(profile_home: Path, output: Path) -> dict[str, Any]:
    load_profile_environment(profile_home)
    settings = Settings.from_env()
    service = KnowledgeService(settings.knowledge_database_path())
    orbits = QuestionOrbitService(service)
    route = _latest_telegram_route(profile_home)
    baseline_history = service.history(limit=1)
    gap = service.add_gap(
        GapRecord(
            gap_type=GapType.WEAK_EVIDENCE,
            reason=(
                "Deployment acceptance needs two independent public sources and restart "
                "recovery evidence."
            ),
            why_worthwhile="This verifies the deployed Question Orbit runner before handoff.",
        ),
        actor_id="wisdom-oldman",
    )
    started = orbits.start(
        QUESTION,
        OBJECTIVE,
        SatisfactionLevel.PROVISIONAL,
        "The deployed runner has not yet completed a live recovered cycle.",
        actor_id="wisdom-oldman",
        gap_ids=[gap["gap_id"]],
        notification_route=route,
    )
    cycle = orbits.acquire_cycle("acceptance-crash-probe", lease_seconds=30)
    if cycle is None:
        raise RuntimeError("The acceptance Orbit could not acquire its simulated crash lease.")
    report = {
        "phase": "seeded",
        "orbit_id": started["orbit"]["orbit_id"],
        "cycle_id": cycle["orbit_cycle_id"],
        "initial_attempt": cycle["attempt"],
        "route_bound": bool(route),
        "baseline_sequence": (
            baseline_history["events"][0]["sequence"] if baseline_history["events"] else 0
        ),
        "database_path": str(settings.knowledge_database_path().resolve()),
    }
    _write_report(output, report)
    return report


def report(profile_home: Path, output: Path) -> dict[str, Any]:
    load_profile_environment(profile_home)
    settings = Settings.from_env()
    service = KnowledgeService(settings.knowledge_database_path())
    orbits = QuestionOrbitService(service)
    previous = json.loads(output.read_text(encoding="utf-8"))
    orbit_id = str(previous["orbit_id"])
    state = orbits.get(orbit_id)
    cycles = [
        item
        for item in service.list_records("orbit_cycle", limit=1000)["records"]
        if item["orbit_id"] == orbit_id
    ]
    notifications = [
        item
        for item in service.list_records("orbit_notification", limit=1000)["records"]
        if item["orbit_id"] == orbit_id
    ]
    route_matches = state["orbit"]["notification_route"] == _latest_telegram_route(profile_home)
    source_ids = {
        source_id for cycle in cycles for source_id in cycle.get("source_ids", [])
    }
    evidence_ids = {
        evidence_id for cycle in cycles for evidence_id in cycle.get("evidence_ids", [])
    }
    recent_events = [
        event
        for event in service.history(limit=1000)["events"]
        if int(event["sequence"]) > int(previous.get("baseline_sequence", 0))
    ]
    automatic_approval_events = [
        event["event_type"]
        for event in recent_events
        if event["event_type"] in {"CLAIM_ACCEPTED", "PATCH_APPLIED"}
    ]
    terminal = state["orbit"]["status"] in {
        "COMPLETED",
        "BUDGET_EXHAUSTED",
        "BLOCKED",
        "FAILED",
        "STOPPED",
    }
    result = previous | {
        "phase": "terminal" if terminal else "running",
        "orbit_status": state["orbit"]["status"],
        "satisfaction_level": state["orbit"]["satisfaction_level"],
        "stop_reason": state["orbit"].get("stop_reason"),
        "cycle_attempts": [item["attempt"] for item in cycles],
        "cycle_statuses": [item["status"] for item in cycles],
        "unique_source_count": len(source_ids),
        "unique_evidence_count": len(evidence_ids),
        "notification_statuses": [
            {"event": item["event_type"], "status": item["status"]}
            for item in notifications
        ],
        "sent_notification_count": sum(
            1 for item in notifications if item["status"] == "SENT"
        ),
        "route_matches_latest_session": route_matches,
        "automatic_approval_events": automatic_approval_events,
        "event_chain_valid": service.history(limit=1)["chain_valid"],
        "projection_health": service.projection_health(),
    }
    _write_report(output, result)
    return result


def stop(profile_home: Path, output: Path) -> dict[str, Any]:
    load_profile_environment(profile_home)
    settings = Settings.from_env()
    service = KnowledgeService(settings.knowledge_database_path())
    orbits = QuestionOrbitService(service)
    previous = json.loads(output.read_text(encoding="utf-8"))
    state = orbits.get(str(previous["orbit_id"]))
    if state["orbit"]["status"] in {"QUEUED", "ACTIVE", "PAUSED", "BLOCKED"}:
        from uuma.knowledge_models import OrbitStatus

        orbits.transition(
            state["orbit"]["orbit_id"],
            OrbitStatus.STOPPED,
            actor_id="wisdom-oldman",
            reason="Stopped after detecting a noncanonical deployment-acceptance data path.",
        )
    return report(profile_home, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the deployed Question Orbit runner.")
    parser.add_argument("mode", choices=("seed", "report", "stop"))
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "seed":
        result = seed(args.profile_home, args.output)
    elif args.mode == "stop":
        result = stop(args.profile_home, args.output)
    else:
        result = report(args.profile_home, args.output)
    print(json.dumps({"phase": result["phase"], "orbit_id": result["orbit_id"]}))


if __name__ == "__main__":
    main()
