"""Replay the native Skeleton handler against read-only, located parser artifacts.

This is a diagnostic, not a scientific accuracy benchmark. It never instantiates
AcquisitionService, claims production jobs, or publishes to Catalog/FieldKG.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .acquisition_worker import AcquisitionWorker
from .model_gateway import CONTRACTS, UnlimitedLLMGateway
from .parser_quality import normalize_mineru_result


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def select_blocks(blocks: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Choose bounded prose spread across the paper, without inventing labels."""
    if count < 1:
        raise ValueError("The number of sampled blocks must be positive")
    eligible = [
        block for block in blocks
        if block.get("block_type", "TEXT") == "TEXT"
        and 250 <= len(str(block.get("text") or "")) <= 2400
        and block.get("section") != "Back matter"
    ]
    if not eligible:
        raise ValueError("No bounded prose blocks are available in this document")
    count = min(count, len(eligible))
    indices = (
        [0] if count == 1
        else [round(index * (len(eligible) - 1) / (count - 1)) for index in range(count)]
    )
    return [eligible[index] for index in indices]


class RecordingGateway:
    """Save actual requests, responses, model receipts and latency after every call."""

    def __init__(self, gateway: Any, journal: Path) -> None:
        self.gateway = gateway
        self.journal = journal
        self.calls: list[dict[str, Any]] = []
        self.cached: dict[str, dict[str, Any]] = {}
        if journal.exists():
            for line in journal.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if record.get("status") == "SUCCESS":
                    self.cached[record["request_digest"]] = record

    def analyze(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        version = CONTRACTS[task].version
        request_digest = _digest([task, version, CONTRACTS[task].instruction, payload])
        if request_digest in self.cached:
            record = copy.deepcopy(self.cached[request_digest])
            record["reused"] = True
            self.calls.append(record)
            return copy.deepcopy(record["result"])
        record: dict[str, Any] = {
            "task": task, "prompt_version": version, "request_digest": request_digest,
            "input": copy.deepcopy(payload), "status": "STARTED", "reused": False,
        }
        started = time.monotonic()
        try:
            result = self.gateway.analyze(task, payload)
            record.update(status="SUCCESS", result=copy.deepcopy(result))
        except Exception as exc:
            record.update(status="FAILED", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            self.calls.append(record)
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{task}: {record['status']} ({record['elapsed_seconds']}s)", flush=True)
        self.cached[request_digest] = record
        return result


class CapturePublication:
    def __init__(self) -> None:
        self.units: list[dict[str, Any]] = []

    def publish_skeleton_result(
        self, parse_run_id: str, units: list[dict[str, Any]], *, model_name: str | None,
        job_id: str | None = None, worker_id: str | None = None,
        fencing_token: int | None = None,
    ) -> dict[str, Any]:
        if (job_id, worker_id, fencing_token) != ("audit-only", "audit-only", 0):
            raise ValueError("Replay publication requires its explicit non-database audit context")
        self.units = copy.deepcopy(units)
        return {"skeleton_run_id": "audit-only", "units": len(units), "published": False}


def replay_native_handler(
    blocks: list[dict[str, Any]], gateway: RecordingGateway,
) -> dict[str, Any]:
    """Execute the real handler, replacing only its DB reads and publication sink."""
    worker = AcquisitionWorker.__new__(AcquisitionWorker)
    sink = CapturePublication()
    worker.service = sink
    worker.model = gateway
    worker.worker_id = "audit-only"
    worker._parse_blocks = lambda _parse_run_id, _paper_id=None: copy.deepcopy(blocks)
    # Diagnostic receipts belong to the explicit file journal, never a production Catalog.
    worker._analyze = lambda _job, task, payload, _parse_run_id=None: gateway.analyze(task, payload)
    worker._handle_skeleton({"paper_id": "audit-only", "job_id": "audit-only", "fencing_token": 0}, {"parse_run_id": "audit-only"})
    units = sink.units
    return {
        "units": units,
        "calls": gateway.calls,
        "models": sorted({
            str(call.get("result", {}).get("_contract", {}).get("actual_model"))
            for call in gateway.calls if call.get("status") == "SUCCESS"
        }),
        "diagnostics": diagnose_result(units, gateway.calls),
    }


def diagnose_result(
    units: list[dict[str, Any]], calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Inspect saved receipts without calling the model or changing the evidence."""
    role_missing = [
        unit["block_id"] for unit in units
        if not (unit["layer4"].get("role") or unit["layer4"].get("label"))
    ]
    dropped_nested_triplets = []
    for unit in units:
        nested = [
            triplet for proposition in unit["layer1"].get("propositions", [])
            if isinstance(proposition, dict)
            for triplet in proposition.get("triplets", [])
            if isinstance(triplet, dict)
            and all(triplet.get(key) for key in ("subject", "predicate", "object"))
        ]
        if nested:
            dropped_nested_triplets.append({
                "block_id": unit["block_id"], "nested_valid_triplets": len(nested),
                "reason": "Canonical publication reads only layer1.triplets",
            })
    return {
        "missing_storage_compatible_l4_role": role_missing,
        "nested_triplets_ignored_by_publication": dropped_nested_triplets,
        "l4_receives_section": any(
            "section" in call["input"]
            for call in calls if call["task"] == "skeleton_layer_4"
        ),
        "l4_receives_document_outline": any(
            "document_outline" in call["input"]
            for call in calls if call["task"] == "skeleton_layer_4"
        ),
        "scientific_accuracy": "NOT_MEASURED_REQUIRES_REFERENCE_ANNOTATIONS",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=1, help="One-based parser audit sample")
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run", action="store_true", help="Call the configured model gateway")
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    if not 1 <= args.sample <= len(audit["results"]):
        parser.error("Sample index is outside the parser audit")
    sample = audit["results"][args.sample - 1]
    content = Path(sample["content_path"])
    pdf = Path(sample["pdf_path"])
    markdown = content.with_name(content.name.removesuffix("_content_list.json") + ".md")
    normalized = normalize_mineru_result({"manifest": {
        "content_list_path": str(content), "markdown_path": str(markdown),
    }}, source_pdf_path=pdf)
    selected = select_blocks(normalized["blocks"], args.blocks)
    for block in selected:
        block["block_id"] = "audit_" + _digest([str(content), block["sequence"]])[:16]
    report: dict[str, Any] = {
        "mode": "NATIVE_HANDLER_DIAGNOSTIC", "status": "PREPARED",
        "paper": sample["name"], "source_content_path": str(content),
        "source_pdf_path": str(pdf),
        "source_content_sha256": hashlib.sha256(content.read_bytes()).hexdigest(),
        "total_body_blocks": len(normalized["blocks"]), "sampled_blocks": selected,
        "parser_quality": normalized["manifest"]["quality"],
        "publication": "DISABLED", "quality_accepted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.run:
        recorder = RecordingGateway(
            UnlimitedLLMGateway(args.root), args.output.with_suffix(".calls.jsonl"),
        )
        try:
            report.update(replay_native_handler(selected, recorder), status="COMPLETED")
        except Exception as exc:  # noqa: BLE001 - retain failed model call evidence for diagnosis
            report.update(
                status="FAILED", error_type=type(exc).__name__, error=str(exc), calls=recorder.calls,
            )
        finally:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "paper": report["paper"], "status": report["status"],
        "body_blocks": report["total_body_blocks"], "sampled_blocks": len(selected),
        "models": report.get("models"), "diagnostics": report.get("diagnostics"),
        "output": str(args.output),
    }, ensure_ascii=False), flush=True)
    if report["status"] == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
