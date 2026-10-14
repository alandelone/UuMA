from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


class CommandPdfAdapter:
    """Optional isolated adapter configured as argv JSON; no shell or interactive bypass."""

    def __init__(self, name: str, environment_key: str) -> None:
        self.name = name
        self.environment_key = environment_key

    def acquire(self, doi: str, output: Path, *, timeout_seconds: int = 600) -> Path | None:
        raw = os.environ.get(self.environment_key)
        if not raw:
            return None
        argv = json.loads(raw)
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
            raise ValueError(f"{self.environment_key} must be a JSON array of argv strings")
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [arg.replace("{doi}", doi).replace("{output}", str(output)) for arg in argv]
        process = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds, check=False
        )
        if process.returncode != 0:
            raise RuntimeError(f"{self.name} failed: {(process.stderr or process.stdout)[-4000:]}")
        return output if output.is_file() else None


FALLBACK_ADAPTERS = (
    CommandPdfAdapter("SciDownl", "RSTV4_SCIDOWNL_ARGV"),
    CommandPdfAdapter("scihub.py", "RSTV4_SCIHUB_ARGV"),
)
