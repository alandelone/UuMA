"""Install Yonc's role sources and narrow tools into an existing Hermes profile."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from ruamel.yaml import YAML

from uuma.specialist_skills import prune_specialist_skills

BEGIN = "<!-- UUMA-MANAGED-SOUL-START -->"
END = "<!-- UUMA-MANAGED-SOUL-END -->"
SKILLS = ("yonc-project-management", "yonc-colleagues")


def role_sources() -> dict[str, str]:
    sources = {}
    for agent in ("brainstormer", "scholar", "wisdom-oldman", "forge-lab-bot", "yonc"):
        sources[f"{agent}.md"] = f"docs/agents/{agent}.md"
        sources[f"{agent}-SOUL.md"] = f"profiles/{agent}/SOUL.md"
    sources["agent-index.md"] = "docs/agents/README.md"
    sources["orchestrator-policy.md"] = "profiles/orchestrator/SOUL.addendum.md"
    return sources


def managed_soul(current: str, source: str, baseline: str) -> str:
    managed = f"{BEGIN}\n{source.strip()}\n{END}\n"
    if BEGIN in current or END in current:
        if current.count(BEGIN) != 1 or current.count(END) != 1:
            raise ValueError("Malformed managed SOUL markers; reconcile the profile before deployment.")
        pattern = re.escape(BEGIN) + r".*?" + re.escape(END)
        if not re.search(pattern, current, flags=re.DOTALL):
            raise ValueError("SOUL markers are in the wrong order.")
        return re.sub(pattern, lambda _: managed.rstrip(), current, flags=re.DOTALL)
    if current.strip() in {"", source.strip(), baseline.strip()}:
        return managed
    raise ValueError("Custom SOUL differs from the managed source; reconcile it before deployment.")


def deploy(source_root: Path, profile_home: Path, backup_root: Path, *, apply: bool) -> dict:
    source_root, profile_home, backup_root = (
        path.resolve() for path in (source_root, profile_home, backup_root)
    )
    if profile_home.name != "yonc" or not (profile_home / "config.yaml").is_file():
        raise ValueError("An existing yonc profile is required.")
    if backup_root == profile_home or profile_home in backup_root.parents:
        raise ValueError("Backups must be outside the live profile.")
    sources = role_sources()
    required = [source_root / locator for locator in sources.values()]
    required += [source_root / f"profiles/yonc/skills/{skill}/SKILL.md" for skill in SKILLS]
    required += [source_root / "integrations/hermes/uuma_control_guard" / name
                 for name in ("__init__.py", "plugin.yaml")]
    required.append(source_root / "scripts/configure-hermes-profile.py")
    if any(not path.is_file() for path in required):
        raise ValueError("A required role document, skill, guard or configurator is missing.")
    config = YAML(typ="safe").load((profile_home / "config.yaml").read_text(encoding="utf-8-sig"))
    worker = config["mcp_servers"]["uuma-worker"]
    project = config["mcp_servers"]["yonc-project"]
    data_dir = worker["env"]["UUMA_DATA_DIR"]
    yonc_root = project["env"]["PYTHONPATH"]
    api_url = project["env"]["YONC_API_URL"]
    current = (profile_home / "SOUL.md").read_text(encoding="utf-8-sig")
    source = (source_root / "profiles/yonc/SOUL.md").read_text(encoding="utf-8")
    baseline_result = subprocess.run(
        ["git", "show", "HEAD:profiles/yonc/SOUL.md"], cwd=source_root,
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    soul = managed_soul(current, source, baseline_result.stdout)
    backup_home = backup_root / datetime.now(UTC).strftime("%Y%m%d-%H%M%S%f")
    preview = prune_specialist_skills(profile_home, "yonc", backup_home / "skills", apply=False)
    report = {
        "applied": apply, "profile_home": str(profile_home), "backup_home": str(backup_home),
        "role_document_count": len(sources), "quarantined_skill_count": len(preview.removed_skills),
    }
    if not apply:
        return report
    backup_home.mkdir(parents=True)
    for relative in ("SOUL.md", "config.yaml", "plugins/uuma_control_guard") + tuple(
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
    subprocess.run([
        sys.executable, str(source_root / "scripts/configure-hermes-profile.py"),
        "--config", str(profile_home / "config.yaml"), "--role", "worker", "--agent-id", "yonc",
        "--python-exe", worker["command"], "--source-path", str(source_root / "src"),
        "--data-dir", data_dir, "--gemini-allowed-roots", str(source_root),
        "--yonc-root", yonc_root, "--yonc-python", project["command"], "--yonc-api-url", api_url,
    ], check=True)
    (profile_home / "SOUL.md").write_text(soul, encoding="utf-8")
    for skill in SKILLS:
        target = profile_home / "skills" / skill
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / f"profiles/yonc/skills/{skill}/SKILL.md", target / "SKILL.md")
    references = profile_home / "skills/yonc-colleagues/references"
    references.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, locator in sources.items():
        path = source_root / locator
        shutil.copy2(path, references / name)
        manifest.append({"file": name, "source": locator,
                         "sha256": sha256(path.read_bytes()).hexdigest()})
    (references / "source-manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(UTC).isoformat(), "sources": manifest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    guard = profile_home / "plugins/uuma_control_guard"
    guard.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(source_root / "integrations/hermes/uuma_control_guard" / name, guard / name)
    prune_specialist_skills(profile_home, "yonc", backup_home / "skills", apply=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(deploy(args.source_root, args.profile_home, args.backup_root, apply=args.apply)))


if __name__ == "__main__":
    main()
