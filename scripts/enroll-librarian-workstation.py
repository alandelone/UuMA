"""Enroll a workstation public key on the server with a checked request digest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from uuma.librarian_enrollment import enroll


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--authorized-keys", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--launcher-sha256", required=True)
    args = parser.parse_args()
    result = enroll(request_path=args.request, expected_request_sha256=args.request_sha256,
                    policy_path=args.policy, authorized_keys=args.authorized_keys,
                    receipts=args.receipts, python=args.python, launcher=args.launcher,
                    expected_launcher_sha256=args.launcher_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
