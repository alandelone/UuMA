from __future__ import annotations

import argparse
import json
import sys

from .approval import capture_user_approval


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--message-id", required=True)
    args = parser.parse_args()
    result = capture_user_approval(
        args.root,
        profile=args.profile,
        session_id=args.session_id,
        message_id=args.message_id,
        user_message=sys.stdin.read(),
    )
    print(json.dumps(result or {}, sort_keys=True))


if __name__ == "__main__":
    main()
