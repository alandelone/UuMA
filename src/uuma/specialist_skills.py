from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

SPECIALIST_SKILL_ALLOWLISTS: dict[str, frozenset[str]] = {
    "yonc": frozenset({"yonc-project-management"}),
    "brainstormer": frozenset(
        {
            "artifact-readiness",
            "discussion-checkpoint",
            "discussion-reentry",
            "discussion-state",
        }
    ),
    "wisdom-oldman": frozenset(
        {
            "wisdom-answer",
            "wisdom-evidence-research",
            "wisdom-investigate",
            "wisdom-knowledge-formation",
            "wisdom-maintain-kag",
            "wisdom-question-orbit",
        }
    ),
    "forge-lab-bot": frozenset(
        {
            "hardware-lab/eschematic",
            "hardware-lab/eschematic-bridge",
            "hardware-lab/lab-as-built",
            "hardware-lab/lab-build-traceability",
            "hardware-lab/lab-commissioning",
            "hardware-lab/lab-engineering-lessons",
            "hardware-lab/lab-failure-analysis",
            "hardware-lab/lab-inventory",
            "hardware-lab/lab-procurement-advice",
            "hardware-lab/lab-receiving",
            "hardware-lab/lab-worklog",
        }
    ),
}


@dataclass(frozen=True)
class SkillPruneResult:
    agent_id: str
    profile_home: str
    quarantine_home: str
    kept_skills: tuple[str, ...]
    removed_skills: tuple[str, ...]
    moved_roots: tuple[str, ...]
    applied: bool


def write_quarantine_manifest(quarantine_root: Path) -> Path:
    quarantine_root = quarantine_root.resolve()
    if not quarantine_root.is_dir():
        raise ValueError("Quarantine directory does not exist.")

    manifest_path = quarantine_root / "manifest.json"
    records: list[dict[str, int | str]] = []
    for path in sorted(quarantine_root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path == manifest_path:
            continue
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        records.append(
            {
                "path": path.relative_to(quarantine_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            }
        )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "quarantine_root": str(quarantine_root),
        "file_count": len(records),
        "files": records,
    }
    temporary_path = quarantine_root / "manifest.json.tmp"
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary_path.replace(manifest_path)
    return manifest_path


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _discover_skill_paths(skills_root: Path) -> set[PurePosixPath]:
    return {
        PurePosixPath(skill_file.parent.relative_to(skills_root).as_posix())
        for skill_file in skills_root.rglob("SKILL.md")
        if skill_file.is_file()
    }


def _minimal_move_roots(
    unknown: set[PurePosixPath], allowed: set[PurePosixPath]
) -> set[PurePosixPath]:
    roots: set[PurePosixPath] = set()
    for skill_path in unknown:
        for depth in range(1, len(skill_path.parts) + 1):
            candidate = PurePosixPath(*skill_path.parts[:depth])
            contains_allowed = any(
                allowed_path.parts[:depth] == candidate.parts
                for allowed_path in allowed
                if len(allowed_path.parts) >= depth
            )
            if not contains_allowed:
                roots.add(candidate)
                break
    return {
        candidate
        for candidate in roots
        if not any(
            other != candidate
            and len(other.parts) < len(candidate.parts)
            and candidate.parts[: len(other.parts)] == other.parts
            for other in roots
        )
    }


def prune_specialist_skills(
    profile_home: Path,
    agent_id: str,
    quarantine_root: Path,
    *,
    apply: bool = False,
) -> SkillPruneResult:
    if agent_id not in SPECIALIST_SKILL_ALLOWLISTS:
        raise ValueError(f"Unsupported specialist profile: {agent_id}")

    profile_home = profile_home.resolve()
    skills_root = (profile_home / "skills").resolve()
    quarantine_root = quarantine_root.resolve()
    if profile_home.name.casefold() != agent_id.casefold():
        raise ValueError("Profile directory name must match the specialist identity.")
    if not skills_root.is_dir() or not _is_within(skills_root, profile_home):
        raise ValueError("The specialist skills directory does not exist inside the profile.")
    if _is_within(quarantine_root, profile_home):
        raise ValueError("Quarantine must be outside the live specialist profile.")

    allowed = {PurePosixPath(path) for path in SPECIALIST_SKILL_ALLOWLISTS[agent_id]}
    discovered = _discover_skill_paths(skills_root)
    kept = discovered & allowed
    unknown = discovered - allowed
    move_roots = _minimal_move_roots(unknown, allowed)

    moves: list[tuple[Path, Path]] = []
    for relative in sorted(move_roots, key=str):
        source = (skills_root / Path(*relative.parts)).resolve()
        destination = quarantine_root / agent_id / Path(*relative.parts)
        if not source.exists() or not _is_within(source, skills_root):
            raise ValueError(f"Unsafe or missing skill source: {source}")
        if destination.exists():
            raise FileExistsError(f"Quarantine destination already exists: {destination}")
        moves.append((source, destination))

    if apply:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))

    return SkillPruneResult(
        agent_id=agent_id,
        profile_home=str(profile_home),
        quarantine_home=str(quarantine_root),
        kept_skills=tuple(sorted(map(str, kept))),
        removed_skills=tuple(sorted(map(str, unknown))),
        moved_roots=tuple(sorted(map(str, move_roots))),
        applied=apply,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prune a Hermes specialist profile to its reviewed skill allowlist."
    )
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--agent-id", choices=sorted(SPECIALIST_SKILL_ALLOWLISTS), required=True)
    parser.add_argument("--quarantine-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = prune_specialist_skills(
        args.profile_home,
        args.agent_id,
        args.quarantine_root,
        apply=args.apply,
    )
    output = asdict(result)
    if args.write_manifest:
        output["manifest_path"] = str(write_quarantine_manifest(args.quarantine_root))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
