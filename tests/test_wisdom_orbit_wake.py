"""Platform-specific process launch contracts; never starts research or a model."""

from types import SimpleNamespace

import pytest

from uuma import mcp_knowledge as knowledge


def configure(monkeypatch, tmp_path, *, platform="posix", profile=True):
    profile_home = tmp_path / "profiles" / "wisdom-oldman"
    environment = {
        "UUMA_AGENT_ID": "wisdom-oldman",
        "UUMA_DATA_DIR": str(tmp_path / "control"),
        "UUMA_IDENTITY_TOKEN_FILE": str(tmp_path / "identity.token"),
        "PYTHONPATH": "existing-source",
    }
    if profile:
        environment["UUMA_QUESTION_ORBIT_PROFILE_HOME"] = str(profile_home)
    monkeypatch.setattr(
        knowledge, "os", SimpleNamespace(name=platform, environ=environment, pathsep=";")
    )
    executable = tmp_path / "bin" / "python"
    monkeypatch.setattr(knowledge, "sys", SimpleNamespace(executable=str(executable)))
    database = tmp_path / "knowledge" / "wisdom.db"
    monkeypatch.setattr(
        knowledge,
        "Settings",
        SimpleNamespace(
            from_env=lambda: SimpleNamespace(knowledge_database_path=lambda: database)
        ),
    )
    calls = []

    def launch(arguments, **options):
        calls.append((arguments, options))
        return SimpleNamespace(pid=12345)

    monkeypatch.setattr(knowledge.subprocess, "Popen", launch)
    return profile_home, executable, database, calls, environment


def test_linux_queued_orbit_launches_detached_with_its_configured_profile(monkeypatch, tmp_path):
    home, executable, database, calls, environment = configure(monkeypatch, tmp_path)

    assert knowledge._wake_orbit_runner("QUEUED") == {
        "requested": True, "method": "detached_process", "pid": 12345
    }

    arguments, options = calls[0]
    assert arguments == [
        str(executable), "-m", "uuma.orbit_runner", "--profile-home", str(home.resolve())
    ]
    assert options["start_new_session"] is True
    assert "creationflags" not in options
    assert options["close_fds"] is True
    for stream in ["stdin", "stdout", "stderr"]:
        assert options[stream] == knowledge.subprocess.DEVNULL
    assert options["env"]["UUMA_DATA_DIR"] == str(database.parent)
    assert options["env"]["UUMA_AGENT_ID"] == "wisdom-oldman"
    assert options["env"]["UUMA_IDENTITY_TOKEN_FILE"] == environment["UUMA_IDENTITY_TOKEN_FILE"]
    assert options["env"]["PYTHONPATH"].endswith(";existing-source")
    assert environment["UUMA_DATA_DIR"] == str(tmp_path / "control")


@pytest.mark.parametrize("status", ["PAUSED", "RUNNING", "COMPLETE", "FAILED", ""])
def test_nonqueued_orbit_does_not_launch_or_resume(monkeypatch, tmp_path, status):
    *_, calls, _environment = configure(monkeypatch, tmp_path)

    assert knowledge._wake_orbit_runner(status) == {"requested": False}
    assert calls == []


def test_linux_without_configured_profile_does_not_guess_profile_or_run_windows_task(
    monkeypatch, tmp_path
):
    *_, calls, environment = configure(monkeypatch, tmp_path, profile=False)
    environment["UUMA_QUESTION_ORBIT_WAKE_TASK"] = "Windows-only wake task"
    monkeypatch.setattr(
        knowledge.subprocess, "run", lambda *args, **kwargs: pytest.fail("Windows task invoked")
    )

    result = knowledge._wake_orbit_runner("QUEUED")

    assert result["requested"] is False
    assert calls == []


def test_linux_launch_failure_does_not_retry_or_run_windows_task(monkeypatch, tmp_path):
    *_unused, environment = configure(monkeypatch, tmp_path)
    environment["UUMA_QUESTION_ORBIT_WAKE_TASK"] = "Windows-only wake task"
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(args)
        raise OSError("Unavailable configured interpreter")

    monkeypatch.setattr(knowledge.subprocess, "Popen", fail)
    monkeypatch.setattr(
        knowledge.subprocess, "run", lambda *args, **kwargs: pytest.fail("Windows task invoked")
    )

    assert knowledge._wake_orbit_runner("QUEUED")["requested"] is False
    assert len(attempts) == 1


def test_windows_keeps_pythonw_hidden_detached_launch(monkeypatch, tmp_path):
    _home, executable, _database, calls, _environment = configure(
        monkeypatch, tmp_path, platform="nt"
    )
    executable.parent.mkdir()
    pythonw = executable.with_name("pythonw.exe")
    pythonw.write_bytes(b"not an executable; Popen is mocked")
    monkeypatch.setattr(knowledge.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(knowledge.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)

    assert knowledge._wake_orbit_runner("QUEUED")["requested"] is True

    arguments, options = calls[0]
    assert arguments[0] == str(pythonw)
    assert options["creationflags"] == 0x08000008
    assert "start_new_session" not in options


def test_windows_keeps_scheduled_task_fallback_after_launch_failure(monkeypatch, tmp_path):
    *_unused, environment = configure(monkeypatch, tmp_path, platform="nt")
    environment["UUMA_QUESTION_ORBIT_WAKE_TASK"] = "ExistingOrbitWake"

    def fail(*args, **kwargs):
        raise OSError("Unavailable interpreter")

    calls = []

    def run(arguments, **options):
        calls.append((arguments, options))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(knowledge.subprocess, "Popen", fail)
    monkeypatch.setattr(knowledge.subprocess, "run", run)

    assert knowledge._wake_orbit_runner("QUEUED") == {"requested": True}
    assert calls[0][0] == ["schtasks.exe", "/run", "/tn", "ExistingOrbitWake"]
    assert calls[0][1]["timeout"] == 15
