"""Adversarial FastMCP Protocol Stress Test Harness for Milestone 2 Verification.

Empirically tests:
1. Protocol Fuzzing (malformed JSON, unknown methods, missing id, invalid params)
2. Input Bound Fuzzing (negative bounds, oversized payloads, null bytes, unicode injection)
3. Tool Surface Verification (10 catalog tools, schema compliance, execution correctness)
4. Concurrent Subprocess Calls (multi-client stdio dispatch, lock contention, database integrity)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Pinned and executable paths
UUMA_ROOT = Path(r"C:\Users\Alandelone\CodeSpace_Local\UuMA")
RSTV4_ROOT = Path(r"C:\Users\Alandelone\CodeSpace_Local\RSTV4")
PYTHON_EXE = RSTV4_ROOT / ".venv" / "Scripts" / "python.exe"
RUNNER_SCRIPT = UUMA_ROOT / "scripts" / "run-scholar-catalog-mcp.py"
MANIFEST_PATH = UUMA_ROOT / ".uuma-local" / "scholar-catalog-runtime" / "active-release.json"
CATALOG_DB = RSTV4_ROOT / "data" / "catalog.db"


class StdioMcpClient:
    """Robust non-blocking stdio FastMCP client harness with strict timeouts."""

    def __init__(self, timeout: float = 6.0):
        self.cmd = [
            str(PYTHON_EXE),
            str(RUNNER_SCRIPT),
            "--project-root", str(UUMA_ROOT),
            "--data-root", str(RSTV4_ROOT),
            "--manifest", str(MANIFEST_PATH),
        ]
        self.proc = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.q_out: queue.Queue[str] = queue.Queue()
        self.q_err: queue.Queue[str] = queue.Queue()
        self.t_out = threading.Thread(target=self._reader, args=(self.proc.stdout, self.q_out), daemon=True)
        self.t_err = threading.Thread(target=self._reader, args=(self.proc.stderr, self.q_err), daemon=True)
        self.t_out.start()
        self.t_err.start()
        self.default_timeout = timeout

    @staticmethod
    def _reader(pipe, q: queue.Queue[str]):
        try:
            for line in iter(pipe.readline, ""):
                q.put(line)
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def send_line(self, line: str):
        if self.proc.poll() is not None:
            raise RuntimeError(f"Child process exited prematurely with code {self.proc.returncode}")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def read_stdout(self, timeout: float | None = None) -> str | None:
        to = self.default_timeout if timeout is None else timeout
        try:
            return self.q_out.get(timeout=to)
        except queue.Empty:
            return None

    def read_stderr(self) -> str:
        lines = []
        while not self.q_err.empty():
            lines.append(self.q_err.get_nowait())
        return "".join(lines)

    def rpc_call(self, req_id: Any, method: str, params: Any = None, timeout: float | None = None) -> dict[str, Any] | None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.send_line(json.dumps(payload))
        line = self.read_stdout(timeout)
        if line is None:
            return None
        return json.loads(line)

    def notify(self, method: str, params: Any = None):
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.send_line(json.dumps(payload))

    def handshake(self) -> dict[str, Any]:
        resp = self.rpc_call(1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "adversarial-tester", "version": "1.0"},
        })
        self.notify("notifications/initialized")
        return resp or {}

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# ==============================================================================
# SECTION 1: PROTOCOL FUZZING
# ==============================================================================

def test_protocol_fuzzing() -> dict[str, Any]:
    """Test malformed JSON-RPC payloads, unknown methods, missing id, invalid params."""
    results = {}
    client = StdioMcpClient(timeout=4.0)
    try:
        init_res = client.handshake()
        assert client.is_alive(), "Process died on handshake"
        results["handshake"] = {
            "server_name": init_res.get("result", {}).get("serverInfo", {}).get("name"),
            "protocol_version": init_res.get("result", {}).get("protocolVersion"),
        }

        # 1.1 Unknown method
        resp = client.rpc_call(101, "catalog/nonexistent_method", {"param": 1})
        assert resp is not None, "Timeout waiting for unknown method response"
        assert resp.get("error", {}).get("code") in (-32601, -32602, -32600), f"Expected JSON-RPC error, got {resp}"
        results["unknown_method"] = resp["error"]

        # 1.2 Invalid params on tools/list (pass string instead of object)
        resp = client.rpc_call(102, "tools/list", "INVALID_PARAM_TYPE")
        # Should return response or error without dying
        assert resp is not None, "Timeout on invalid params"
        results["invalid_params_type"] = resp

        # 1.3 Missing name in tools/call
        resp = client.rpc_call(103, "tools/call", {})
        assert resp is not None, "Timeout on missing tool name"
        assert "error" in resp or resp.get("result", {}).get("isError"), f"Expected error on empty tools/call: {resp}"
        results["missing_tool_name_in_call"] = resp

        # 1.4 Call unknown tool name
        resp = client.rpc_call(104, "tools/call", {"name": "unknown_tool_xyz_999", "arguments": {}})
        assert resp is not None, "Timeout on unknown tool call"
        assert "error" in resp or resp.get("result", {}).get("isError"), f"Expected error on unknown tool: {resp}"
        results["unknown_tool_call"] = resp

        # 1.5 Missing id on request (JSON-RPC notification vs request mismatch)
        client.send_line(json.dumps({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_catalog_reading_status"}}))
        # Notifications do not return responses per JSON-RPC spec. Verify server does not crash.
        time.sleep(0.5)
        assert client.is_alive(), "Process died when notification without id was sent"
        results["missing_id_notification_handled"] = "PASSED (server ignored or handled without dying)"

        # 1.6 Verify liveness after protocol fuzzing
        liveness_resp = client.rpc_call(105, "tools/list", {})
        assert liveness_resp is not None and "result" in liveness_resp
        results["liveness_after_fuzzing"] = "PASSED (server alive and responding)"

    finally:
        client.close()

    # 1.7 Malformed JSON syntax on separate client
    client2 = StdioMcpClient(timeout=3.0)
    try:
        client2.send_line('{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": { BROKEN JSON')
        resp_line = client2.read_stdout(timeout=2.0)
        stderr_text = client2.read_stderr()
        results["malformed_json_syntax"] = {
            "stdout_response": resp_line.strip() if resp_line else "NO_STDOUT",
            "stderr_output": stderr_text[:200].strip(),
            "process_alive": client2.is_alive()
        }
    finally:
        client2.close()

    return results


# ==============================================================================
# SECTION 2: INPUT BOUND FUZZING
# ==============================================================================

def test_input_bound_fuzzing() -> dict[str, Any]:
    """Test extreme boundaries, invalid types, oversized inputs, and unicode injections."""
    results = {}
    client = StdioMcpClient(timeout=6.0)
    try:
        client.handshake()

        # 2.1 Negative theme_offset / theme_limit on query_catalog_understanding
        resp = client.rpc_call(201, "tools/call", {
            "name": "query_catalog_understanding",
            "arguments": {"theme_offset": -1, "theme_limit": -10}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "ValueError" in json.dumps(resp)
        results["negative_theme_limits"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.2 theme_limit exceeding maximum (100)
        resp = client.rpc_call(202, "tools/call", {
            "name": "query_catalog_understanding",
            "arguments": {"theme_offset": 0, "theme_limit": 99999}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "ValueError" in json.dumps(resp)
        results["exceeded_theme_limit"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.3 Malformed query_json string
        resp = client.rpc_call(203, "tools/call", {
            "name": "query_catalog_understanding",
            "arguments": {"query_json": "INVALID_JSON_CONTENT_NOT_A_DICT"}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "error" in json.dumps(resp).lower()
        results["malformed_query_json"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.4 Null byte injection in paper_id
        resp = client.rpc_call(204, "tools/call", {
            "name": "get_catalog_understanding",
            "arguments": {"paper_id": "paper_\x00\x00_inject"}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "error" in json.dumps(resp).lower()
        results["null_byte_paper_id"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.5 Path traversal attempt in paper_id
        resp = client.rpc_call(205, "tools/call", {
            "name": "get_catalog_understanding",
            "arguments": {"paper_id": "../../../../../Windows/System32/drivers/etc/hosts"}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "error" in json.dumps(resp).lower()
        results["path_traversal_paper_id"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.6 SQL injection attempt in paper_id
        resp = client.rpc_call(206, "tools/call", {
            "name": "get_catalog_understanding",
            "arguments": {"paper_id": "' OR 1=1; DROP TABLE papers; --"}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "error" in json.dumps(resp).lower()
        results["sql_injection_paper_id"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.7 Oversized query string in query_catalog_content (5,000 chars)
        large_query = "energy storage optimization " * 200
        resp = client.rpc_call(207, "tools/call", {
            "name": "query_catalog_content",
            "arguments": {"query_json": json.dumps({"text": large_query, "limit": 2})}
        })
        assert resp is not None
        results["oversized_query_string"] = {
            "status": "handled",
            "has_result": "result" in resp,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.8 Unicode, RTL, Emoji stress in get_catalog_reading_status
        resp = client.rpc_call(208, "tools/call", {
            "name": "get_catalog_reading_status",
            "arguments": {"paper_id": "⚡🔥الورقة_العلمية_123🚀"}
        })
        assert resp is not None
        assert "error" in resp or resp.get("result", {}).get("isError") or "error" in json.dumps(resp).lower()
        results["unicode_rtl_emoji"] = {
            "is_error": True,
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.9 Negative limit/offset in get_catalog_reading_status
        resp = client.rpc_call(209, "tools/call", {
            "name": "get_catalog_reading_status",
            "arguments": {"offset": -10, "limit": -50}
        })
        assert resp is not None
        results["negative_status_bounds"] = {
            "status": "handled",
            "response_preview": json.dumps(resp)[:150]
        }

        # 2.10 Verify liveness after boundary fuzzing
        resp = client.rpc_call(210, "tools/call", {
            "name": "get_catalog_reading_status",
            "arguments": {"section": "overview"}
        })
        assert resp is not None and "result" in resp and not resp.get("result", {}).get("isError")
        results["liveness_after_bounds"] = "PASSED (server alive and answering valid queries)"

    finally:
        client.close()

    return results


# ==============================================================================
# SECTION 3: TOOL SURFACE VERIFICATION
# ==============================================================================

def test_tool_surface_verification() -> dict[str, Any]:
    """Verify registered tools, schemas, and actual execution against the canonical catalog."""
    results = {}
    client = StdioMcpClient(timeout=8.0)
    try:
        client.handshake()

        # 3.1 List Tools
        tools_resp = client.rpc_call(301, "tools/list", {})
        assert tools_resp is not None and "result" in tools_resp
        tools = tools_resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        results["registered_tools_count"] = len(tool_names)
        results["registered_tool_names"] = sorted(tool_names)

        expected_native_tools = [
            "control_catalog_reading",
            "get_catalog_reading_status",
            "get_catalog_skeleton_views",
            "get_catalog_theme_candidates",
            "get_catalog_understanding",
            "query_catalog_content",
            "query_catalog_understanding",
            "request_catalog_deep_reading",
            "request_catalog_initial_reading",
            "retry_catalog_initial_reading",
        ]
        assert sorted(tool_names) == sorted(expected_native_tools), f"Surface mismatch: {tool_names}"

        # 3.2 Schema checks
        schemas = {}
        for tool in tools:
            name = tool["name"]
            schema = tool.get("inputSchema", {})
            assert schema.get("type") == "object", f"Tool {name} inputSchema not object"
            schemas[name] = {
                "description_preview": (tool.get("description") or "")[:80] + "...",
                "properties": list(schema.get("properties", {}).keys()),
                "required": schema.get("required", [])
            }
        results["schemas"] = schemas

        # 3.3 Execution of get_catalog_reading_status
        r_status = client.rpc_call(302, "tools/call", {
            "name": "get_catalog_reading_status",
            "arguments": {"section": "overview"}
        })
        assert r_status is not None and not r_status.get("result", {}).get("isError")
        status_text = r_status["result"]["content"][0]["text"]
        status_obj = json.loads(status_text)
        assert "overview" in status_obj
        results["exec_get_catalog_reading_status"] = {
            "status": "PASS",
            "window": status_obj["overview"]["policy"].get("window"),
            "queue_pending": status_obj["overview"].get("queue_pending")
        }

        # 3.4 Execution of get_catalog_theme_candidates
        t_cand_start = time.perf_counter()
        r_cand = client.rpc_call(303, "tools/call", {
            "name": "get_catalog_theme_candidates",
            "arguments": {"query_json": json.dumps({"limit": 2})}
        }, timeout=70.0)
        cand_duration = time.perf_counter() - t_cand_start
        print(f"DEBUG: r_cand completed in {cand_duration:.2f}s! Result preview: {str(r_cand)[:150]}", flush=True)
        assert r_cand is not None and not r_cand.get("result", {}).get("isError"), f"r_cand error: {r_cand}"
        cand_text = r_cand["result"]["content"][0]["text"]
        cand_obj = json.loads(cand_text)
        assert "items" in cand_obj
        results["exec_get_catalog_theme_candidates"] = {
            "status": "PASS",
            "items_returned": len(cand_obj["items"]),
            "applied_merges": cand_obj.get("applied_merges")
        }

        # 3.5 Execution of query_catalog_understanding
        r_under = client.rpc_call(304, "tools/call", {
            "name": "query_catalog_understanding",
            "arguments": {"query_json": json.dumps({"limit": 2})}
        })
        assert r_under is not None and not r_under.get("result", {}).get("isError")
        under_text = r_under["result"]["content"][0]["text"]
        under_obj = json.loads(under_text)
        assert "total" in under_obj
        results["exec_query_catalog_understanding"] = {
            "status": "PASS",
            "total_papers": under_obj["total"],
            "returned_items": len(under_obj.get("items", []))
        }

        # 3.6 Execution of query_catalog_content (hybrid search)
        t_content_start = time.perf_counter()
        r_content = client.rpc_call(305, "tools/call", {
            "name": "query_catalog_content",
            "arguments": {"query_json": json.dumps({"query": "reinforcement learning microgrid", "limit": 2})}
        }, timeout=70.0)
        content_duration = time.perf_counter() - t_content_start
        print(f"DEBUG: r_content completed in {content_duration:.2f}s! Result preview: {str(r_content)[:150]}", flush=True)
        assert r_content is not None and not r_content.get("result", {}).get("isError")
        content_text = r_content["result"]["content"][0]["text"]
        content_obj = json.loads(content_text)
        assert "matches" in content_obj
        results["exec_query_catalog_content"] = {
            "status": "PASS",
            "duration_s": round(content_duration, 2),
            "total_matches": content_obj.get("total_matches"),
            "returned_matches": len(content_obj["matches"]),
            "search_mode": content_obj.get("search_mode")
        }

        # 3.7 Execution of get_catalog_understanding for sample paper
        sample_paper = "paper_0075702bbd78cbb86485045659cde814"
        t_paper_start = time.perf_counter()
        r_paper = client.rpc_call(306, "tools/call", {
            "name": "get_catalog_understanding",
            "arguments": {"paper_id": sample_paper, "section": "overview"}
        }, timeout=70.0)
        paper_duration = time.perf_counter() - t_paper_start
        print(f"DEBUG: r_paper completed in {paper_duration:.2f}s! Result preview: {str(r_paper)[:150]}", flush=True)
        assert r_paper is not None and not r_paper.get("result", {}).get("isError")
        paper_text = r_paper["result"]["content"][0]["text"]
        paper_obj = json.loads(paper_text)
        assert "understanding" in paper_obj
        results["exec_get_catalog_understanding"] = {
            "status": "PASS",
            "paper_id": sample_paper,
            "has_understanding": bool(paper_obj.get("understanding")),
            "detail_available": paper_obj.get("detail_available")
        }

        # 3.8 Execution of get_catalog_skeleton_views for sample paper
        r_skel = client.rpc_call(307, "tools/call", {
            "name": "get_catalog_skeleton_views",
            "arguments": {"paper_id": sample_paper, "section": "overview"}
        })
        assert r_skel is not None and not r_skel.get("result", {}).get("isError")
        skel_text = r_skel["result"]["content"][0]["text"]
        skel_obj = json.loads(skel_text)
        results["exec_get_catalog_skeleton_views"] = {
            "status": "PASS",
            "paper_id": sample_paper,
            "content_views_count": len(skel_obj.get("content_views", [])),
            "purpose_judgments_count": len(skel_obj.get("purpose_judgments", []))
        }

        # 3.9 Prompt tool name mapping probe
        dispatch_alternate_names = [
            ("list_catalog_reading_papers", "query_catalog_understanding"),
            ("get_catalog_paper_record", "get_catalog_understanding"),
            ("search_catalog_understanding_content", "query_catalog_content"),
            ("get_catalog_understanding_status", "get_catalog_reading_status"),
            ("list_catalog_skeleton_views", "get_catalog_skeleton_views"),
            ("get_catalog_skeleton_view_detail", "get_catalog_skeleton_views(section='complete')"),
            ("list_catalog_skeleton_theme_observations", "get_catalog_understanding(section='theme:...')"),
            ("get_catalog_candidate_links", "get_catalog_theme_candidates"),
        ]
        prompt_probe = {}
        for alt_name, native_equiv in dispatch_alternate_names:
            r = client.rpc_call(350, "tools/call", {"name": alt_name, "arguments": {}})
            prompt_probe[alt_name] = {
                "cleanly_rejected": bool(r and ("error" in r or r.get("result", {}).get("isError"))),
                "native_equivalent_tool": native_equiv
            }
        results["prompt_tool_name_parity_analysis"] = prompt_probe

    finally:
        client.close()

    return results


# ==============================================================================
# SECTION 4: CONCURRENT SUBPROCESS STRESS
# ==============================================================================

def run_single_client_stress(client_id: int, queries_count: int = 3) -> dict[str, Any]:
    """Run interleaved queries in a dedicated stdio subprocess."""
    client = StdioMcpClient(timeout=10.0)
    latencies = []
    errors = []
    t_start = time.perf_counter()
    try:
        client.handshake()
        for i in range(queries_count):
            t0 = time.perf_counter()
            r1 = client.rpc_call(client_id * 100 + i * 3 + 1, "tools/call", {
                "name": "get_catalog_reading_status",
                "arguments": {"section": "overview"}
            })
            if r1 is None or r1.get("result", {}).get("isError") or "error" in r1:
                errors.append(f"Client {client_id} call 1 failed: {r1}")

            r2 = client.rpc_call(client_id * 100 + i * 3 + 2, "tools/call", {
                "name": "query_catalog_understanding",
                "arguments": {"query_json": json.dumps({"limit": 1})}
            })
            if r2 is None or r2.get("result", {}).get("isError") or "error" in r2:
                errors.append(f"Client {client_id} call 2 failed: {r2}")

            r3 = client.rpc_call(client_id * 100 + i * 3 + 3, "tools/call", {
                "name": "get_catalog_theme_candidates",
                "arguments": {"query_json": json.dumps({"limit": 1})}
            })
            if r3 is None or r3.get("result", {}).get("isError") or "error" in r3:
                errors.append(f"Client {client_id} call 3 failed: {r3}")

            latencies.append(time.perf_counter() - t0)
    finally:
        client.close()

    return {
        "client_id": client_id,
        "completed_queries": queries_count * 3,
        "total_time_s": round(time.perf_counter() - t_start, 3),
        "avg_roundtrip_latency_s": round(sum(latencies) / len(latencies), 4) if latencies else 0,
        "errors": errors,
    }


def test_concurrent_subprocess_calls(concurrency: int = 3, queries_per_client: int = 2) -> dict[str, Any]:
    """Spawn multiple concurrent stdio processes and verify no database lock or deadlocks."""
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(run_single_client_stress, idx, queries_per_client)
            for idx in range(concurrency)
        ]
        client_results = [f.result() for f in futures]
    t1 = time.perf_counter()

    all_errors = []
    total_queries = 0
    for cr in client_results:
        all_errors.extend(cr["errors"])
        total_queries += cr["completed_queries"]

    # Verify SQLite database integrity after concurrent stress
    conn = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro", uri=True)
    integrity = conn.execute("PRAGMA integrity_check").fetchall()
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    return {
        "concurrency": concurrency,
        "total_queries_executed": total_queries,
        "elapsed_wall_time_s": round(t1 - t0, 3),
        "qps": round(total_queries / (t1 - t0), 2),
        "total_errors": len(all_errors),
        "error_messages": all_errors,
        "catalog_db_integrity": integrity[0][0] if integrity else "EMPTY",
        "catalog_db_journal_mode": journal_mode,
        "clients": client_results,
    }


# ==============================================================================
# MAIN RUNNER
# ==============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", type=int, choices=[0, 1, 2, 3, 4], default=0)
    args = parser.parse_args()

    print("=" * 80, flush=True)
    print("FASTMCP PROTOCOL ADVERSARIAL CHALLENGER SUITE", flush=True)
    print("Target Runner: run-scholar-catalog-mcp.py", flush=True)
    print("Target DB: catalog.db (read-only mode)", flush=True)
    print("=" * 80, flush=True)

    summary = {}

    if args.section in (0, 1):
        print("\n[1/4] Running Protocol Fuzzing...", flush=True)
        t0 = time.perf_counter()
        summary["protocol_fuzzing"] = test_protocol_fuzzing()
        print(f"Protocol Fuzzing finished in {time.perf_counter() - t0:.2f}s", flush=True)
        print(json.dumps(summary["protocol_fuzzing"], indent=2), flush=True)

    if args.section in (0, 2):
        print("\n[2/4] Running Input Bound Fuzzing...", flush=True)
        t0 = time.perf_counter()
        summary["input_bound_fuzzing"] = test_input_bound_fuzzing()
        print(f"Input Bound Fuzzing finished in {time.perf_counter() - t0:.2f}s", flush=True)
        print(json.dumps(summary["input_bound_fuzzing"], indent=2), flush=True)

    if args.section in (0, 3):
        print("\n[3/4] Running Tool Surface Verification...", flush=True)
        t0 = time.perf_counter()
        summary["tool_surface_verification"] = test_tool_surface_verification()
        print(f"Tool Surface Verification finished in {time.perf_counter() - t0:.2f}s", flush=True)
        print(json.dumps(summary["tool_surface_verification"], indent=2), flush=True)

    if args.section in (0, 4):
        print("\n[4/4] Running Concurrent Subprocess Stress...", flush=True)
        t0 = time.perf_counter()
        summary["concurrent_subprocess_stress"] = test_concurrent_subprocess_calls(concurrency=3, queries_per_client=2)
        print(f"Concurrent Subprocess Stress finished in {time.perf_counter() - t0:.2f}s", flush=True)
        print(json.dumps(summary["concurrent_subprocess_stress"], indent=2), flush=True)

    print("\n" + "=" * 80, flush=True)
    print("ADVERSARIAL CHALLENGE EXECUTION SUMMARY", flush=True)
    print("=" * 80, flush=True)
    print(f"ALL SECTIONS COMPLETED: {list(summary.keys())}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
