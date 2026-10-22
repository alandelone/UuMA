"""Authenticated speech relay to the workstation's fixed local STT command."""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .auth import TokenRegistry

ALLOWED_AGENTS = {"brainstormer", "yonc", "honc", "wisdom-oldman", "forge-lab-bot"}
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_REQUEST_BYTES = 4 * ((MAX_AUDIO_BYTES + 2) // 3) + 2048
SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".oga", ".opus", ".flac", ".aac", ".webm"}


class RelayUnavailable(RuntimeError):
    pass


class AudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio_base64: str = Field(min_length=1, max_length=MAX_REQUEST_BYTES)
    extension: str = Field(pattern=r"^\.[A-Za-z0-9]{1,8}$")
    language: str = Field(default="auto", pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
    model: str = Field(default="stt", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


@dataclass(frozen=True)
class RelaySettings:
    python: Path
    script: Path
    token_registry: Path
    temporary_root: Path | None = None

    @classmethod
    def from_env(cls) -> RelaySettings:
        return cls(
            python=Path(os.environ["UUMA_STT_PYTHON"]),
            script=Path(os.environ["UUMA_STT_SCRIPT"]),
            token_registry=Path(os.environ["UUMA_STT_TOKEN_REGISTRY"]),
        )


def _decode_audio(value: AudioRequest) -> bytes:
    if value.extension.lower() not in SUFFIXES:
        raise ValueError("Unsupported audio suffix")
    try:
        audio = base64.b64decode(value.audio_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("Invalid base64 audio") from error
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Audio must contain between 1 byte and 20 MiB")
    return audio


def _transcribe(settings: RelaySettings, value: AudioRequest, audio: bytes) -> str:
    if not all(
        path.is_absolute() and path.is_file() for path in (settings.python, settings.script)
    ):
        raise RelayUnavailable("desktop_unavailable: local speech command is not configured")
    with tempfile.TemporaryDirectory(prefix="uuma-stt-", dir=settings.temporary_root) as work:
        directory = Path(work)
        if os.name != "nt" and stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise RelayUnavailable("desktop_unavailable: speech temporary directory is not private")
        audio_path = directory / ("audio" + value.extension.lower())
        output_path = directory / "text.txt"
        descriptor = os.open(audio_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(audio)
        command = [
            str(settings.python), str(settings.script), "--input", str(audio_path),
            "--output", str(output_path), "--language", value.language, "--model", value.model,
        ]
        try:
            result = subprocess.run(
                command, shell=False, capture_output=True, timeout=150, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RelayUnavailable(
                "desktop_unavailable: speech execution failed or timed out"
            ) from error
        if (
            result.returncode or not output_path.is_file()
            or output_path.stat().st_size > 1024 * 1024
        ):
            raise RelayUnavailable(
                "desktop_unavailable: speech command returned no valid transcript"
            )
        try:
            transcript = output_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise RelayUnavailable(
                "desktop_unavailable: speech output could not be read"
            ) from error
        if not transcript:
            raise RelayUnavailable(
                "desktop_unavailable: speech command returned an empty transcript"
            )
        return transcript


def create_app(
    settings: RelaySettings | None = None, *, tokens: TokenRegistry | None = None
) -> FastAPI:
    app = FastAPI(title="UuMA workstation speech relay", docs_url=None, redoc_url=None)

    @app.post("/v1/transcribe")
    async def transcribe(request: Request):
        try:
            configuration = settings or RelaySettings.from_env()
            registry = tokens or TokenRegistry(configuration.token_registry)
        except (KeyError, ValueError, OSError) as error:
            raise HTTPException(
                503, "desktop_unavailable: speech relay is not configured"
            ) from error
        authorization = request.headers.get("authorization", "")
        identity = request.headers.get("x-uuma-identity", "")
        bearer = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not identity and bearer:
            matches = [
                agent for agent in ALLOWED_AGENTS if registry.verify(agent, bearer, "worker")
            ]
            identity = matches[0] if len(matches) == 1 else ""
        if (
            identity not in ALLOWED_AGENTS or not bearer
            or not registry.verify(identity, bearer, "worker")
        ):
            raise HTTPException(403, "Invalid speech relay identity")
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > MAX_REQUEST_BYTES:
                raise HTTPException(413, "Audio request exceeds 20 MiB limit")
        try:
            value = AudioRequest.model_validate_json(bytes(body))
            audio = _decode_audio(value)
        except (ValidationError, ValueError) as error:
            raise HTTPException(422, "Invalid bounded audio request") from error
        try:
            transcript = await run_in_threadpool(_transcribe, configuration, value, audio)
        except RelayUnavailable as error:
            raise HTTPException(503, str(error)) from error
        return {"transcript": transcript, "agent_id": identity}

    return app


def transcribe_remote(input_path: Path, output_path: Path, *, language="auto", model="stt",
                      client: httpx.Client | None = None) -> None:
    identity = os.environ.get("UUMA_AGENT_ID", "")
    if identity not in ALLOWED_AGENTS:
        raise PermissionError("Agent is not permitted to use the speech relay")
    endpoint = os.environ.get("UUMA_STT_RELAY_URL", "http://127.0.0.1:8774").rstrip("/")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path
    ):
        raise ValueError("Speech relay must use a loopback HTTP endpoint")
    token_path = Path(os.environ["UUMA_STT_TOKEN_FILE"])
    token = token_path.read_text(encoding="utf-8").strip()
    if not token or len(token) > 1024:
        raise ValueError("A scoped speech relay token is required")
    if input_path.stat().st_size > MAX_AUDIO_BYTES:
        raise ValueError("Audio exceeds 20 MiB")
    value = AudioRequest(audio_base64=base64.b64encode(input_path.read_bytes()).decode("ascii"),
                         extension=input_path.suffix, language=language, model=model)
    _decode_audio(value)

    def request(http):
        try:
            response = http.post(endpoint + "/v1/transcribe", json=value.model_dump(),
                                 headers={"Authorization": f"Bearer {token}",
                                          "X-Uuma-Identity": identity}, timeout=160)
            response.raise_for_status()
            payload = response.json()
            transcript = payload.get("transcript")
            if (payload.get("agent_id") != identity or not isinstance(transcript, str)
                    or not transcript.strip() or len(transcript) > 1024 * 1024):
                raise ValueError("Invalid transcript response")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as error:
            raise RelayUnavailable(
                "desktop_unavailable: waiting for workstation speech; request was not retried"
            ) from error
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(transcript.strip(), encoding="utf-8")

    if client is not None:
        request(client)
    else:
        with httpx.Client(transport=httpx.HTTPTransport(retries=0), follow_redirects=False,
                          trust_env=False) as http:
            request(http)


app = create_app()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8774)
    transcribe = sub.add_parser("transcribe")
    transcribe.add_argument("--input", required=True, type=Path)
    transcribe.add_argument("--output", required=True, type=Path)
    transcribe.add_argument("--language", default="auto")
    transcribe.add_argument("--model", default="stt")
    args = parser.parse_args()
    if args.action == "serve":
        import uvicorn

        configuration = RelaySettings.from_env()
        uvicorn.run(create_app(configuration), host="127.0.0.1", port=args.port)
        return 0
    try:
        transcribe_remote(args.input, args.output, language=args.language, model=args.model)
    except (RelayUnavailable, OSError, ValueError, KeyError) as error:
        print(f"Speech relay failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
