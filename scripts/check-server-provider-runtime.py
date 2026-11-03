"""Check the server's pinned account-pool transport without calling a model."""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


def check(runtime_dir: Path, hermes_home: Path) -> dict:
    runtime_dir = runtime_dir.resolve(strict=True)
    pool_module = importlib.import_module("uuma_provider_pool")
    expected = runtime_dir / "uuma_provider_pool.py"
    if Path(pool_module.__file__).resolve() != expected:
        raise RuntimeError("The account-pool module is not from the configured release")
    pool = pool_module.AccountPool(Path(os.environ["UUMA_AGY_POOL_ROOT"]))
    if pool.authentication_token() is None:
        raise RuntimeError("The configured account pool has no ready authorization")
    command = Path(os.environ["ANTIGRAVITY_COMMAND"]).resolve(strict=True)
    if command.parent != runtime_dir.parent:
        raise RuntimeError("Provider wrapper and account-pool runtime releases differ")
    plugin = hermes_home / "plugins" / "antigravity-oauth"
    name = "_uuma_provider_readiness"
    spec = importlib.util.spec_from_file_location(
        name, plugin / "__init__.py", submodule_search_locations=[str(plugin)]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("The Antigravity provider plugin cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="uuma-provider-readiness-") as workspace:
        client = module.antigravity_profile.create_client(command=str(command), cwd=workspace)
        try:
            if type(client).__name__ != "AntigravityClient":
                raise RuntimeError("Provider initialization selected the wrong client")
        finally:
            client.close()
    status = pool.status()
    return {
        "module": str(expected),
        "client": "AntigravityClient",
        "account_count": len(status["accounts"]),
        "ready_accounts": sum(a["status"] == "READY" for a in status["accounts"]),
        "inference_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--hermes-home", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.runtime_dir, args.hermes_home)
    except Exception as error:  # Startup must stop before the generic SDK fallback.
        raise SystemExit("Provider runtime preflight failed: " + type(error).__name__) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
