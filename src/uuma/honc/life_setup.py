"""Explicit, reversible deployment into the existing honc Hermes profile only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ruamel.yaml import YAML

from ..specialist_skills import SPECIALIST_SKILL_ALLOWLISTS
from .life_context import LifeContextBroker
from .life_migration import apply_migration
from .life_models import LifeSettings, SettingsUpdateRequest
from .life_service import LifeService
from .life_store import canonical

HONC_TOOLS = (
    "honc_status",
    "honc_get_context",
    "honc_record_execution",
    "honc_control_round",
    "honc_assess_completion",
    "honc_apply_completion",
    "honc_correct_record",
    "honc_get_report",
    "honc_reconcile_updates",
    "honc_get_life_context",
    "honc_configure_habit",
    "honc_update_life_settings",
    "honc_record_habit",
    "honc_record_body",
    "honc_save_diary",
    "honc_correct_life_record",
    "honc_record_anchor",
    "honc_get_life_operation",
    "honc_get_life_history",
)
FORBIDDEN_TOOLSETS = {
    "terminal",
    "browser",
    "code_execution",
    "computer_use",
    "delegation",
    "cronjob",
    "connections",
    "file",
    "kanban",
}
BEGIN, END = "<!-- UUMA-MANAGED-SOUL-START -->", "<!-- UUMA-MANAGED-SOUL-END -->"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure(config: dict, runtime_path: Path) -> None:
    """Only honc role permissions change; preserve the model and all unrelated keys."""
    servers = config["mcp_servers"]
    if set(servers) != {"uuma-worker", "honc-execution"}:
        raise ValueError("Unexpected honc MCP servers; preserve and reconcile before installing")
    execution = servers["honc-execution"]
    if execution["args"][:2] != ["-m", "uuma.honc.mcp"]:
        raise ValueError("Unexpected existing honc execution command")
    execution["args"] = ["-m", "uuma.honc.mcp", "--life-config", str(runtime_path)]
    execution["tools"] = {"include": list(HONC_TOOLS), "resources": False, "prompts": False}
    servers["uuma-worker"].setdefault("tools", {}).update(resources=False, prompts=False)
    config["honc_life"] = {"runtime_config": str(runtime_path)}
    plugins = config.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    if "honc_life" not in enabled:
        enabled.append("honc_life")
    disabled = plugins.setdefault("disabled", [])
    if "honc_life" in disabled:
        disabled.remove("honc_life")
    for values in config.get("platform_toolsets", {}).values():
        if isinstance(values, list):
            values[:] = [value for value in values if value not in FORBIDDEN_TOOLSETS]
    config.setdefault("tools", {}).setdefault("tool_search", {})["enabled"] = "off"


def managed_soul(current: str, source: str) -> str:
    managed = f"{BEGIN}\n{source.strip()}\n{END}"
    if BEGIN not in current and END not in current:
        return managed + "\n" + current
    if current.count(BEGIN) != 1 or current.count(END) != 1:
        raise ValueError("Malformed existing SOUL managed boundary")
    return re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: managed, current, flags=re.DOTALL
    )


def initialize_settings(service: LifeService) -> dict:
    """Persist accepted defaults once; a later installation never overwrites user settings."""
    with service.store.ledger.connect() as connection:
        previous = connection.execute(
            "SELECT s.source_ref, q.request_ref, p.result_json FROM life_sources s "
            "JOIN life_requests q ON q.source_ref=s.source_ref "
            "LEFT JOIN life_operations p ON p.request_ref=q.request_ref "
            "WHERE s.owner_id=? AND s.adapter_id='authorized-local-life-setup' "
            "AND s.source_event_id='honc-life-defaults-v1'",
            (service.owner_id,),
        ).fetchone()
    if previous and previous["result_json"]:
        result = json.loads(previous["result_json"])
        return {"state": "ALREADY_INITIALIZED", "operation_id": result["operation_id"]}
    if service.get_context().data["settings_persisted"]:
        return {"state": "EXISTING_USER_SETTINGS_PRESERVED"}
    patch = LifeSettings().model_dump(
        mode="json",
        exclude={
            "revision",
            "timezone",
            "body_followup_enabled",
            "nightly_unchecked_habit_chase_enabled",
            "importance_does_not_change_count",
        },
    )
    authorization = "settle until fully setup honc as i expected"
    now = datetime.now(UTC)
    if previous:
        with service.store.ledger.connect() as connection:
            now = datetime.fromisoformat(
                connection.execute(
                    "SELECT received_at FROM life_sources WHERE source_ref=?",
                    (previous["source_ref"],),
                ).fetchone()[0]
            )
    receipt = service.receive_user_message(
        adapter_id="authorized-local-life-setup",
        source_event_id="honc-life-defaults-v1",
        raw_content=canonical({"authorization": authorization, "accepted_defaults": patch}),
        received_at=now,
        source_origin="configuration_import",
        granted_operations=("update_settings",),
    )
    result = service.bind_source(receipt["source_ref"]).update_settings(
        SettingsUpdateRequest(
            request_ref=receipt["request_refs"]["update_settings"],
            source_quote=authorization,
            expected_revision=0,
            patch=patch,
        )
    )
    if not result.ok:
        raise ValueError("Could not initialize life settings: " + result.status)
    return {"state": "INITIALIZED", "operation_id": result.operation_id}


def native(
    repository: Path, hermes_root: Path, profile_home: Path, action: str, runtime_path: Path
) -> dict:
    environment = dict(os.environ, HERMES_HOME=str(profile_home), PYTHONUTF8="1")
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            str(hermes_root / "venv/Scripts/python.exe"),
            "-X",
            "utf8",
            str(repository / "scripts/honc-native-lifecycle.py"),
            action,
            str(runtime_path),
        ],
        cwd=hermes_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if result.returncode:
        # The helper contains no credentials; retain its actual diagnostics locally.
        raise RuntimeError("Native honc lifecycle failed: " + result.stderr[-2000:])
    return json.loads(result.stdout)


def install(
    repository: Path,
    profile_home: Path,
    database: Path,
    hermes_root: Path,
    cache: Path,
    history: Path,
) -> dict:
    repository, profile_home = repository.resolve(), profile_home.resolve()
    if profile_home.name != "honc" or profile_home.parent.name != "profiles":
        raise ValueError("Deployment is restricted to the existing honc profile")
    if database.name != "honc.db":
        raise ValueError("Life data belongs only to honc.db")
    from dotenv import dotenv_values

    private_env = dotenv_values(profile_home / ".env")
    owners = [
        value.strip() for value in (private_env.get("TELEGRAM_ALLOWED_USERS") or "").split(",")
    ]
    if len(owners) != 1 or not owners[0].isdigit() or not private_env.get("TELEGRAM_BOT_TOKEN"):
        raise ValueError("An existing single private Telegram owner/bot binding is required")
    private_files = [
        path for path in (profile_home / ".env", profile_home / "auth.json") if path.exists()
    ]
    credentials = {str(path): digest(path) for path in private_files}
    yaml = YAML()
    config = yaml.load((profile_home / "config.yaml").read_text(encoding="utf-8"))
    original_model = json.dumps(config.get("model"), sort_keys=True)
    runtime_path = profile_home / "plugins/honc_life/runtime.json"
    prior = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.exists() else {}
    if prior and prior["owner_id"] != owners[0]:
        raise ValueError("Existing life owner differs; no automatic migration across owners")
    backup = repository / ".uuma-local/honc-deployment-backups" / uuid4().hex
    backup.mkdir(parents=True)
    targets = [
        profile_home / "config.yaml",
        profile_home / "SOUL.md",
        profile_home / "plugins/honc_life",
        profile_home / "scripts/honc-life-tick.py",
    ]
    targets += [
        profile_home / "skills" / name for name in sorted(SPECIALIST_SKILL_ALLOWLISTS["honc"])
    ]
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "backup_directory": str(backup),
        "profile_home": str(profile_home),
        "owned_paths": [],
        "database_backup": None,
        "rollback": "Pause honc life native job; restore owned paths from backup. Keep appended life records and receipts; do not delete history or restore honc.db over new user facts.",
    }
    for path in targets:
        relative = path.relative_to(profile_home)
        saved = backup / "profile" / relative
        if path.is_dir():
            shutil.copytree(path, saved, ignore=shutil.ignore_patterns("__pycache__"))
        elif path.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
        manifest["owned_paths"].append(
            {"path": str(path), "existed": path.exists(), "backup": str(saved)}
        )
    if database.exists():
        with (
            sqlite3.connect(database) as source,
            sqlite3.connect(backup / "honc.db") as destination,
        ):
            source.backup(destination)
        manifest["database_backup"] = str(backup / "honc.db")
    (backup / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    runtime = {
        "profile": "honc",
        "owner_id": owners[0],
        "database_path": str(database),
        "repository_root": str(repository),
        "profile_home": str(profile_home),
        "delivery_binding": {"platform": "telegram", "chat_id": owners[0]},
        "scheduler_job_id": prior.get("scheduler_job_id"),
        "config_path": str(runtime_path),
    }
    plugin = runtime_path.parent
    shutil.copytree(
        repository / "integrations/hermes/honc_life",
        plugin,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "runtime.json"),
    )
    runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")
    scripts = profile_home / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "honc-life-tick.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        + f"sys.path.insert(0, {str(repository / 'src')!r})\n"
        + "from uuma.honc.native_reminders import main\n"
        + f"main(Path({str(runtime_path)!r}))\n",
        encoding="utf-8",
    )
    job = native(repository, hermes_root, profile_home, "prepare", runtime_path)
    runtime["scheduler_job_id"] = job["id"]
    runtime_path.write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")
    configure(config, runtime_path)
    assert original_model == json.dumps(config.get("model"), sort_keys=True)
    temp = profile_home / (".config-honc-life-" + uuid4().hex + ".yaml")
    with temp.open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle)
    temp.replace(profile_home / "config.yaml")
    soul = profile_home / "SOUL.md"
    soul.write_text(
        managed_soul(
            soul.read_text(encoding="utf-8") if soul.exists() else "",
            (repository / "profiles/honc/SOUL.md").read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    for name in SPECIALIST_SKILL_ALLOWLISTS["honc"]:
        shutil.copytree(
            repository / "profiles/honc/skills" / name,
            profile_home / "skills" / name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    broker = LifeContextBroker(runtime)
    service = LifeService(
        broker.store,
        owner_id=runtime["owner_id"],
        profile="honc",
        session_id="authorized-local-setup",
        reminders=broker.runtime,
    )
    settings_receipt = initialize_settings(service)
    migration = apply_migration(service, cache, history)
    for path in private_files:
        assert digest(path) == credentials[str(path)], "Credentials were modified"
    result = {
        "installed_at": datetime.now(UTC).isoformat(),
        "profile": "honc",
        "backup_manifest": str(backup / "manifest.json"),
        "model_preserved": True,
        "credentials_preserved": True,
        "native_job": job,
        "life_tools": len(HONC_TOOLS),
        "skills": sorted(SPECIALIST_SKILL_ALLOWLISTS["honc"]),
        "migration": migration,
        "settings_initialization": settings_receipt,
        "activated": False,
    }
    evidence = repository / "docs/reviews/honc-architecture-2026-10-13/live-installation-v1.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    for key in ("repository", "profile-home", "database", "hermes-root", "cache", "history"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    result = install(
        args.repository,
        args.profile_home,
        args.database,
        args.hermes_root,
        args.cache,
        args.history,
    )
    print(
        json.dumps(
            {
                "profile": "honc",
                "habits": len(result["migration"]["mapping"]),
                "skills": len(result["skills"]),
                "life_tools": 10,
                "job_paused": True,
                "model_preserved": True,
                "credentials_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    main()
