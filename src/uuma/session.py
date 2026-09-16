"""Repository session journal and fail-closed handoff gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path


class Session:
    def __init__(self, root: Path):
        self.root = root.resolve()
        directory = self.root / ".uuma-local"
        directory.mkdir(exist_ok=True)
        self.db = sqlite3.connect(directory / "uuma.db", timeout=30)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS repo_session_events "
            "(id INTEGER PRIMARY KEY, time TEXT NOT NULL, kind TEXT NOT NULL, "
            "payload TEXT NOT NULL)"
        )
        self.db.commit()

    def events(self):
        return list(
            self.db.execute("SELECT id,time,kind,payload FROM repo_session_events ORDER BY id")
        )

    def append(self, kind, **payload):
        self.db.execute(
            "INSERT INTO repo_session_events(time,kind,payload) VALUES (?,?,?)",
            (datetime.now(UTC).isoformat(), kind, json.dumps(payload)),
        )
        self.db.commit()
        self.progress()

    def progress(self):
        path = self.root / "active-session" / "progress.md"
        path.parent.mkdir(exist_ok=True)
        original = path.read_text(encoding="utf-8") if path.exists() else "# Progress\n"
        marker = "\n<!-- automatic-session-journal -->\n"
        lines = []
        for seq, time, kind, raw in self.events():
            payload = json.loads(raw)
            payload.pop("content", None)
            snapshot = payload.pop("snapshot", None)
            if snapshot is not None:
                payload["files_observed"] = len(snapshot)
            lines.append(f"- {time} #{seq} {kind}: {json.dumps(payload)}")
        path.write_text(
            original.split(marker)[0] + marker + "\n".join(lines) + "\n", encoding="utf-8"
        )

    def snapshot(self):
        result = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "Cannot verify repository snapshot: "
                + result.stderr.decode("utf-8", errors="replace").strip()
            )
        files = {}
        for name in set(result.stdout.decode("utf-8").split("\0")):
            if (
                not name
                or name.startswith((".uuma-local/", ".venv/"))
                or name in {"active-session/progress.md", "active-session/HANDOFF.md"}
            ):
                continue
            path = self.root / name
            if path.is_file() and not path.is_symlink():
                files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return files

    def active(self):
        events = self.events()
        if not events or events[-1][2] == "closed":
            raise ValueError("No active session. Run start first.")
        return events

    def start(self):
        if self.events() and self.events()[-1][2] != "closed":
            raise ValueError(
                "Unfinished session: resume it, then handoff and close; history retained."
            )
        handoff = self.root / "active-session" / "HANDOFF.md"
        self.append(
            "started",
            snapshot=self.snapshot(),
            content=handoff.read_text(encoding="utf-8") if handoff.exists() else "",
        )

    def run(self, command):
        self.active()
        before = self.snapshot()
        # Arguments/output may contain credentials: retain only executable and outcome.
        self.append("command_started", executable=Path(command[0]).name)
        try:
            code = subprocess.run(command, cwd=self.root, check=False).returncode
        except BaseException as exc:
            self.append("command_interrupted", error=type(exc).__name__)
            raise
        after = self.snapshot()
        changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        self.append("command_finished", exit_code=code, changed=changed)
        return code

    def handoff(self, summary, dead_ends, next_step):
        self.active()
        if any(not value.strip() for value in (summary, dead_ends, next_step)):
            raise ValueError("Summary, dead ends (or explicit none), and next step are required.")
        content = (
            f"# Session Handoff\n\n## Current position\n\n{summary}\n\n"
            f"## Known dead ends\n\n{dead_ends}\n\n## Next action\n\n{next_step}\n"
        )
        path = self.root / "active-session" / "HANDOFF.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.append(
            "handoff",
            snapshot=self.snapshot(),
            content=content,
            digest=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def check(self):
        events = self.active()
        if events[-1][2] != "handoff":
            raise ValueError("Fresh handoff required after the last operation.")
        payload = json.loads(events[-1][3])
        path = self.root / "active-session" / "HANDOFF.md"
        if (
            not path.exists()
            or hashlib.sha256(path.read_bytes()).hexdigest() != payload["digest"]
            or self.snapshot() != payload["snapshot"]
        ):
            raise ValueError("Files changed since handoff. Regenerate handoff before closing.")

    def close(self):
        self.check()
        self.append("closed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("start", "check", "close", "resume"):
        sub.add_parser(name)
    run = sub.add_parser("run")
    run.add_argument("command", nargs=argparse.REMAINDER)
    handoff = sub.add_parser("handoff")
    for name in ("summary", "dead-ends", "next-step"):
        handoff.add_argument("--" + name, required=True)
    args = parser.parse_args()
    session = Session(args.root)
    try:
        if args.action == "run":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if not command:
                parser.error("run requires a command")
            raise SystemExit(session.run(command))
        if args.action == "handoff":
            session.handoff(args.summary, args.dead_ends, args.next_step)
        elif args.action == "resume":
            session.active()
            session.progress()
            print("Resumed unfinished session. Review HANDOFF.md and progress.md.")
        else:
            getattr(session, args.action)()
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    finally:
        session.db.close()


if __name__ == "__main__":
    main()
