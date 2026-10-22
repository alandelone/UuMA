import json
import subprocess
import zipfile

import pytest

from uuma.source_snapshot import snapshot


def test_snapshot_preserves_local_engine_edits_and_excludes_state(tmp_path):
    root = tmp_path / "engine"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "engine.py").write_text("original")
    (root / "deleted.py").write_text("old")
    subprocess.run(["git", "-C", str(root), "add", "engine.py", "deleted.py"], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Fixture", "-c",
        "user.email=fixture@example.invalid", "commit", "-m", "baseline",
    ], check=True, capture_output=True)
    (root / "engine.py").write_text("local improvement")
    (root / "deleted.py").unlink()
    (root / "new.py").write_text("new implementation")
    (root / ".env").write_text("SECRET=private")
    (root / "state.db").write_bytes(b"private")
    (root / "data").mkdir()
    (root / "data/private.txt").write_text("private")
    report = snapshot(root, tmp_path / "snapshots", ["."], engine="fixture")
    with zipfile.ZipFile(report["archive"]) as z:
        assert z.read("engine.py") == b"local improvement"
        assert "new.py" in z.namelist()
        assert set(z.namelist()) == {"engine.py", "new.py", "engine-source-receipt.json"}
        receipt = json.loads(z.read("engine-source-receipt.json"))
        assert receipt["runtime_state_included"] is False
        assert receipt["working_tree_edits_preserved"] is True


def test_snapshot_requires_repository_relative_scope(tmp_path):
    with pytest.raises(ValueError):
        snapshot(tmp_path, tmp_path / "out", ["../credentials"], engine="fixture")


def test_hermes_snapshot_requires_all_declared_runtime_packages(tmp_path):
    root = tmp_path / "engine"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "pyproject.toml").write_text(
        '[tool.setuptools.packages.find]\ninclude = ["gateway", "tui_gateway"]\n'
    )
    for name in ("gateway", "tui_gateway"):
        (root / name).mkdir()
        (root / name / "__init__.py").write_text("# source\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(root), "-c", "user.name=Fixture", "-c",
        "user.email=fixture@example.invalid", "commit", "-m", "baseline",
    ], check=True, capture_output=True)
    output = tmp_path / "snapshots"
    with pytest.raises(ValueError, match="tui_gateway"):
        snapshot(root, output, ["pyproject.toml", "gateway"], engine="hermes")
    assert not output.exists()
    report = snapshot(root, output, ["pyproject.toml", "gateway", "tui_gateway"], engine="hermes")
    with zipfile.ZipFile(report["archive"]) as archive:
        assert "tui_gateway/__init__.py" in archive.namelist()
