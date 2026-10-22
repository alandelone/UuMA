"""Sync Wisdom-Oldman's real Hermes commands; no chat messages or update polling."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.profile_home.name != "wisdom-oldman":
        raise SystemExit("Only Wisdom-Oldman may use this menu installer")
    os.environ["HERMES_HOME"] = str(args.profile_home.resolve())
    from hermes_cli.commands_platforms import telegram_menu_commands, telegram_menu_max_commands

    menu, _ = telegram_menu_commands(max_commands=telegram_menu_max_commands())
    commands = [{"command": name, "description": description} for name, description in menu]
    assert {"topics", "progress", "wisdom", "model", "new", "stop", "help"} <= {
        row["command"] for row in commands
    }
    assert [row["command"] for row in commands[:3]] == ["progress", "topics", "wisdom"]
    if not args.apply:
        print(json.dumps({"commands": commands}, ensure_ascii=False))
        return
    from dotenv import dotenv_values

    token = dotenv_values(args.profile_home / ".env").get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Wisdom-Oldman credential is unavailable")

    def api(method: str, payload: dict):
        request = Request(
            f"https://api.telegram.org/bot{token}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Telegram {method}: {type(exc).__name__}; token omitted") from None
        if result.get("ok") is not True:
            raise RuntimeError(f"Telegram {method} did not acknowledge operation")
        return result["result"]

    before = []
    for scope in ("default", "all_private_chats", "all_group_chats"):
        for language in ("", "zh", "en"):
            payload = {"scope": {"type": scope}, "language_code": language}
            before.append({"scope": payload, "commands": api("getMyCommands", payload)})
    args.evidence.mkdir(parents=True, exist_ok=True)
    with (args.evidence / "telegram-menu.before.json").open("x", encoding="utf-8") as stream:
        json.dump(before, stream, ensure_ascii=False, indent=2)
    changed = []
    for row in before:
        payload = row["scope"]
        if payload["language_code"] and not row["commands"]:
            continue
        api("setMyCommands", {**payload, "commands": commands})
        assert api("getMyCommands", payload) == commands
        changed.append(payload)
    receipt = {
        "commands": commands,
        "updated_scopes": changed,
        "readback_verified": True,
        "chat_messages_sent": 0,
    }
    (args.evidence / "telegram-menu.after.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "commands": len(commands),
                "scopes_updated": len(changed),
                "readback_verified": True,
                "chat_messages_sent": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
