from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    artifact_dir: Path
    ingest_spool_dir: Path
    hermes_executable: Path
    kanban_board: str = "uuma-control"
    knowledge_data_dir: Path | None = None
    honc_data_dir: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        data_dir = Path(os.environ.get("UUMA_DATA_DIR", local_app_data / "UuMA")).expanduser()
        default_hermes = (
            local_app_data
            / "hermes"
            / "hermes-agent"
            / "venv"
            / "Scripts"
            / "hermes.exe"
        )
        return cls(
            data_dir=data_dir,
            database_path=data_dir / "uuma.db",
            artifact_dir=data_dir / "artifacts",
            ingest_spool_dir=data_dir / "spool" / "hermes",
            hermes_executable=Path(os.environ.get("UUMA_HERMES_EXE", default_hermes)),
            kanban_board=os.environ.get("UUMA_KANBAN_BOARD", "uuma-control"),
            knowledge_data_dir=(
                Path(os.environ["UUMA_KNOWLEDGE_DATA_DIR"]).expanduser()
                if os.environ.get("UUMA_KNOWLEDGE_DATA_DIR") else None
            ),
            honc_data_dir=(
                Path(os.environ["UUMA_HONC_DATA_DIR"]).expanduser()
                if os.environ.get("UUMA_HONC_DATA_DIR") else None
            ),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.ingest_spool_dir.mkdir(parents=True, exist_ok=True)
        (self.honc_data_dir or (self.data_dir / "honc")).mkdir(parents=True, exist_ok=True)

    def token_file(self) -> Path:
        return self.data_dir / "tokens.json"

    def knowledge_database_path(self) -> Path:
        """Return Wisdom-Oldman's database without coupling it to control-plane state."""
        return (self.knowledge_data_dir or self.data_dir) / "wisdom.db"

    def knowledge_content_path(self) -> Path:
        """Return the content-addressed source store kept beside, but outside, wisdom.db."""
        path = (self.knowledge_data_dir or self.data_dir) / "wisdom-content"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def honc_database_path(self) -> Path:
        """Return honc's database path without coupling it to control-plane or knowledge state."""
        return (self.honc_data_dir or (self.data_dir / "honc")) / "honc.db"

    def load_tokens(self) -> dict[str, str]:
        path = self.token_file()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
