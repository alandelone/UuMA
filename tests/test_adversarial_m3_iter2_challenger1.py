"""Adversarial stress-test suite for Milestone 3 Iteration 2 (Finding F06 & Audit Item W29).

Challenger: challenger_m3_iter2_1
Target: Delivery Archive Packaging & Strict Verifier Gate

Verification Scope:
1. Member stripping: Removing ANY of the 11 REQUIRED_MEMBERS from packet.tar.gz causes verify_delivery_archive() to fail closed (AssertionError).
2. Member injection: Adding unexpected files into packet.tar.gz causes verify_delivery_archive() to fail closed (AssertionError).
3. Manifest divergence: Modifying manifest.json entries, hashes, or versions causes verify_delivery_archive() to fail closed.
4. Verifier receipt tampering: Modifying verifier_receipt.json assertions causes verify_delivery_archive() to fail closed.
"""
from __future__ import annotations

import json
import shutil
import sys
import tarfile
from pathlib import Path

import pytest

# Ensure repository paths in sys.path
repo_root = Path(__file__).resolve().parents[1]
rstv4_root = repo_root.parent / "RSTV4"
uuma_local = repo_root / ".uuma-local" / "scholar-catalog-implementation-20261023"

for p in (repo_root / "src", rstv4_root / "src", uuma_local):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from package_scholar_delivery_archive import (
    REQUIRED_MEMBERS,
    TARGET_ARCHIVE_20261106,
    sha256_file,
    verify_delivery_archive,
)


@pytest.fixture
def fresh_archive(tmp_path: Path):
    """Provides a fresh, hermetic scratch copy of the verified 20261106 delivery archive."""
    scratch = tmp_path / "delivery-archive-test"
    shutil.copytree(TARGET_ARCHIVE_20261106, scratch)
    return scratch


def repackage_tarball(archive_dir: Path, exclude: set[str] | None = None, extra_files: dict[str, bytes] | None = None) -> None:
    """Helper to repackage packet.tar.gz with exclusions or injected files."""
    exclude = exclude or set()
    extra_files = extra_files or {}
    tar_path = archive_dir / "packet.tar.gz"
    tar_path.unlink()

    with tarfile.open(tar_path, "w:gz") as tar:
        for f in sorted(archive_dir.iterdir()):
            if f.name in ("packet.tar.gz", "manifest.json") or f.name in exclude:
                continue
            tar.add(f, arcname=f.name)
        for extra_name, content in extra_files.items():
            import io
            ti = tarfile.TarInfo(name=extra_name)
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))


# ==============================================================================
# 1. Member Stripping Stress Tests (All 11 REQUIRED_MEMBERS)
# ==============================================================================

@pytest.mark.parametrize("stripped_member", sorted(REQUIRED_MEMBERS))
def test_member_stripping_from_tarball_only_fails_closed(fresh_archive: Path, stripped_member: str):
    """Stripping member from packet.tar.gz only while manifest expects it MUST raise AssertionError."""
    repackage_tarball(fresh_archive, exclude={stripped_member})

    # Update only packet hash in manifest
    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    manifest["packet_sha256"] = sha256_file(fresh_archive / "packet.tar.gz")
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError) as exc_info:
        verify_delivery_archive(fresh_archive)
    assert any(
        msg in str(exc_info.value)
        for msg in [
            "Expected exactly 11 archive members",
            "Archive packet member mismatch",
            "missing or unverified from packet.tar.gz",
            "Archive packet does NOT include",
        ]
    )


@pytest.mark.parametrize("stripped_member", sorted(REQUIRED_MEMBERS))
def test_member_stripping_from_both_tarball_and_manifest_fails_closed(fresh_archive: Path, stripped_member: str):
    """Stripping member from BOTH tarball, outer directory, and manifest MUST raise AssertionError."""
    (fresh_archive / stripped_member).unlink()
    repackage_tarball(fresh_archive, exclude={stripped_member})

    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    if stripped_member in manifest["files"]:
        del manifest["files"][stripped_member]
    manifest["packet_sha256"] = sha256_file(fresh_archive / "packet.tar.gz")
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError) as exc_info:
        verify_delivery_archive(fresh_archive)
    assert any(
        msg in str(exc_info.value)
        for msg in [
            "missing from outer manifest",
            "Missing expected outer file",
            "Manifest files set mismatch",
            "Expected exactly 11 archive members",
            "Archive packet member mismatch",
        ]
    )


# ==============================================================================
# 2. Member Injection Stress Tests
# ==============================================================================

def test_member_injection_unexpected_file_in_tarball_not_in_manifest(fresh_archive: Path):
    """Injecting an unexpected extra file into packet.tar.gz without outer manifest entry fails closed."""
    repackage_tarball(fresh_archive, extra_files={"injected_exploit.py": b"print('compromised')"})

    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    manifest["packet_sha256"] = sha256_file(fresh_archive / "packet.tar.gz")
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Member injected_exploit.py not recorded in manifest"):
        verify_delivery_archive(fresh_archive)


def test_member_injection_unexpected_file_in_tarball_and_manifest(fresh_archive: Path):
    """Injecting an extra file into packet.tar.gz and outer manifest (len=12) fails closed."""
    injected_bytes = b"print('compromised')"
    injected_hash = "6df3c0897b69bb37d3632cfb7fa1f0c2a7f0e340a6ab0c704f0b2f56ceb9201a"
    (fresh_archive / "injected_exploit.py").write_bytes(injected_bytes)
    repackage_tarball(fresh_archive)

    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    manifest["files"]["injected_exploit.py"] = injected_hash
    manifest["packet_sha256"] = sha256_file(fresh_archive / "packet.tar.gz")
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError) as exc_info:
        verify_delivery_archive(fresh_archive)
    assert "Manifest files set mismatch" in str(exc_info.value) or "Expected exactly 11 archive members" in str(exc_info.value)


