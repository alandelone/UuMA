import os
import subprocess
from pathlib import Path


def test_native_idle_and_queued_voice_records_preserve_source_and_receipt(tmp_path):
    root = Path(__file__).resolve().parents[1]
    hermes = Path(os.environ["LOCALAPPDATA"]) / "hermes/hermes-agent"
    environment = dict(os.environ, PYTHONPATH=str(hermes), PYTHONUTF8="1")
    result = subprocess.run(
        [
            str(hermes / "venv/Scripts/python.exe"),
            "-X",
            "utf8",
            str(root / "test-fixtures/honc/voice_inbound_probe.py"),
            str(root),
            str(tmp_path),
        ],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-7000:] + result.stdout[-2000:]
    assert '"idle_and_queued_saved": 2' in result.stdout
