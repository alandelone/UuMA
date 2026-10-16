"""Live diagnostic and verification tool for ChatGPT Bridge end-to-end integration."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from uuma.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ChatGPT Bridge and Extension connectivity.")
    parser.add_argument("--url", default="http://127.0.0.1:8787", help="ChatGPT bridge URL")
    parser.add_argument("--test-ping", action="store_true", help="Submit a test consultation request")
    parser.add_argument("--agent", default="wisdom-oldman", help="Agent identity to verify")
    args = parser.parse_args()

    print(f"=== UuMA ChatGPT Bridge End-to-End Diagnostic ({args.agent}) ===")
    settings = Settings.from_env()

    # 1. Health check
    health_url = f"{args.url.rstrip('/')}/health"
    try:
        with urlopen(health_url, timeout=5.0) as res:
            health = json.loads(res.read().decode("utf-8"))
            print(f"[OK] Bridge service healthy: {health}")
    except (URLError, HTTPError, OSError) as exc:
        print(f"[FAIL] Bridge service unreachable at {health_url}: {exc}")
        return 1

    # 2. Database account check
    db_path = settings.database_path
    if not db_path.exists():
        print(f"[FAIL] Control database missing: {db_path}")
        return 1

    with sqlite3.connect(db_path) as db:
        cur = db.cursor()
        cur.execute("SELECT alias, identity, workspace, enabled, status, chrome_profile FROM chatgpt_accounts")
        accounts = cur.fetchall()
        print(f"Found {len(accounts)} ChatGPT accounts in uuma.db:")
        for acct in accounts:
            print(f"  - alias={acct[0]}, identity={acct[1]}, status={acct[4]}, profile={acct[5]}")

        cur.execute("SELECT agent, account FROM chatgpt_routes WHERE agent=?", (args.agent,))
        route = cur.fetchone()
        if not route:
            print(f"[WARN] No route configured for agent {args.agent}")
        else:
            print(f"[OK] Route configured: agent={route[0]} -> account={route[1]}")

    # 3. Extension pairing check
    pairs_file = settings.data_dir / "chatgpt-bridge" / "extension-pairs.json"
    if pairs_file.exists():
        pairs = json.loads(pairs_file.read_text(encoding="utf-8"))
        print(f"[OK] Extension paired accounts: {list(pairs.keys())}")
    else:
        print("[WARN] No extension pairs file found.")

    tokens = settings.load_tokens()
    token = tokens.get(args.agent)
    if not token:
        print(f"[FAIL] No UuMA token configured for agent {args.agent}")
        return 1
    print(f"[OK] Found token for {args.agent} (length {len(token)})")

    if args.test_ping:
        print("\nSubmitting test consultation ping...")
        temp_task_id = None
        temp_run_id = None
        with sqlite3.connect(db_path) as db:
            cur = db.cursor()
            cur.execute(
                "SELECT run_id FROM runs WHERE agent_id=? AND status='RUNNING' ORDER BY updated_sequence DESC LIMIT 1",
                (args.agent,)
            )
            row = cur.fetchone()
            if row:
                run_id = row[0]
            else:
                temp_task_id = f"task_diag_{int(time.time())}"
                temp_run_id = f"run_diag_{int(time.time())}"
                cur.execute(
                    """INSERT INTO tasks(task_id, title, status, assignee, contract_json, current_run_id, updated_sequence)
                    VALUES(?, 'ChatGPT Diagnostic Task', 'RUNNING', ?, '{}', ?, 0)""",
                    (temp_task_id, args.agent, temp_run_id)
                )
                cur.execute(
                    """INSERT INTO runs(run_id, task_id, agent_id, status, source, execution_class, progress_json, updated_sequence)
                    VALUES(?, ?, ?, 'RUNNING', 'diagnostic', 'READ_ONLY', '{}', 0)""",
                    (temp_run_id, temp_task_id, args.agent)
                )
                db.commit()
                run_id = temp_run_id

        submit_url = f"{args.url.rstrip('/')}/agent/requests"
        payload = {
            "run_id": run_id,
            "project": "diagnostics",
            "thread": "diag-main",
            "mode": "chat",
            "prompt": "UuMA bridge diagnostic ping. Respond with PONG.",
            "idempotency_key": f"diag-ping-{int(time.time())}",
            "sites": [],
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UuMA-Identity": args.agent,
            "Content-Type": "application/json",
        }
        req = Request(submit_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(req, timeout=10.0) as res:
                created = json.loads(res.read().decode("utf-8"))
            req_id = created["id"]
            print(f"[OK] Request created: {req_id}, initial status: {created.get('status')}")
        except Exception as exc:
            print(f"[FAIL] Request submission failed: {exc}")
            return 1

        print("Polling status for up to 35 seconds...")
        status_url = f"{args.url.rstrip('/')}/agent/requests/{req_id}"
        deadline = time.monotonic() + 35.0
        while time.monotonic() < deadline:
            time.sleep(2.0)
            req_poll = Request(status_url, headers=headers, method="GET")
            try:
                with urlopen(req_poll, timeout=5.0) as res:
                    state = json.loads(res.read().decode("utf-8"))
                st = state.get("status")
                err = state.get("error")
                print(f"  -> status: {st}, error: {err}")
                if st == "COMPLETED":
                    print("[SUCCESS] Consultation completed successfully!")
                    print(f"Answer snippet: {str(state.get('result', {}).get('answer'))[:200]}")
                    if temp_task_id:
                        with sqlite3.connect(db_path) as db:
                            db.execute("DELETE FROM runs WHERE run_id=?", (temp_run_id,))
                            db.execute("DELETE FROM tasks WHERE task_id=?", (temp_task_id,))
                            db.commit()
                    return 0
                if st in {"FAILED", "PAUSED", "CANCELLED", "NEEDS_REVIEW"}:
                    print(f"[NOTICE] Request ended with status: {st}, error: {err}")
                    if temp_task_id:
                        with sqlite3.connect(db_path) as db:
                            db.execute("DELETE FROM runs WHERE run_id=?", (temp_run_id,))
                            db.execute("DELETE FROM tasks WHERE task_id=?", (temp_task_id,))
                            db.commit()
                    return 2
            except Exception as poll_exc:
                print(f"  -> poll error: {poll_exc}")
                break

        if temp_task_id:
            with sqlite3.connect(db_path) as db:
                db.execute("DELETE FROM runs WHERE run_id=?", (temp_run_id,))
                db.execute("DELETE FROM tasks WHERE task_id=?", (temp_task_id,))
                db.commit()

    return 0


if __name__ == "__main__":
    sys.exit(main())
