from __future__ import annotations

import hmac
import json
import secrets
from pathlib import Path

TOKEN_ROLES = {
    "orchestrator": "control",
    "brainstormer": "worker",
    "scholar": "worker",
    "wisdom-oldman": "worker",
    "forge-lab-bot": "worker",
    "yonc": "worker",
    "audit": "ingest",
}


class TokenRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self, *, overwrite: bool = False) -> dict[str, str]:
        if self.path.exists() and not overwrite:
            tokens = self.load()
            missing = [identity for identity in TOKEN_ROLES if identity not in tokens]
            if not missing:
                return tokens
            tokens.update({identity: secrets.token_urlsafe(32) for identity in missing})
            self.path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
            return tokens
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tokens = {identity: secrets.token_urlsafe(32) for identity in TOKEN_ROLES}
        self.path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
        return tokens

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            # Malformed serialized input retains the public ValueError contract.
            raise ValueError("Token file must contain an object")  # noqa: TRY004
        return {str(key): str(token) for key, token in value.items()}

    def verify(self, identity: str, token: str, required_role: str) -> bool:
        expected = self.load().get(identity)
        role = TOKEN_ROLES.get(identity)
        return bool(
            expected
            and role == required_role
            and hmac.compare_digest(expected.encode("utf-8"), token.encode("utf-8"))
        )
