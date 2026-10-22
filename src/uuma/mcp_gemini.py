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
    """Run a bounded stateless task with the configured worker backend.

    Server profiles may use the shared account pool in plan mode. The requesting
    Agent retains responsibility for scope, decisions and reviewing the result.
    """
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
