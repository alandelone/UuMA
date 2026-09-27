"""Chrome Native Messaging host CLI entry point."""

from __future__ import annotations

import os

# Set restricted native worker mode
os.environ["UUMA_WORKER_MODE"] = "native"
os.environ["UUMA_AGENT_ID"] = "forge-lab-bot"

from uuma.native_host.host import NativeHost


def main() -> None:
    host = NativeHost()
    host.run_loop()


if __name__ == "__main__":
    main()
