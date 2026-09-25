from __future__ import annotations

import argparse
import json
import logging
import os
import webbrowser
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from secrets import token_urlsafe

from .chatgpt_bridge import BridgeStore
from .chatgpt_server import admin_secret, create_app
from .settings import Settings


def dashboard_url(data_dir: Path, port: int) -> str:
    """Return a one-use navigation URL so Chrome reloads an existing dashboard tab."""
    launch_id = token_urlsafe(8)
    return f"http://127.0.0.1:{port}/?launch={launch_id}#token={admin_secret(data_dir)}"


@contextmanager
def instance_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def main():
    parser = argparse.ArgumentParser(description="UuMA ChatGPT Web Bridge")
    parser.add_argument("--data-dir", type=Path, default=Settings.from_env().data_dir)
    parser.add_argument("--port", type=int, default=8787)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("dashboard")
    account = sub.add_parser("account")
    commands = account.add_subparsers(dest="action", required=True)
    commands.add_parser("list")
    add = commands.add_parser("add")
    add.add_argument("alias")
    add.add_argument("--identity", required=True)
    add.add_argument("--workspace", default="Personal")
    for name in ("open", "verify", "enable", "disable"):
        commands.add_parser(name).add_argument("alias")
    bind = sub.add_parser("bind")
    bind.add_argument("agent")
    bind.add_argument("account")
    args = parser.parse_args()
    if args.command == "dashboard":
        # The launch secret is a URL fragment: never sent in HTTP URLs or access logs.
        webbrowser.open(dashboard_url(args.data_dir, args.port))
        return
    if args.command == "serve":
        import uvicorn

        root = args.data_dir / "chatgpt-bridge"
        root.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(root / "service.log", maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[handler])
        with instance_lock(root / "runner.lock"):
            uvicorn.run(create_app(args.data_dir, port=args.port), host="127.0.0.1",
                        port=args.port, access_log=False, log_config=None)
        return
    store = BridgeStore(args.data_dir / "uuma.db")
    if args.command == "bind":
        store.bind(args.agent, args.account)
    elif args.action == "list":
        print(json.dumps(store.accounts(), indent=2))
    elif args.action == "add":
        store.add_account(args.alias, args.identity, args.workspace)
    else:
        store.account_action(args.alias, args.action)


if __name__ == "__main__":
    main()