# ==============================================================================
# 3. Manifest Divergence Stress Tests
# ==============================================================================

@pytest.mark.parametrize("target_member", sorted(REQUIRED_MEMBERS))
def test_manifest_file_hash_tampering_fails_closed(fresh_archive: Path, target_member: str):
    """Tampering with any file hash recorded in manifest['files'] fails closed."""
    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    orig_hash = manifest["files"][target_member]
    tampered_hash = ("0" if orig_hash[0] != "0" else "1") + orig_hash[1:]
    manifest["files"][target_member] = tampered_hash
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match=f"Hash mismatch for {target_member}"):
        verify_delivery_archive(fresh_archive)


def test_manifest_packet_sha256_tampering_fails_closed(fresh_archive: Path):
    """Tampering with manifest packet_sha256 fails closed."""
    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    orig_hash = manifest["packet_sha256"]
    manifest["packet_sha256"] = ("f" if orig_hash[0] != "f" else "e") + orig_hash[1:]
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Outer manifest packet_sha256 mismatch"):
        verify_delivery_archive(fresh_archive)


def test_manifest_version_tampering_fails_closed(fresh_archive: Path):
    """Tampering with manifest version string fails closed."""
    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    manifest["version"] = "scholar-catalog-delivery-archive-v999"
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Manifest version mismatch"):
        verify_delivery_archive(fresh_archive)


def test_manifest_paper_id_tampering_fails_closed(fresh_archive: Path):
    """Tampering with manifest paper_id fails closed."""
    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    manifest["paper_id"] = "paper_spoofed_00000000000000000000000000000000"
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Manifest paper_id mismatch"):
        verify_delivery_archive(fresh_archive)


def test_manifest_extra_phantom_file_fails_closed(fresh_archive: Path):
    """Adding a phantom file to manifest['files'] fails closed."""
    manifest = json.loads((fresh_archive / "manifest.json").read_bytes())
    manifest["files"]["phantom_evidence.dat"] = "0" * 64
    (fresh_archive / "manifest.json").write_text(json.dumps(manifest, indent=2))

    with pytest.raises(AssertionError, match="Manifest files set mismatch"):
        verify_delivery_archive(fresh_archive)


# ==============================================================================
# 4. Verifier Receipt Tampering Stress Tests
# ==============================================================================

def update_receipt_in_archive(archive_dir: Path, mutator_fn) -> None:
    """Helper to mutate verifier_receipt.json, repackage tarball, and update manifest hash."""
    receipt_file = archive_dir / "verifier_receipt.json"
    receipt = json.loads(receipt_file.read_bytes())
    mutator_fn(receipt)
    receipt_file.write_text(json.dumps(receipt, indent=2))

    repackage_tarball(archive_dir)
    manifest = json.loads((archive_dir / "manifest.json").read_bytes())
    manifest["files"]["verifier_receipt.json"] = sha256_file(receipt_file)
    manifest["packet_sha256"] = sha256_file(archive_dir / "packet.tar.gz")
    manifest["files"]["packet.tar.gz"] = manifest["packet_sha256"]
    (archive_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def test_verifier_receipt_tampered_status_fails_closed(fresh_archive: Path):
    """Tampering verifier_receipt.json verifier_status to TAMPERED fails closed."""
    def mutate(r):
        r["verifier_status"] = "TAMPERED"

    update_receipt_in_archive(fresh_archive, mutate)

    with pytest.raises(AssertionError, match="Verifier receipt status is not VERIFIED"):
        verify_delivery_archive(fresh_archive)


def test_verifier_receipt_tampered_total_members_fails_closed(fresh_archive: Path):
    """Tampering verifier_receipt.json total_members to 10 fails closed."""
    def mutate(r):
        r["integrity_assertions"]["total_members"] = 10

    update_receipt_in_archive(fresh_archive, mutate)

    with pytest.raises(AssertionError, match=r"Verifier receipt total_members != 11, got 10"):
        verify_delivery_archive(fresh_archive)


def test_verifier_receipt_foreign_key_violations_fails_closed(fresh_archive: Path):
    """Tampering verifier_receipt.json foreign_key_violations to 1 fails closed."""
    def mutate(r):
        r["integrity_assertions"]["foreign_key_violations"] = 1

    update_receipt_in_archive(fresh_archive, mutate)

    with pytest.raises(AssertionError, match=r"Verifier receipt foreign_key_violations != 0: 1"):
        verify_delivery_archive(fresh_archive)


def test_verifier_receipt_integrity_check_failure_fails_closed(fresh_archive: Path):
    """Tampering verifier_receipt.json database_integrity_check to corrupt fails closed."""
    def mutate(r):
        r["integrity_assertions"]["database_integrity_check"] = "corrupt"

    update_receipt_in_archive(fresh_archive, mutate)

    with pytest.raises(AssertionError, match=r"Verifier receipt database_integrity_check != ok: corrupt"):
        verify_delivery_archive(fresh_archive)


def test_verifier_receipt_paper_id_mismatch_fails_closed(fresh_archive: Path):
    """Tampering verifier_receipt.json paper_id fails closed."""
    def mutate(r):
        r["paper_id"] = "paper_forged_receipt_id"

    update_receipt_in_archive(fresh_archive, mutate)

    with pytest.raises(AssertionError, match="Verifier receipt paper_id mismatch"):
        verify_delivery_archive(fresh_archive)
