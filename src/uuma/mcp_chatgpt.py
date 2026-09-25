"""Narrow authenticated client: browser/account administration is never an MCP tool."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

from .chatgpt_bridge import BridgeStore, Consultation
from .settings import Settings

mcp = FastMCP("chatgpt-bridge")


def _open(request: Request):
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def _start_local_bridge():
    if os.name != "nt":
        raise RuntimeError("ChatGPT Bridge is unavailable; start the local service first")
    task = os.environ.get("UUMA_CHATGPT_BRIDGE_TASK", "UuMA ChatGPT Bridge")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["schtasks.exe", "/Run", "/TN", task],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=flags,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "ChatGPT Bridge could not start on demand; use the local bridge manager"
        )


def _wake_profile_extension(base: str, agent: str) -> None:
    """Open the routed Chrome profile on a short-lived authenticated dashboard URL."""
    settings = Settings.from_env()
    store = BridgeStore(settings.database_path)
    route = next((row for row in store.routes() if row["agent"] == agent), None)
    if route is None:
        return
    account = next(
        (row for row in store.accounts() if row["alias"] == route["account"]),
        None,
    )
    if account is None or not account.get("chrome_profile"):
        return

    # Imports stay local so the MCP process does not load the web app unless a
    # stopped bridge actually needs its normal Chrome profile awakened.
    from .chatgpt_server import admin_secret
    from .chrome_profiles import open_chrome_profile

    query = urlencode({"launch": secrets.token_urlsafe(8), "connect": account["alias"]})
    dashboard = f"{base}/?{query}#token={admin_secret(settings.data_dir)}"
    open_chrome_profile(account["chrome_profile"], dashboard)


def _open_with_lazy_start(request: Request, *, agent: str):
    try:
        return _open(request)
    except HTTPError:
        # Authentication, validation, and conflict responses prove the bridge is reachable.
        # Preserve them for call() instead of misreporting them as a startup failure.
        raise
    except URLError:
        _start_local_bridge()

    parsed = urlsplit(request.full_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    deadline = time.monotonic() + 30
    while True:
        try:
            _open(Request(base + "/health"))
            break
        except URLError as exc:
            if time.monotonic() >= deadline:
                raise RuntimeError("ChatGPT Bridge did not become ready within 30 seconds") from exc
            time.sleep(0.5)
    _wake_profile_extension(base, agent)
    return _open(request)


def call(path: str, payload: dict | None = None):
    agent = os.environ.get("UUMA_AGENT_ID", "")
    BridgeStore.authorize(agent)
    base = os.environ.get("UUMA_CHATGPT_BRIDGE_URL", "http://127.0.0.1:8787")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Bridge must use local loopback HTTP")
    token = Settings.from_env().load_tokens().get(agent)
    if not token:
        raise PermissionError("Missing configured UuMA agent credential")
    request = Request(base.rstrip("/") + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Authorization": "Bearer " + token, "X-UuMA-Identity": agent,
                               "Content-Type": "application/json"})
    try:
        return _open_with_lazy_start(request, agent=agent)
    except HTTPError as exc:
        raise RuntimeError(json.loads(exc.read()).get("detail", "Bridge request failed")) from None


@mcp.tool()
def chatgpt_request(run_id: str, prompt: str, idempotency_key: str, mode: str = "chat",
                    project: str = "general", thread: str = "main",
                    sites: list[str] | None = None) -> dict:
    """Queue bounded consultation. Lab-bot permits search only. Requires your active UuMA run."""
    body = Consultation(run_id=run_id, prompt=prompt, idempotency_key=idempotency_key,
                        mode=mode, project=project, thread=thread, sites=sites or [])
    return call("/agent/requests", body.model_dump())


@mcp.tool()
def chatgpt_continue(request_id: str, run_id: str, prompt: str, idempotency_key: str) -> dict:
    """Continue your completed consultation or supply requested clarification in its own thread."""
    parent = call("/agent/requests/" + quote(request_id, safe=""))
    body = Consultation(run_id=run_id, prompt=prompt, idempotency_key=idempotency_key,
                        mode=parent["mode"], project=parent["project"], thread=parent["thread"],
                        account=parent["account"], parent_id=request_id,
                        sites=parent["payload"]["sites"])
    return call("/agent/requests", body.model_dump())


@mcp.tool()
def chatgpt_status(request_id: str) -> dict:
    """Read durable progress; awaiting input is not a completed research report."""
    result = call("/agent/requests/" + quote(request_id, safe=""))
    return {k: result[k] for k in ("id", "status", "error", "url", "created", "updated")}


@mcp.tool()
def chatgpt_result(request_id: str) -> dict:
    """Get your answer, clarification, citations and conversation provenance."""
    return call("/agent/requests/" + quote(request_id, safe=""))


@mcp.tool()
def chatgpt_cancel(request_id: str) -> dict:
    """Cancel your consultation; browser cancellation is best effort, not remote deletion."""
    return call("/agent/requests/" + quote(request_id, safe="") + "/cancel", {})


@mcp.tool()
def chatgpt_list_threads() -> list:
    """List only the conversations assigned to your agent identity."""
    return call("/agent/threads")


def main():
    BridgeStore.authorize(os.environ.get("UUMA_AGENT_ID", ""))
    mcp.run()


if __name__ == "__main__":
    main()
