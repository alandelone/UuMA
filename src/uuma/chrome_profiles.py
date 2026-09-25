"""Discover and open ordinary Chrome profiles without reading browser credentials."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


def chrome_user_data() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"


def chrome_profiles(user_data: Path | None = None) -> list[dict[str, str]]:
    root = user_data or chrome_user_data()
    try:
        state = json.loads((root / "Local State").read_text(encoding="utf-8"))
        cache = state.get("profile", {}).get("info_cache", {})
    except (OSError, ValueError, TypeError):
        return []
    profiles = []
    for directory, details in cache.items():
        if not re.fullmatch(r"Default|Profile \d+", directory) or not isinstance(details, dict):
            continue
        profiles.append({
            "directory": directory,
            "name": str(details.get("name") or directory),
            "email": str(details.get("user_name") or ""),
        })
    return sorted(
        profiles,
        key=lambda item: (item["directory"] != "Default", item["directory"]),
    )


def validate_chrome_profile(directory: str, user_data: Path | None = None) -> str:
    available = {profile["directory"] for profile in chrome_profiles(user_data)}
    if directory not in available:
        raise ValueError("Choose an available Chrome profile from the dashboard.")
    return directory


def chrome_executable() -> Path:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" /
        "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" /
        "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" /
        "chrome.exe",
    ]
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        raise RuntimeError("Google Chrome is not installed in a standard location.")
    return executable


def open_chrome_profile(directory: str, url: str = "https://chatgpt.com/") -> None:
    profile = validate_chrome_profile(directory)
    subprocess.Popen(
        [str(chrome_executable()), f"--profile-directory={profile}", url],
        close_fds=True,
    )
