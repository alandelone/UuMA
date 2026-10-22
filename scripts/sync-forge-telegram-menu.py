"""Publish Hermes Forge's real command menu; never send chat messages or poll updates."""

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
    if args.profile_home.name != "forge-lab-bot":
        raise SystemExit("This menu migration is restricted to forge-lab-bot.")
    os.environ["HERMES_HOME"] = str(args.profile_home.resolve())
    from hermes_cli.commands_platforms import telegram_menu_commands, telegram_menu_max_commands

    menu, hidden = telegram_menu_commands(max_commands=telegram_menu_max_commands())
    commands = [{"command": name, "description": description} for name, description in menu]
    assert {"forge", "inventory", "projects", "shortages", "worklog", "cancel", "model",
            "new", "help"} <= {row["command"] for row in commands}
    assert not any("AntiGravity" in row["description"] for row in commands)
    if not args.apply:
        print(json.dumps({"mode": "preview", "commands": commands, "hidden": hidden}, ensure_ascii=False))
        return
    from dotenv import dotenv_values

    token = dotenv_values(args.profile_home / ".env").get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Forge bot credential is unavailable; no menu was changed.")

    def api(method: str, data: dict):
        request = Request(f"https://api.telegram.org/bot{token}/{method}",
                          data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=20) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Telegram {method} failed ({type(exc).__name__}); credential omitted.") from None
        if not result.get("ok"):
            raise RuntimeError(f"Telegram {method} did not acknowledge the operation.")
        return result["result"]

    before = []
    for scope_type in ("default", "all_private_chats", "all_group_chats"):
        for language in ("", "zh", "en"):
            payload = {"scope": {"type": scope_type}, "language_code": language}
            previous = api("getMyCommands", payload)
            before.append({"scope": payload, "commands": previous})
    args.evidence.mkdir(parents=True, exist_ok=True)
    with (args.evidence / "telegram-menu.before.json").open("x", encoding="utf-8") as stream:
        json.dump(before, stream, ensure_ascii=False, indent=2)
    changed = []
    for entry in before:
        payload = entry["scope"]
        if payload["language_code"] and not entry["commands"]:
            continue
        api("setMyCommands", {**payload, "commands": commands})
        assert api("getMyCommands", payload) == commands, "Published menu did not match readback"
        changed.append(payload)
    receipt = {"receiver": "Hermes forge-lab-bot", "commands": commands,
               "updated_scopes": changed, "readback_verified": True, "chat_messages_sent": 0}
    (args.evidence / "telegram-menu.after.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"menu_commands": len(commands), "scopes_updated": len(changed),
                      "readback_verified": True, "chat_messages_sent": 0}))


if __name__ == "__main__":
    main()
