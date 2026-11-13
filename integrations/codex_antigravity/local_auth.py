"""Codex credential helper for the loopback gateway, independent of ChatGPT login."""

from pathlib import Path


def main() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / ".uuma-local/codex-antigravity-ui-20261102/gateway-token"
    )
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32 or any(character.isspace() for character in token):
        raise SystemExit("Invalid local gateway credential; run manage.py independent-auth")
    # This stdout is consumed privately by Codex's command-backed auth protocol.
    print(token)


if __name__ == "__main__":
    main()
