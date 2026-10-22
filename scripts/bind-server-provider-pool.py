"""Bind a separate Linux profile candidate to the node-local account pool.

Only the provider transport changes; role definitions and MCP tool filters are untouched.
Run on a credential-free candidate copy, never the workstation's live profiles.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


def inject(source: str, function: str, body: str) -> str:
    tree = ast.parse(source)
    node = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == function)
    first = node.body[0]
    position = (
        first.end_lineno if isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
        else first.lineno - 1
    )
    lines = source.splitlines(keepends=True)
    lines.insert(position, body)
    result = "".join(lines)
    ast.parse(result)
    return result


def bind(profile: Path) -> dict:
    if (profile / ".env").exists() or (profile / "auth.json").exists():
        raise ValueError("Bind a credential-free profile candidate")
    plugin = profile / "plugins" / "antigravity-oauth"
    patches = {
        "process.py": [("resolve_real_token_path", (
            '    if os.getenv("UUMA_AGY_POOL_ROOT"):\n'
            '        from uuma_provider_pool import AccountPool\n'
            '        return AccountPool(Path(os.environ["UUMA_AGY_POOL_ROOT"])).authentication_token()\n'
          ))],
        "account_pool.py": [
            ("rotate_on_quota_error", (
             '    if os.getenv("UUMA_AGY_POOL_ROOT"):\n'
             '        return None  # Node pool owns cooldown; never replay an Agent turn.\n')),
            ("maybe_restore_primary_account", (
             '    if os.getenv("UUMA_AGY_POOL_ROOT"):\n'
             '        return False  # No machine-wide identity switching on the server.\n')),
        ],
        "auth.py": [("_run_login", (
            '    if os.getenv("UUMA_AGY_POOL_ROOT"):\n'
            '        raise RuntimeError("Use the server account-pool operator login")\n'
          ))],
    }
    receipt = {"schema_version": 1, "files": {}, "production_active": False}
    replacements = {}
    for name, functions in patches.items():
        path = plugin / name
        source = path.read_text(encoding="utf-8")
        if "UUMA_AGY_POOL_ROOT" in source:
            raise ValueError("Profile is already bound; create a new release candidate")
        result = source
        if name == "auth.py":
            # This plugin version does not otherwise import os.
            result = result.replace("from __future__ import annotations\n",
                                    "from __future__ import annotations\n\nimport os\n", 1)
        for function, body in functions:
            result = inject(result, function, body)
        replacements[path] = result
        receipt["files"][name] = {
            "before_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "after_sha256": hashlib.sha256(result.encode()).hexdigest(),
        }
    client_path = plugin / "client.py"
    client = client_path.read_text(encoding="utf-8")
    boundary = "        worker_acquired = self._worker_lock.acquire(blocking=False)\n"
    if client.count(boundary) != 1 or "UUMA_AGY_POOL_ROOT" in client:
        raise ValueError("Provider worker layout changed; review the pool adapter")
    # Idle persistent workers would permanently reserve accounts across Agent turns.
    # Preserve full Hermes message history through the plugin's existing one-shot route.
    result = client.replace(boundary, (
        '        if os.getenv("UUMA_AGY_POOL_ROOT"):\n'
        '            return self._run_oneshot_completion(\n'
        '                model=resolved_model, effort=effort, messages=messages_list,\n'
        '                timeout=effective_timeout, tools=tools, tool_choice=tool_choice,\n'
        '                stream=stream,\n'
        '            )\n\n' + boundary
    ))
    ast.parse(result)
    replacements[client_path] = result
    receipt["files"]["client.py"] = {
        "before_sha256": hashlib.sha256(client.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(result.encode()).hexdigest(),
    }
    for path, result in replacements.items():
        path.write_text(result, encoding="utf-8")
    (profile / "provider-pool-binding.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    print(json.dumps(bind(args.profile)))
