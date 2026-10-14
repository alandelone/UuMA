"""Install Honc's role sources, narrow tools, and Telegram token into a Hermes profile."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from uuma.specialist_skills import prune_specialist_skills

BEGIN = "<!-- UUMA-MANAGED-SOUL-START -->"
END = "<!-- UUMA-MANAGED-SOUL-END -->"
SKILLS = ("honc-daily-execution", "honc-tracing", "honc-focus", "honc-checkin",
          "honc-body-tracker", "honc-diary", "honc-life-settings",
          "honc-wake-bedtime", "honc-life-history")


def managed_soul(current: str, source: str) -> str:
    managed = f"{BEGIN}\n{source.strip()}\n{END}\n"
    if BEGIN in current or END in current:
        if current.count(BEGIN) != 1 or current.count(END) != 1:
            raise ValueError("Malformed managed SOUL markers; reconcile the profile before deployment.")
        pattern = re.escape(BEGIN) + r".*?" + re.escape(END)
        if not re.search(pattern, current, flags=re.DOTALL):
            raise ValueError("SOUL markers are in the wrong order.")
        return re.sub(pattern, lambda _: managed.rstrip(), current, flags=re.DOTALL)
    return managed


def set_dotenv_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacement = f"{key}={value}"
    matched = False
    updated = []
    for line in lines:
        if re.match(rf"^{re.escape(key)}=", line):
            matched = True
            updated.append(replacement)
        else:
            updated.append(line)
    if not matched:
        updated.append(replacement)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def deploy(
    source_root: Path,
    profile_home: Path,
    backup_root: Path,
    telegram_token: str,
    *,
    apply: bool,
) -> dict:
    source_root = source_root.resolve()
    profile_home = profile_home.resolve()
    backup_root = backup_root.resolve()

    hermes_exe = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes/hermes-agent/venv/Scripts/hermes.exe"

    # 1. Create profile if it does not exist
    if not profile_home.exists() or not (profile_home / "config.yaml").is_file():
        if apply:
            cmd = [
                str(hermes_exe),
                "profile",
                "create",
                "--clone-from",
                "default",
                "--description",
                "Daily execution, focus rounds, habit tracking, and verified task completion.",
                "honc",
            ]
            subprocess.run(cmd, check=True)
        else:
            return {
                "applied": False,
                "profile_home": str(profile_home),
                "action": "create_profile_needed",
            }

    required = [source_root / f"profiles/honc/skills/{skill}/SKILL.md" for skill in SKILLS]
    required += [
        source_root / "integrations/hermes/uuma_control_guard" / name
        for name in ("__init__.py", "plugin.yaml")
    ]
    required.append(source_root / "scripts/configure-hermes-profile.py")
    if any(not path.is_file() for path in required):
        raise ValueError("A required role document, skill, guard or configurator is missing.")

    current_soul = (
        (profile_home / "SOUL.md").read_text(encoding="utf-8-sig")
        if (profile_home / "SOUL.md").is_file()
        else ""
    )
    source_soul = (source_root / "profiles/honc/SOUL.md").read_text(encoding="utf-8")
    soul = managed_soul(current_soul, source_soul)

    backup_home = backup_root / datetime.now(UTC).strftime("%Y%m%d-%H%M%S%f")
    preview = prune_specialist_skills(profile_home, "honc", backup_home / "skills", apply=False)
    report = {
        "applied": apply,
        "profile_home": str(profile_home),
        "backup_home": str(backup_home),
        "quarantined_skill_count": len(preview.removed_skills),
    }
    if not apply:
        return report

    backup_home.mkdir(parents=True, exist_ok=True)
    for relative in ("SOUL.md", "config.yaml", ".env", "plugins/uuma_control_guard") + tuple(
        f"skills/{skill}" for skill in SKILLS
    ):
        path = profile_home / relative
        if not path.exists():
            continue
        target = backup_home / "previous" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)

    data_dir = str(Path(os.environ.get("LOCALAPPDATA", "")) / "UuMA")

    # Run configurator
    subprocess.run(
        [
            sys.executable,
            str(source_root / "scripts/configure-hermes-profile.py"),
            "--config",
            str(profile_home / "config.yaml"),
            "--role",
            "worker",
            "--agent-id",
            "honc",
            "--python-exe",
            sys.executable,
            "--source-path",
            str(source_root / "src"),
            "--data-dir",
            data_dir,
            "--gemini-allowed-roots",
            str(source_root),
        ],
        check=True,
    )

    (profile_home / "SOUL.md").write_text(soul, encoding="utf-8")
    for skill in SKILLS:
        target = profile_home / "skills" / skill
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / f"profiles/honc/skills/{skill}/SKILL.md", target / "SKILL.md")

    guard = profile_home / "plugins/uuma_control_guard"
    guard.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source_root / "integrations/hermes/uuma_control_guard" / name, guard / name)

    # Configure .env
    dotenv_path = profile_home / ".env"
    set_dotenv_value(dotenv_path, "TELEGRAM_BOT_TOKEN", telegram_token)
    set_dotenv_value(dotenv_path, "TELEGRAM_ALLOWED_USERS", "1055853620")
    set_dotenv_value(dotenv_path, "UUMA_AGENT_ID", "honc")
    set_dotenv_value(dotenv_path, "UUMA_DATA_DIR", data_dir)
    set_dotenv_value(dotenv_path, "UUMA_INGEST_URL", "http://127.0.0.1:8766/ingest/hermes")
    set_dotenv_value(dotenv_path, "UUMA_TOKEN_FILE", str(Path(data_dir) / "tokens.json"))

    prune_specialist_skills(profile_home, "honc", backup_home / "skills", apply=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--profile-home",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", "")) / "hermes/profiles/honc",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", "")) / "UuMA/skill-quarantine/honc",
    )
    parser.add_argument(
        "--telegram-token",
        type=str,
        default="8621039339:AAHBiCtzaMt6QGr4rnhobgMRk9iWx_kx-vY",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            deploy(
                args.source_root,
                args.profile_home,
                args.backup_root,
                args.telegram_token,
                apply=args.apply,
            )
        )
    )


if __name__ == "__main__":
    main()
