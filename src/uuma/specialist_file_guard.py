"""Opt-in file-tool read roots; this is not operating-system isolation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FILE_READ_TOOLS = {"read_file", "search_files"}


def file_read_decision(profile: str, tool_name: str, args: Any, policy: str) -> dict | None:
    """Fail closed on ambiguous paths and keep native credential denies intact.

    Native search may recover a nonexistent path by splitting commas/spaces into
    multiple roots. Requiring one existing absolute path prevents that fallback
    from changing the path admitted here. Relative paths are deliberately denied:
    the gateway task cwd can differ from this hook's process cwd.
    """
    if tool_name not in FILE_READ_TOOLS:
        return None
    denied = {
        "action": "block",
        "message": (
            "Specialist file access requires one existing absolute path inside this Agent's "
            "configured file roots. Credential files and other Agent data are not available."
        ),
    }
    try:
        mapping = json.loads(policy)
        if not isinstance(mapping, dict) or not mapping:
            return denied
        roots_by_profile = {}
        for identity, values in mapping.items():
            if (not isinstance(identity, str) or not isinstance(values, list) or not values
                    or any(not isinstance(value, str) or not value for value in values)):
                return denied
            roots = []
            for value in values:
                if value.startswith(("//", "\\\\")):
                    return denied
                root = Path(value)
                if not root.is_absolute():
                    return denied
                root = root.resolve(strict=True)
                if not root.is_dir() or root == Path(root.anchor):
                    return denied
                roots.append(root)
            roots_by_profile[identity] = roots
        roots = roots_by_profile.get(profile)
        if not roots or not isinstance(args, dict):
            return denied
        value = args.get("path")
        if not isinstance(value, str) or not value or value.startswith(("//", "\\\\")):
            return denied
        target = Path(value)
        if not target.is_absolute():
            return denied
        target = target.resolve(strict=True)
        if not any(target.is_relative_to(root) for root in roots):
            return denied
        # Native read_file/search_files still run their own file_safety denylist.
        # Do not allow these especially sensitive names even in a profile root.
        if target.name.lower() in {
            "auth.json", "auth.lock", ".anthropic_oauth.json", ".env", ".env.local",
            ".env.development", ".env.production", ".env.test", ".env.staging", ".envrc",
        }:
            return denied
    except (ValueError, TypeError, OSError, RuntimeError):
        return denied
    return None
