from __future__ import annotations

from pathlib import Path

import pytest

from uuma.specialist_skills import prune_specialist_skills, write_quarantine_manifest


def _skill(root: Path, relative: str) -> Path:
    skill = root.joinpath("skills", *relative.split("/"), "SKILL.md")
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(f"# {relative}\n", encoding="utf-8")
    return skill


def test_dry_run_preserves_profile_and_reports_grouped_move_roots(tmp_path: Path) -> None:
    profile = tmp_path / "brainstormer"
    _skill(profile, "discussion-state")
    _skill(profile, "autonomous-ai-agents/codex")
    _skill(profile, "autonomous-ai-agents/computer-use")

    result = prune_specialist_skills(profile, "brainstormer", tmp_path / "quarantine")

    assert result.kept_skills == ("discussion-state",)
    assert result.removed_skills == (
        "autonomous-ai-agents/codex",
        "autonomous-ai-agents/computer-use",
    )
    assert result.moved_roots == ("autonomous-ai-agents",)
    assert not result.applied
    assert (profile / "skills/autonomous-ai-agents/codex/SKILL.md").is_file()


def test_apply_moves_unapproved_skills_and_preserves_forge_allowlist(tmp_path: Path) -> None:
    profile = tmp_path / "forge-lab-bot"
    _skill(profile, "hardware-lab/lab-inventory")
    _skill(profile, "hardware-lab/unreviewed-driver")
    _skill(profile, "software-development/systematic-debugging")
    quarantine = tmp_path / "quarantine"

    result = prune_specialist_skills(
        profile,
        "forge-lab-bot",
        quarantine,
        apply=True,
    )

    assert result.applied
    assert (profile / "skills/hardware-lab/lab-inventory/SKILL.md").is_file()
    assert not (profile / "skills/hardware-lab/unreviewed-driver").exists()
    assert not (profile / "skills/software-development").exists()
    assert (
        quarantine / "forge-lab-bot/hardware-lab/unreviewed-driver/SKILL.md"
    ).is_file()
    assert (
        quarantine / "forge-lab-bot/software-development/systematic-debugging/SKILL.md"
    ).is_file()


def test_rejects_quarantine_inside_live_profile(tmp_path: Path) -> None:
    profile = tmp_path / "wisdom-oldman"
    _skill(profile, "wisdom-answer")

    with pytest.raises(ValueError, match="outside"):
        prune_specialist_skills(
            profile,
            "wisdom-oldman",
            profile / "quarantine",
            apply=True,
        )


def test_rejects_profile_identity_mismatch(tmp_path: Path) -> None:
    profile = tmp_path / "not-brainstormer"
    _skill(profile, "discussion-state")

    with pytest.raises(ValueError, match="match"):
        prune_specialist_skills(profile, "brainstormer", tmp_path / "quarantine")


def test_quarantine_manifest_records_file_hashes(tmp_path: Path) -> None:
    quarantine = tmp_path / "quarantine"
    skill_file = quarantine / "brainstormer/obsolete/SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("obsolete skill\n", encoding="utf-8")

    manifest = write_quarantine_manifest(quarantine)

    contents = manifest.read_text(encoding="utf-8")
    assert '"file_count": 1' in contents
    assert '"path": "brainstormer/obsolete/SKILL.md"' in contents
    assert '"sha256":' in contents
