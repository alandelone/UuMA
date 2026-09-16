from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from .gemini_worker import GeminiTask, GeminiWorker, GeminiWorkerSettings

mcp = FastMCP("gemini-worker")


@lru_cache(maxsize=1)
def _worker() -> GeminiWorker:
    return GeminiWorker(GeminiWorkerSettings.from_env())


@mcp.tool()
def delegate_to_gemini(
    task: str,
    working_directory: str,
    context: list[str],
    constraints: list[str],
    expected_output: str,
    done_when: str,
) -> dict[str, Any]:
    """Delegate one bounded, stateless task to Gemini CLI within an allowlisted directory."""
    package = GeminiTask(
        task=task,
        working_directory=working_directory,
        context=context,
        constraints=constraints,
        expected_output=expected_output,
        done_when=done_when,
    )
    return _worker().run(package, os.environ.get("UUMA_AGENT_ID", "").strip())


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
