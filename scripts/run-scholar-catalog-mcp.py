"""Admit the fixed Catalog release before starting Scholar's stdio MCP child."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def resolve_runtime(project_root: Path, data_root: Path, manifest: Path) -> dict[str, Any]:
    resolver = project_root / "scripts" / "resolve-scholar-catalog-runtime.ps1"
    result = subprocess.run(
        [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(resolver),
            "-ManifestPath", str(manifest), "-ExpectedDataRoot", str(data_root),
            "-ProjectRoot", str(project_root),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError("Fixed Catalog admission failed: " + result.stderr[-2000:].strip())
    runtime = json.loads(result.stdout)
    if runtime.get("kind") != "FIXED_RELEASE" or runtime.get("service_started") is not False:
        raise ValueError("Catalog admission did not return an unstarted fixed release")
    return runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    project_root = args.project_root.resolve(strict=True)
    runtime = resolve_runtime(
        project_root, args.data_root.resolve(strict=True), args.manifest.resolve(strict=True)
    )
    if args.check_only:
        print(json.dumps({**runtime, "mcp_started": False, "global_tools_on_start": True}))
        return 0
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=os.pathsep.join([str(Path(runtime["engine_root"]) / "src"),
                                  str(project_root / "src")]),
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        PYTHONDONTWRITEBYTECODE="1",
        RSTV4_ROOT=runtime["data_root"],
        RSTV4_PYTHON=runtime["python"],
        RSTV4_ENGINE_ROOT=runtime["parser_engine_root"],
        RSTV4_RESOURCE_ROOT=runtime["resource_root"],
        RSTV4_MINERU_PYTHON=runtime["mineru_python"],
        RSTV4_CATALOG_GLOBAL_TOOLS="1",
    )
    # Keep all three streams as binary handles. Admission diagnostics are captured
    # above; only the actual MCP child writes the protocol stream.
    bootstrap = (
        "import os; from mcp.server.fastmcp import FastMCP; "
        "from rstv4.catalog_runtime import require_owner; "
        "from rstv4.catalog_mcp import register_catalog_tools; "
        "root=os.environ['RSTV4_ROOT']; require_owner(root); "
        "server=FastMCP('scholar-catalog'); "
        "register_catalog_tools(server, lambda: root); server.run()"
    )
    result = subprocess.run(
        [runtime["python"], "-c", bootstrap],
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=sys.stderr.buffer,
        env=environment,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
