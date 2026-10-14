"""Replay complete unchanged source parents that already retain verified additions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from rstv4.skeleton_complete_reference import (
    COMPLETE_REFERENCE_VERSION,
    CompleteSourceGraphBuilder,
    verified_source_additions,
)
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_coverage_diagnostics import (
    CoverageDiagnosticPredictor,
    DiagnosticCompleteVerifiedReferenceBuilder,
)
from rstv4.skeleton_dspy import write_json
from rstv4.skeleton_experiment import ReferenceRelation
from rstv4.skeleton_graph_reference import alias_claims, edge_key
from rstv4.skeleton_mapped_graph_v2 import MAPPED_GRAPH_VERSION, read
from rstv4.skeleton_transactional_reference import (
    ReusableMappedSourceGraphBuilder,
    TransactionalVerifiedReferenceBuilder,
)

AUGMENTED_REUSE_VERSION = "exact-canonical-and-full-source-parent-verified-additions-v2"


def parent_covers_additions(parent: dict, inputs: dict, base: dict, ledger: list[dict]) -> bool:
    """Eligibility only; accepted parents still undergo all existing replay validators."""
    if (parent["inputs_digest"] != digest(inputs) or parent["candidate_access"] is not False
            or {**copy.deepcopy(parent["reference"]), "relations": []} != base):
        return False
    canonical = {edge_key(edge): edge for edge in parent["reference"]["relations"]}
    full = {edge_key(edge): edge for connection in parent.get("graph_review", {}).get("connections", [])
            for edge in connection["outgoing_relations"]}
    return all(full.get(edge_key(item["edge"])) == item["edge"]
               and canonical.get(edge_key(item["edge"])) == {
                   key: item["edge"][key] for key in ReferenceRelation.model_fields
               } for item in ledger)


def covered_roots(roots: list[Path], inputs: dict, base: dict, ledger: list[dict]) -> list[Path]:
    return [root for root in roots if any(
        parent_covers_additions(read(path), inputs, base, ledger)
        for path in (root / "references").glob("*.json")
    )]


class AugmentedSourceGraphBuilder(CompleteSourceGraphBuilder):
    def build(self, inputs: dict[str, str]) -> dict:
        blocks = json.loads(inputs["source_blocks"])
        parts = [self.atomic.block(inputs["document_context"], block) for block in blocks]
        base = {"claims": [claim for part in parts for claim in part["claims"]],
                "roles": [role for part in parts for role in part["roles"]], "relations": []}
        _, self.current_mapping = alias_claims(base["claims"])
        self.addition_ledger = verified_source_additions(inputs, base, self.addition_reports)
        parents, legacy = self.mapped_draft_parents, self.legacy_source
        if self.addition_ledger:
            self.mapped_draft_parents = covered_roots(parents, inputs, base, self.addition_ledger)
            self.legacy_source = legacy if legacy and covered_roots(
                [legacy], inputs, base, self.addition_ledger,
            ) else None
        try:
            # This existing path rechecks full source, canonical decisions and stage identity,
            # and reconstructs the unchanged supported-edge ledger. No semantic values change.
            reference = ReusableMappedSourceGraphBuilder.build(self, inputs)
        finally:
            self.mapped_draft_parents, self.legacy_source = parents, legacy
        key = digest({"version": MAPPED_GRAPH_VERSION, "inputs": inputs})
        path = self.output / "references" / f"{key}.json"
        saved = read(path)
        extra = {"protocol_version": COMPLETE_REFERENCE_VERSION, "ledger": self.addition_ledger,
                 "candidate_access": False}
        if "verified_source_additions" in saved and saved["verified_source_additions"] != extra:
            raise SourceContractError("Replayed source addition ledger changed")
        saved["verified_source_additions"] = extra
        if saved["origin"] == "UNIQUE_KEY_SOURCE_GRAPH":
            records = [(item, read(item)) for item in (self.output / "edge-coverage-stages").glob("*.json")]
            evidence = []
            for name, stage in saved["stages"].items():
                matches = [(item, record) for item, record in records
                           if record["stage_inputs_digest"] == stage["input_digest"]
                           and record["mapped_graph"] == stage["mapped_graph"]]
                if len(matches) != 1:
                    raise SourceContractError("Fresh augmented graph lacks its unique source phases")
                evidence.append({"stage": name, "path": str(matches[0][0]), "digest": digest(matches[0][1])})
            saved["edge_coverage_stage_evidence"] = evidence
        final = {edge_key(edge): edge for edge in reference["relations"]}
        if any(final.get(edge_key(item["edge"])) != item["edge"] for item in self.addition_ledger):
            raise SourceContractError("Augmented graph omitted/changed a verified source addition")
        write_json(path, saved)
        return reference


class AugmentedVerifiedReferenceBuilder(DiagnosticCompleteVerifiedReferenceBuilder):
    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.drafts = AugmentedSourceGraphBuilder(
            kwargs.get("draft_source") or output / "draft-source-graph",
            addition_reports=kwargs.get("addition_reports") or [],
            mapped_draft_parents=kwargs.get("mapped_draft_parents") or [],
            actual_model=kwargs["actual_model"], atomic_source=kwargs.get("atomic_source"),
            legacy_source=kwargs.get("legacy_draft"), table_output=output / "table-field-ledgers",
            source_parents=kwargs.get("legacy_verified") or [], edge_root=self.edges.output / "edges",
        )
        self.drafts.annotator = CoverageDiagnosticPredictor(
            self.drafts.annotator, self.drafts.output, require_resolved=False,
        )
        self.drafts.reviewer = CoverageDiagnosticPredictor(self.drafts.reviewer, self.drafts.output)

    def build(self, inputs: dict[str, str]) -> dict:
        original = self.drafts.build(inputs)
        parents = self.legacy_verified
        ledger = self.drafts.addition_ledger
        if ledger:
            base = {**copy.deepcopy(original), "relations": []}
            eligible = covered_roots([root for root, _ in parents], inputs, base, ledger)
            self.legacy_verified = [(root, draft) for root, draft in parents if root in eligible]
        try:
            # Retain the existing full-round/real-endpoint-cache parent validator and
            # four-round bounded correction, skipping only blanket parent exclusion.
            reference = TransactionalVerifiedReferenceBuilder.build(self, inputs)
        finally:
            self.legacy_verified = parents
        final = {edge_key(edge): edge for edge in reference["relations"]}
        if any(final.get(edge_key(item["edge"])) != item["edge"] for item in ledger):
            raise SourceContractError("Final graph omitted/changed its verified source addition")
        return reference
