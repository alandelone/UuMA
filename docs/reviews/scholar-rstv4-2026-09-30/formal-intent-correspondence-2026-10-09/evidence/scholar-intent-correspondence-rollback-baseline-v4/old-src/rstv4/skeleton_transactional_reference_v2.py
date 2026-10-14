"""Pinpoint omitted source-claim explanations without relaxing transaction validation."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_dspy import json_text
from rstv4.skeleton_mapped_graph_v2 import read
from rstv4.skeleton_transactional_reference import (
    TransactionalGraphPredictor,
    TransactionalVerifiedReferenceBuilder,
)

DIAGNOSTIC_REFERENCE_VERSION = "exact-post-operation-empty-claim-domain-diagnostic-v1"


def omission_diagnostic(record: dict) -> dict:
    edges = copy.deepcopy(record["original_graph"]["edges"])
    patch = record["patch"]
    for key, operation in patch["repairs"].items():
        if operation["action"] == "REMOVE":
            del edges[key]
        else:
            edges[key] = operation["replacement"]
    edges.update(patch["additional_edges"])
    required = set(record["original_graph"]["connections"]) - {
        edge["source_reference_id"] for edge in edges.values()
    }
    reasons = patch["empty_claim_rationales"]
    return {"protocol_version": DIAGNOSTIC_REFERENCE_VERSION,
            "required_empty_claim_ids": sorted(required),
            "missing_claim_ids": sorted(required - reasons.keys()),
            "unexpected_claim_ids": sorted(reasons.keys() - required),
            "invalid_rationale_claim_ids": sorted(key for key, value in reasons.items()
                if not isinstance(value, str) or len(value.strip()) < 20)}


class SpecificOmissionGraphPredictor(TransactionalGraphPredictor):
    def __call__(self, **values: str) -> Any:
        try:
            return super().__call__(**values)
        except SourceContractError as exc:
            if not str(exc).startswith("Repair needs concrete rationales for all and only empty"):
                raise
            record = read(self.output / "correction-patches" / f"{digest(values)}.json")
            diagnostic = omission_diagnostic(record)
            raise SourceContractError(str(exc) + ". Exact declared-operation domain: "
                                      + json_text(diagnostic)) from exc


class SpecificOmissionVerifiedReferenceBuilder(TransactionalVerifiedReferenceBuilder):
    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.corrector = SpecificOmissionGraphPredictor(output)
