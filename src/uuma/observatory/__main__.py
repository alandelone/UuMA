"""CLI launcher for UuMA All-in-One Observatory server."""
from __future__ import annotations

import argparse
import sys

import uvicorn

from .server import create_observatory_app


def main() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Start the UuMA All-in-One Observatory server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8790, help="Port to listen on (default: 8790)")
    parser.add_argument("--token", default=None, help="Explicit view token for authentication")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()

    app = create_observatory_app(auth_token=args.token)

    print("\n=======================================================")
    print(f"[START] UuMA All-in-One Observatory running on http://{args.host}:{args.port}")
    print(f"[TOKEN] Auth Token: {app.state.valid_token}")
    print(f"[URL] Direct Access: http://{args.host}:{args.port}/?auth={app.state.valid_token}")
    print("=======================================================\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
