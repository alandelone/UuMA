"""Unexecuted G11 preparation and read-only audit; never serves or calls a model.

Main operator, through the managed session wrapper:
  ... scholar-all11-g11-current-v2.py prepare
  ... scholar-all11-g11-current-v2.py audit

Preparation is exclusive and cannot be replayed after success OR partial failure.
Audit writes only a new evidence file; it does not execute business guards.
Native observations and the four stage/one Method refusals remain separate work.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]
RST = REPO.parent / "RSTV4"
HERE = REPO / ".tmp/scholar-all11-g11-current-v2"
TEMP = Path("C:/Users/Alandelone/AppData/Local/Temp")
VECTOR = REPO / ".tmp/scholar-same-origin-v1/source-before.json"
CONTEXT = REPO / ".tmp/scholar-all11-context-v2/receipt.json"
SCHEMA_REFERENCE = REPO / ".tmp/scholar-all11-native-v1/protected-source110.json"
DISCUSSION_TABLES = {
    "research_discussion_annotations", "research_discussion_jobs",
    "research_discussion_messages", "research_discussion_requests",
}
SOURCES = {
    "success": {
        "root": TEMP / "scui-g11-native-22n_zg_d", "count": 106, "version": 14,
        "snapshot": REPO / ".tmp/scholar-quickread-native-preview-v2/terminal106-all-tables.json",
    },
    "identity": {
        "root": TEMP / "scui-g11-identity-20jvto03", "count": 105, "version": 13,
        "snapshot": REPO / ".tmp/scholar-g11-identity-native-v1/final-all-tables.json",
    },
    "upstream": {
        "root": TEMP / "scui-g11-upstream-copy-j6xdmqml", "count": 105, "version": 13,
        "snapshot": REPO / ".tmp/scholar-g11-upstream-native-prepare-v1/owned-after-refusal-all-tables.json",
    },
}
HISTORICAL = TEMP / "scholar-formal-gates-z2aa267y"
HISTORICAL_SNAPSHOT = REPO / ".tmp/scholar-g11-upstream-native-prepare-v1/historical-all-tables.json"
PAPER = "paper_dde0a449e93444c2771e7b0edeb7daf9"
FILE = "source_file_491d18ddee7958c95deb123a188280d5"
PDF_SHA = "85f4078a0ae99a5c0b13894ce4bbf511c7e9302958512e738b7180dae1110f99"
GPU = "job_76d39031d8cc329ec431e6a896a08f54"
QUICK = "job_fe4651959298eab54d88abd9edaf6760"
PARSE = "parse_run_bb2661e7c11bb18dd684661073472d71"
COLLECTION = "collection_62ca47c927342115eb5f8fd870af9ca6"
TRACK = "track_19bd9c2c7abb40d48013dd0e0374e4fd"
METHOD = "method_578417c4dcfc42e99060150cccd53613"
CLAIMS = ("claim_bb84d9ba73be4451a3b4222d941427e2", "claim_5fdad5a7be7144aca7ff828926d00e11")
REVIEW_MS = "manuscript_fde24662e8b044c59e729f7516ad10ca"
PLAN = "experiment_plan_81163acc4ada40c786e62a8e66576d9d"
ZERO = {
    "manuscript_264202f005144e1ba60f8574c6637f70": ("DRAFTING", "WHOLE_PAPER_REVIEW"),
    "manuscript_d24e458d188e42449fb25c1d65affc29": ("WHOLE_PAPER_REVIEW", "FINALIZATION_SUBMISSION"),
    "manuscript_ed7c93ebf4824ec48186d731583185c8": ("FINALIZATION_SUBMISSION", "REVISION"),
    "manuscript_332d6e2945cd4c30b4d39fcae921e28a": ("FINALIZATION_SUBMISSION", "PUBLICATION"),
}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def put(name: str, value) -> None:
    with (HERE / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def row_order(value) -> str:
    # Exact original runtime_copy_and_serve.snapshot ordering, NOT SQL row order.
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def snapshot(db: Path) -> dict:
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        schema = [list(r) for r in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        )]
        tables = {}
        for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [r[1] for r in conn.execute("PRAGMA table_info(" + quoted + ")")]
            rows = [[{"__blob__": v.hex()} if isinstance(v, bytes) else v for v in row]
                    for row in conn.execute("SELECT * FROM " + quoted)]
            tables[name] = {"columns": columns, "rows": sorted(rows, key=row_order)}
        return {"schema": schema, "tables": tables}


def records(state: dict, table: str) -> list[dict]:
    value = state["tables"][table]
    return [dict(zip(value["columns"], row)) for row in value["rows"]]


def one(state: dict, table: str, key: str, value: str) -> dict:
    matches = [row for row in records(state, table) if row[key] == value]
    assert len(matches) == 1, (table, key, value, len(matches))
    return matches[0]


def filemap(root: Path) -> dict:
    # SQLite-managed sidecars are separately excluded; no payload file is excluded.
    result = {}
    for path in sorted(root.rglob("*")):
        assert not path.is_symlink(), "Do not follow a source symlink"
        if path.is_file() and not path.name.endswith(("-wal", "-shm")):
            assert path.resolve().is_relative_to(root.resolve())
            result[path.relative_to(root).as_posix()] = {"sha256": sha(path), "bytes": path.stat().st_size}
    return result


def source_guard() -> dict:
    vector = read(VECTOR)
    assert len(vector) == 421, "Use the established complete source421 vector"
    for name, digest in vector.items():
        path = Path(name).resolve()
        assert path.is_relative_to(RST.resolve()) or path.is_relative_to((REPO.parent / "writing-studio").resolve())
        assert sha(path) == digest, "Source421 changed: " + str(path)
    context = read(CONTEXT)
    for name, digest in context["backend_source_vector"].items():
        assert sha(RST / name) == digest, name
    for name, digest in context["frontend_product_vector"].items():
        assert sha(REPO.parent / "writing-studio" / name) == digest, name
    return {"count": len(vector), "vector_path": str(VECTOR), "vector_sha256": sha(VECTOR),
            "context_receipt_sha256": sha(CONTEXT), "helper_sha256": sha(Path(__file__)),
            "schema_reference_sha256": sha(SCHEMA_REFERENCE)}


def matches_sealed(current: dict, expected: dict) -> None:
    if "tables" in expected:
        assert current == expected, "Canonical schema/columns/row snapshot differs from retained evidence"
        return
    # The old upstream helper stored all tables as unsorted list[dict], no schema.
    # Preserve every actual field/value. Table names and column order come from SQL,
    # not inferred from the first row (empty tables have no row to infer from).
    assert set(current["tables"]) == set(expected)
    for name, rows in expected.items():
        assert sorted(records(current, name), key=row_order) == sorted(rows, key=row_order), name


def binding(role: str, state: dict, root: Path) -> dict:
    if role in {"success", "identity"}:
        source = one(state, "source_file_versions", "file_version_id", FILE)
        assert source["paper_id"] == PAPER and source["sha256"] == PDF_SHA and source["size_bytes"] == 1827
        assert source["identity_status"] == "VERIFIED"
        original_path = Path(source["storage_path"]).resolve()
        assert sha(original_path) == PDF_SHA and original_path.stat().st_size == 1827
        gpu = one(state, "acquisition_jobs", "job_id", GPU)
        assert (gpu["status"], gpu["attempts"], gpu["fencing_token"]) == ("SUCCEEDED", 6, 6)
        quick = one(state, "acquisition_jobs", "job_id", QUICK)
        collection = one(state, "collections", "collection_id", COLLECTION)
        assert one(state, "parse_runs", "parse_run_id", PARSE)["status"] == "SUCCEEDED"
        if role == "success":
            assert (quick["status"], quick["attempts"], quick["fencing_token"]) == ("SUCCEEDED", 1, 1)
            assert len(records(state, "acquisition_model_call_events")) == 34
            assessment = one(state, "paper_assessments", "assessment_id", "assessment_2663f1581433c6e731b80ff6eca5113f")
            assert assessment["status"] == "COMPLETED" and assessment["assessment_type"] == "QUICK_READ"
            events = [r for r in records(state, "acquisition_model_call_events") if r["job_id"] == QUICK]
            assert len(events) == 2 and {r["event_kind"] for r in events} == {"STARTED", "RETURNED"}
            assert {r["fencing_token"] for r in events} == {1}
            assert collection["status"] == "ACTIVE" and collection["revision"] == 4
            assert one(state, "collections", "collection_id", "collection_d016024afda6fbf0ce956023f80306a8")["status"] == "PAUSED"
        else:
            assert (quick["status"], quick["attempts"]) == ("READY", 0)
            assert one(state, "acquisition_jobs", "job_id", "job_ce6c4d42d5f07ead8f5bd6d21189427c")["status"] == "READY"
            action = one(state, "catalog_review_actions", "action_id", "review_action_e440f948f21f589b155e4a7e5fe12d79")
            assert action["action_kind"] == "APPROVE_IDENTITY"
            assert action["supersedes_action_id"] == "review_action_d51a5e2c83e99360a695ecb894f0d452"
        return {"root": str(root), "paper_id": PAPER, "file_version_id": FILE,
                "collection_id": COLLECTION, "gpu_job_id": GPU, "quickread_job_id": QUICK,
                "quickread_status_in_this_root": quick["status"], "parse_run_id": PARSE,
                "original_pdf_path": str(original_path), "original_pdf_sha256": PDF_SHA,
                "do_not_reexecute_models_or_approval": True}
    method = one(state, "research_nodes", "node_id", METHOD)
    assert (method["track_id"], method["status"], method["revision"]) == (TRACK, "SUPERSEDED", 2)
    for claim in CLAIMS:
        row = one(state, "research_nodes", "node_id", claim)
        assert (row["track_id"], row["status"], row["revision"]) == (TRACK, "STALE", 2)
    manuscript = one(state, "manuscripts", "manuscript_id", REVIEW_MS)
    assert manuscript["needs_scientific_review"] == 1 and manuscript["revision"] == 2
    assert one(state, "manuscript_nodes", "manuscript_id", REVIEW_MS)["node_revision"] == 1
    assert one(state, "experiment_plans", "plan_id", PLAN)["method_node_id"] == METHOD
    cases = []
    for ms, (stage, target) in ZERO.items():
        row = one(state, "manuscripts", "manuscript_id", ms)
        doc = one(state, "studio_documents", "manuscript_id", ms)
        assert row["workflow_stage"] == stage and row["revision"] == 1
        assert doc["active_generated_version_id"] is None
        assert not [r for r in records(state, "manuscript_versions") if r["manuscript_id"] == ms]
        cases.append({"manuscript_id": ms, "retained_stage": stage, "target": target,
                      "expected_revision": 1, "endpoint": f"/api/manuscripts/{ms}/stage",
                      "expected_status": 422, "reason": "G11 explicit zero-version software guard only"})
    return {"root": str(root), "track_id": TRACK, "method_id": METHOD, "stale_claim_ids": CLAIMS,
            "review_manuscript_id": REVIEW_MS, "old_plan_id": PLAN, "zero_version_cases": cases,
            "native_experiment_button_disabled_is_distinct_from_core_refusal": True,
            "successful_terminal_run_do_not_repeat": "run_d79366ed2ce545f08eddb3aee9b5014f"}


def literal_schema(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    candidates = [node.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets)]
    assert len(candidates) == 1
    value = ast.literal_eval(candidates[0])
    assert isinstance(value, str)
    return value


def verify_migration(before: dict, after: dict, version_before: int) -> dict:
    added = DISCUSSION_TABLES | ({"studio_submission_bindings"} if version_before == 13 else set())
    assert set(after["tables"]) - set(before["tables"]) == added
    assert len(after["tables"]) == 110
    assert set(before["tables"]).issubset(after["tables"])
    for name, original in before["tables"].items():
        if name != "schema_version" or version_before == 14:
            assert after["tables"][name] == original, "Old table changed: " + name
        else:
            old = records(before, name)
            new = records(after, name)
            assert len(old) == len(new) == 1
            assert old[0]["component"] == new[0]["component"] == "catalog"
            assert old[0]["version"] == 13 and new[0]["version"] == 14
            assert before["tables"][name]["columns"] == after["tables"][name]["columns"]
            assert set(old[0]) == set(new[0]) == {"component", "version", "applied_at"}
    assert all(after["tables"][name]["rows"] == [] for name in added)
    old_objects = {(r[0], r[1]): r for r in before["schema"]}
    new_objects = {(r[0], r[1]): r for r in after["schema"]}
    assert all(new_objects.get(key) == value for key, value in old_objects.items()), "Old schema changed"
    appended = [value for key, value in new_objects.items() if key not in old_objects]
    expected = [r for r in read(SCHEMA_REFERENCE)["schema"] if r[2] in added]
    assert appended == expected, "New schema objects differ from current native110 contract"
    return {"old_tables": len(before["tables"]), "current_tables": len(after["tables"]),
            "new_empty_tables": sorted(added), "all_old_schema_and_columns_exact": True,
            "all_old_rows_exact_except_declared_schema_version": True,
            "schema_version_before": records(before, "schema_version"),
            "schema_version_after": records(after, "schema_version")}


def guard_originals(receipt: dict) -> None:
    assert source_guard() == receipt["source421"]
    for role in [*SOURCES, "historical"]:
        original = receipt["originals"][role]
        assert sha(Path(original["sealed_snapshot"])) == original["sealed_snapshot_sha256"]
        root = Path(original["root"])
        assert filemap(root) == read(HERE / f"{role}-source-files.json"), "Original bytes changed: " + role
        assert snapshot(root / "data/catalog.db") == read(HERE / f"{role}-source-tables.json"), "Original tables changed: " + role


def prepare() -> None:
    source = source_guard()  # Fail before creating any output if source421 drifted.
    HERE.mkdir(exist_ok=False)  # Also blocks replay after a partially failed copy.
    put("attempt.json", {"status": "EXCLUSIVE_PREPARATION_STARTED_DO_NOT_REPLAY", "source421": source,
                         "at": datetime.now(timezone.utc).isoformat()})
    originals = {}
    for role, spec in {**SOURCES, "historical": {"root": HISTORICAL, "snapshot": HISTORICAL_SNAPSHOT, "count": 83, "version": 5}}.items():
        root = spec["root"].resolve()
        assert root.parent == TEMP.resolve()
        before_files = filemap(root)
        state = snapshot(root / "data/catalog.db")
        assert filemap(root) == before_files, "Concurrent original change during snapshot"
        assert len(state["tables"]) == spec["count"]
        matches_sealed(state, read(spec["snapshot"]))
        assert records(state, "schema_version")[0]["version"] == spec["version"]
        put(f"{role}-source-files.json", before_files)
        put(f"{role}-source-tables.json", state)
        originals[role] = {"root": str(root), "sealed_snapshot": str(spec["snapshot"]),
                           "sealed_snapshot_sha256": sha(spec["snapshot"])}
        if role != "historical":
            put(f"{role}-source-binding.json", binding(role, state, root))
    receipt = {"source421": source, "originals": originals, "copies": {},
               "models_workers_jobs_approvals_executed": 0, "native_acceptance_executed": False,
               "final_integrated_proven": False, "all118_complete": False}
    guard_originals(receipt)
    sys.path.insert(0, str(RST / "src"))
    from rstv4.database import CATALOG_VERSION, initialize_catalog
    assert CATALOG_VERSION == 14
    discussion_sql = literal_schema(RST / "src/rstv4/research_discussions.py")
    for role, spec in SOURCES.items():
        root = Path(tempfile.mkdtemp(prefix=f"scui-all11-g11-{role}-")).resolve()
        put(f"{role}-allocation.json", {"root": str(root), "source_root": str(spec["root"]), "resume_or_recopy_automatically": False})
        original = spec["root"].resolve()
        protected = read(HERE / f"{role}-source-files.json")
        for relative, metadata in protected.items():
            if relative == "data/catalog.db":
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original / relative, target)
            assert sha(target) == metadata["sha256"]
        target_db = root / "data/catalog.db"
        target_db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect((original / "data/catalog.db").as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(target_db)) as dst:
                src.backup(dst)
        before = snapshot(target_db)
        assert before == read(HERE / f"{role}-source-tables.json")
        copied_files = filemap(root)
        assert set(copied_files) == set(protected)
        assert all(copied_files[name] == meta for name, meta in protected.items() if name != "data/catalog.db")
        put(f"{role}-before-migration.json", before)
        put(f"{role}-before-migration-files.json", copied_files)
        initialize_catalog(target_db)  # Official schema migration, copy only; no service constructors.
        with closing(sqlite3.connect(target_db)) as conn, conn:
            conn.executescript(discussion_sql)  # Literal current schema; no service/gateway import.
        after = snapshot(target_db)
        migration = verify_migration(before, after, spec["version"])
        initialize_catalog(target_db)
        with closing(sqlite3.connect(target_db)) as conn, conn:
            conn.executescript(discussion_sql)
        assert snapshot(target_db) == after, "Current initialization must be idempotent"
        current_files = filemap(root)
        added_files = set(current_files) - set(copied_files)
        allowed_files = {"data/catalog.pre-v14.bak"} if spec["version"] == 13 else set()
        assert added_files.issubset(allowed_files) and not (set(copied_files) - set(current_files))
        assert all(current_files[name] == meta for name, meta in copied_files.items() if name != "data/catalog.db")
        put(f"{role}-migration.json", migration)
        put(f"{role}-baseline110.json", after)
        put(f"{role}-baseline-files.json", current_files)
        put(f"{role}-binding.json", binding(role, after, root))
        receipt["copies"][role] = {"root": str(root), "tables": 110, "migration": migration,
                                     "new_derived_files": sorted(added_files)}
        guard_originals(receipt)
    put("receipt.json", {**receipt, "status": "PREPARED_THREE_SOURCE421_COPIES_NO_NATIVE_ACCEPTANCE"})
    print("PREPARED_THREE_COPIES_NO_MODELS_NO_BUSINESS_REPLAY_NO_NATIVE_PASS", flush=True)


def audit() -> None:
    receipt = read(HERE / "receipt.json")
    guard_originals(receipt)
    bindings = {}
    for role, entry in receipt["copies"].items():
        root = Path(entry["root"])
        assert root.parent == TEMP.resolve() and root.name.startswith(f"scui-all11-g11-{role}-")
        state = snapshot(root / "data/catalog.db")
        assert state == read(HERE / f"{role}-baseline110.json"), "Copied business state/schema changed: " + role
        assert filemap(root) == read(HERE / f"{role}-baseline-files.json"), "Copied payload bytes changed: " + role
        bindings[role] = binding(role, state, root)
        assert bindings[role] == read(HERE / f"{role}-binding.json")
    guard_originals(receipt)
    name = "readonly-audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    put(name, {"status": "PASS_READONLY_SOURCE421_ORIGINALS_AND_THREE_COMPATIBLE_COPIES",
               "source421": receipt["source421"], "bindings": bindings,
               "originals_and_copies_all_tables_and_files_exact": True,
               "models_workers_jobs_approval_actions": 0, "native_observations_executed": False,
               "current_stage_or_method_refusals_executed": False, "final_integrated_proven": False})
    print("PASS_READONLY_SEMANTIC_BINDING_ONLY_NATIVE_AND_CURRENT_REFUSALS_REMAIN", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "audit"])
    args = parser.parse_args()
    {"prepare": prepare, "audit": audit}[args.mode]()
