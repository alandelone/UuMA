import json
import os
import subprocess
from pathlib import Path

import pytest


def test_real_hermes_plugin_stdio_and_delivery_queue_in_two_isolated_profiles(tmp_path):
    root = Path(__file__).resolve().parents[1]
    hermes = Path(
        os.environ.get(
            "HERMES_AGENT_ROOT", Path(os.environ.get("LOCALAPPDATA", "")) / "hermes/hermes-agent"
        )
    )
    native_python = hermes / "venv/Scripts/python.exe"
    if not native_python.is_file():
        pytest.skip("Native Hermes installation is required for this optional integration check")
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
        }
    }
    env.update(
        {
            "PYTHONPATH": os.pathsep.join((str(hermes), str(root / "src"))),
            "HERMES_HOME": str(tmp_path / "A/profiles/honc"),
            "PYTHONUTF8": "1",
        }
    )
    result = subprocess.run(
        [
            str(native_python),
            "-X",
            "utf8",
            str(root / "test-fixtures/honc/native_life_probe.py"),
            str(root),
            str(tmp_path),
            str(root / ".venv/Scripts/python.exe"),
        ],
        env=env,
        cwd=hermes,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-8000:] + result.stdout[-3000:]
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt["result"] == "PASS" and receipt["profile_sequence"] == ["A", "B", "A"]
    assert receipt["actual_stdio_tools"] == 20 and receipt["native_queue_sends"] == 1
    assert receipt["native_scheduler_groups"] == 1
    assert receipt["real_notifications_sent"] == receipt["real_model_calls"] == 0
