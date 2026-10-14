"""Bounded evaluator recovery using a reversible identifier representation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .skeleton_contract import SourceContractError, digest
from .skeleton_dspy import write_json
from .skeleton_grounded_review import GroundedReviewer, score_grounded

RECOVERY_VERSION = "source-grounded-bijective-identifier-recovery-v2"


def alias_candidate(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Change only candidate identifier spelling; statements and evidence stay exact."""
    value = copy.deepcopy(candidate)
    original_ids = [atom["atom_id"] for record in value["block_atoms"] for atom in record["atoms"]]
    if len(original_ids) != len(set(original_ids)):
        raise SourceContractError("Cannot alias duplicate candidate identifiers")
    aliases = {f"c{index}": atom_id for index, atom_id in enumerate(original_ids)}
    reverse = {atom_id: alias for alias, atom_id in aliases.items()}
    for record in value["block_atoms"]:
        for atom in record["atoms"]:
            atom["atom_id"] = reverse[atom["atom_id"]]
    for record in value["intents"]:
        if record["atom_id"] not in reverse:
            raise SourceContractError("Intent points to an absent candidate identifier")
        record["atom_id"] = reverse[record["atom_id"]]
    for edge in value["relations"]:
        if edge["source_id"] not in reverse or edge["target_id"] not in reverse:
            raise SourceContractError("Relation points to an absent candidate identifier")
        edge["source_id"], edge["target_id"] = reverse[edge["source_id"]], reverse[edge["target_id"]]
    return value, aliases


def unalias_review(review: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    value = copy.deepcopy(review)
    for record in value["matches"] + value["atom_verdicts"]:
        atom_id = record["atom_id"]
        if atom_id is not None:
            if atom_id not in aliases:
                raise SourceContractError("Reviewer invented an identifier outside the exact alias map")
            record["atom_id"] = aliases[atom_id]
    return value


class EvaluatorRecovery:
    def __init__(self, output: Path, *, actual_model: str) -> None:
        self.output = output
        self.secondary = GroundedReviewer(output / "alias-review", actual_model=actual_model)

    def assess(
        self, inputs: dict[str, str], reference: dict[str, Any], candidate: dict[str, Any],
        primary: dict[str, Any],
    ) -> dict[str, Any]:
        key = digest({"version": RECOVERY_VERSION, "inputs": inputs, "reference": reference,
                      "candidate": candidate, "primary": primary})
        path = self.output / "assessments" / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        aliases: dict[str, str] = {}
        if primary.get("evaluation_contract_failure") and not candidate.get("error"):
            encoded, aliases = alias_candidate(candidate)
            secondary = self.secondary.assess(inputs, reference, encoded)
            if not secondary.get("contract_failure"):
                decoded = unalias_review(secondary["grounded_review"], aliases)
                report = score_grounded(json.loads(inputs["source_blocks"]), reference, candidate, decoded)
            else:
                report = copy.deepcopy(secondary)
            recovered = not report.get("contract_failure")
            method = "Bounded source review with bijective candidate identifier aliases"
        else:
            if not primary.get("contract_failure"):
                report = score_grounded(json.loads(inputs["source_blocks"]), reference,
                                        candidate, primary["grounded_review"])
            else:
                report = copy.deepcopy(primary)
            recovered = False
            method = "Primary source verdicts retained; no additional model call"
        report["evaluator_recovery"] = {
            "version": RECOVERY_VERSION, "primary_report_digest": digest(primary),
            "primary_contract_failure": bool(primary.get("contract_failure")),
            "recovered_contract_failure": recovered, "method": method,
            "identifier_aliases": aliases, "source_and_claim_content_unchanged": True,
            "candidate_reselection_or_extraction": False,
        }
        write_json(path, report)
        return report
