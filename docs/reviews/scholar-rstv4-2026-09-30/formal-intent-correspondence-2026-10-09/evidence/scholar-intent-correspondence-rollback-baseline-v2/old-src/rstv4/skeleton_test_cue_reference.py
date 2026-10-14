"""Test-only source connective repair with immutable compile and source provenance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import dspy

from rstv4.skeleton_boundary_reference_v3 import BoundaryCoverageVerifiedReferenceBuilder
from rstv4.skeleton_cached_reference import validate_cached_source_edge
from rstv4.skeleton_contract import SourceContractError, digest
from rstv4.skeleton_cue_diagnosis import SourceCueDiagnoser
from rstv4.skeleton_dspy import json_text, write_json
from rstv4.skeleton_endpoint_review import EndpointEdgeReviewer
from rstv4.skeleton_graph_reference import alias_claims, edge_key
from rstv4.skeleton_mapped_graph_v2 import MAPPED_VERIFIED_VERSION, read
from rstv4.skeleton_verified_reference import reference_edge_inputs

TEST_CUE_REFERENCE_VERSION = "post-compile-candidate-blind-cue-additions-with-unchanged-source-gates-v1"

PLANNER_RULES = """
verified_source_cue_relations contains source-only annotations independently reviewed and
individually SUPPORTED against their two actual endpoints after the learner was compiled.
Retain these exact complete edges, including evidence and rationale, in your proposed graph.
For a correction, preserve an already present exact edge; add a missing edge with a fresh
e-number ID in additional_edges. Do not duplicate an existing tuple or replace an unrelated
supported implication. This is source evidence, not a learner candidate or requested score.
All ordinary raw-source, independent coverage and exact-endpoint gates still apply. Source
uncertainty cannot be force-resolved. Claims, qualifications, roles and raw text stay intact.
"""


def enhanced_signature(signature: type) -> type:
    return signature.with_instructions(signature.instructions + PLANNER_RULES).append(
        "verified_source_cue_relations", dspy.InputField(),
    )


class TestSourceCueRegistry:
    def __init__(self, output: Path, *, compile_record: dict, seed_reports: list[Path],
                 supported_round_seeds: list[Path] | None = None) -> None:
        self.output, self.compile_record, self.seed_reports = output, compile_record, seed_reports
        self.supported_round_seeds = supported_round_seeds or []
        if (compile_record["test_papers_accessed_during_compile"] != 0
                or compile_record["instruction_digest"] != digest(compile_record["instructions"])):
            raise SourceContractError("Test-only source protocol requires an immutable uncontaminated compile")

    @staticmethod
    def source_inputs(values: dict[str, str]) -> dict[str, str]:
        return {key: values[key] for key in (
            "document_context", "source_blocks", "reference_claims", "relation_ontology",
        )}

    def records(self, values: dict[str, str]) -> list[tuple[Path, dict]]:
        common = self.source_inputs(values)
        matches = []
        for path in self.seed_reports + sorted((self.output / "additions").glob("*/report.json")):
            saved = read(path)
            frozen = read(path.parent / "freeze.json")
            actual = {key: frozen["inputs"][key] for key in common}
            if actual != common:
                continue
            if (saved["freeze_digest"] != digest(frozen) or not saved["agreement"]
                    or saved["candidate_access"] is not False or saved["held_out_source_access"] is not True
                    or saved["after_compile_only"] is not True
                    or saved["selected_prompt_digest"] != digest(self.compile_record)
                    or saved["compiled_at_unix"] != self.compile_record["completed_at_unix"]):
                raise SourceContractError("Test-only source addition lost its isolation/compile provenance")
            final = saved["independent_review"]
            if final["classification"] != "INTER_CLAIM_RELATION":
                continue
            judgment = saved["judgment"]
            if (judgment["status"] != "ASSESSED" or judgment["verdict"]["verdict"] != "SUPPORTED"
                    or read(path.parent / "isolated-source-edge/edges" / f"{judgment['input_digest']}.json") != judgment):
                raise SourceContractError("Test-only source addition lacks its exact supported endpoint cache")
            matches.append((path, saved))
        return matches

    def constraints(self, values: dict[str, str]) -> list[dict]:
        edges = {}
        for path in self.supported_round_seeds:
            seed = read(path)
            if seed["inputs"] != {key: values[key] for key in ("document_context", "source_blocks")}:
                continue
            parent_path = Path(seed["parent_round_path"])
            parent = read(parent_path)
            claims, mapping = alias_claims(parent["reference"]["claims"])
            if (seed["candidate_access"] is not False or seed["held_out_source_access"] is not True
                    or seed["selected_prompt_digest"] != digest(self.compile_record)
                    or seed["parent_round_digest"] != digest(parent)
                    or json_text(claims) != values["reference_claims"]):
                raise SourceContractError("Individual supported-round seed changed source/compile provenance")
            aliases = {original: alias for alias, original in mapping.items()}
            full = {edge_key(edge): edge for item in parent["graph_review"]["connections"]
                    for edge in item["outgoing_relations"]}
            synthetic = reference_edge_inputs(parent["reference"], json.loads(values["source_blocks"]))
            ledger = []
            for index, judgment in enumerate(parent["edge_reviews"]):
                if judgment["status"] != "ASSESSED" or judgment["verdict"]["verdict"] != "SUPPORTED":
                    continue
                validate_cached_source_edge(seed["inputs"], synthetic, index, judgment, Path(seed["edge_cache_root"]))
                edge = copy.deepcopy(full[edge_key(parent["reference"]["relations"][index])])
                ledger.append({"edge": copy.deepcopy(edge), "judgment_digest": digest(judgment)})
                for name in ("source_reference_id", "target_reference_id"):
                    edge[name] = aliases[edge[name]]
                edges[edge_key(edge)] = edge
            if seed["ledger"] != ledger:
                raise SourceContractError("Individual source-supported edge ledger omitted or altered a judgment")
        for _, saved in self.records(values):
            decision, verdict = saved["independent_review"], saved["judgment"]["verdict"]
            edge = {"source_reference_id": decision["first_reference_id"],
                    "target_reference_id": decision["second_reference_id"], "relation": decision["relation"],
                    "rationale": decision["rationale"],
                    "source_evidence_span_ids": verdict["source_evidence_span_ids"],
                    "target_evidence_span_ids": verdict["target_evidence_span_ids"]}
            key = edge_key(edge)
            if key in edges and edges[key] != edge:
                raise SourceContractError("Independent source additions disagree on an exact complete edge")
            edges[key] = edge
        return list(edges.values())

    def diagnose(self, values: dict[str, str], cue: dict) -> None:
        common = self.source_inputs(values)
        inputs = {**common, "source_cue": json_text(cue), "protocol_repair_feedback": ""}
        output = self.output / "additions" / digest(inputs)
        freeze = {"version": TEST_CUE_REFERENCE_VERSION, "inputs": inputs, "inputs_digest": digest(inputs),
                  "selected_prompt_digest": digest(self.compile_record),
                  "compiled_at_unix": self.compile_record["completed_at_unix"],
                  "candidate_access": False, "held_out_source_access": True, "after_compile_only": True,
                  "optimization_or_prompt_selection_allowed": False}
        frozen = output / "freeze.json"
        if frozen.exists() and read(frozen) != freeze:
            raise SourceContractError("Test-only source diagnosis changed after its freeze")
        if not frozen.exists():
            write_json(frozen, freeze)
        report_path = output / "report.json"
        if report_path.exists():
            return
        result = SourceCueDiagnoser(output, actual_model="gemini-3.1-pro").diagnose(inputs)
        final = result["independent_review"]["output"]["decision"]
        judgment = None
        if result["agreement"] and final["classification"] == "INTER_CLAIM_RELATION":
            proposal = {"source_reference_id": final["first_reference_id"],
                        "target_reference_id": final["second_reference_id"],
                        "relation": final["relation"], "rationale": final["rationale"]}
            source_reference = {"claims": json.loads(common["reference_claims"]), "relations": [proposal]}
            synthetic = reference_edge_inputs(source_reference, json.loads(common["source_blocks"]))
            judgment = EndpointEdgeReviewer(output / "isolated-source-edge", actual_model="gemini-3.1-pro").assess(
                {key: common[key] for key in ("document_context", "source_blocks")}, synthetic, 0,
            )
        report = {"version": TEST_CUE_REFERENCE_VERSION, "freeze_digest": digest(freeze),
                  "annotation": result["annotation"]["output"]["decision"], "independent_review": final,
                  "agreement": result["agreement"], "judgment": judgment,
                  "selected_prompt_digest": digest(self.compile_record),
                  "compiled_at_unix": self.compile_record["completed_at_unix"],
                  "candidate_access": False, "held_out_source_access": True, "after_compile_only": True,
                  "source_stage_records": {name: {"path": str(output / filename), "digest": digest(result[name])}
                      for name, filename in (("annotation", "annotation.json"), ("independent_review", "independent-review.json"))},
                  "quality_acceptance": "AI_SOURCE_REVIEW_NOT_EXPERT_GOLD"}
        write_json(report_path, report)
        if (not result["agreement"] or final["classification"] == "UNRESOLVED"
                or (judgment is not None and (judgment["status"] != "ASSESSED"
                    or judgment["verdict"]["verdict"] != "SUPPORTED"))):
            raise SourceContractError("Independent test-only source diagnosis remains unresolved or unsupported")


class TestCuePlanner:
    def __init__(self, original: Any, output: Path, registry: TestSourceCueRegistry) -> None:
        self.original_signature = original.signature
        self.predictor = dspy.Predict(enhanced_signature(original.signature))
        self.output, self.registry = output, registry

    def __call__(self, **values: str) -> Any:
        constraints = self.registry.constraints(values)
        actual = {**values, "verified_source_cue_relations": json_text(constraints)}
        result = self.predictor(**actual)
        output = {key: ({name: item.model_dump() for name, item in value.items()}
                        if isinstance(value, dict) else value) for key, value in dict(result).items()}
        record = {"version": TEST_CUE_REFERENCE_VERSION, "legacy_inputs": values,
                  "legacy_inputs_digest": digest(values), "actual_inputs": actual,
                  "actual_inputs_digest": digest(actual), "output": output,
                  "legacy_signature_digest": digest(self.original_signature.instructions),
                  "signature_digest": digest(self.predictor.signature.instructions),
                  "source_addition_reports": [{"path": str(path), "digest": digest(saved)}
                      for path, saved in self.registry.records(values)],
                  "supported_round_seeds": [{"path": str(path), "digest": digest(read(path))}
                      for path in self.registry.supported_round_seeds],
                  "candidate_access": False, "held_out_source_access": True, "after_compile_only": True}
        path = self.output / "cue-planner-stages" / f"{digest(actual)}.json"
        if path.exists() and read(path) != record:
            raise SourceContractError("Test-only planner changed for the same actual source constraints")
        write_json(path, record)
        if "edges" in output:
            edges = output["edges"]
        else:
            edges = copy.deepcopy(json.loads(values["draft_graph"])["edges"])
            for key, repair in output["repairs"].items():
                if repair["action"] == "REMOVE":
                    del edges[key]
                elif repair["replacement"] is not None:
                    edges[key] = repair["replacement"]
            edges.update(output["additional_edges"])
        actual_edges = {edge_key(edge): edge for edge in edges.values()}
        for edge in constraints:
            if actual_edges.get(edge_key(edge)) != edge:
                raise SourceContractError("Source planner must explicitly retain this complete verified cue relation: "
                                          + json_text(edge))
        return result


class DiagnosingTestCueCoverage:
    def __init__(self, original: Any, registry: TestSourceCueRegistry) -> None:
        self.original, self.registry = original, registry

    def __call__(self, **values: str) -> Any:
        result = self.original(**values)
        cues = {item["cue_id"]: item for item in json.loads(values["discourse_cues"])}
        for key, decision in result.cue_resolutions.items():
            if decision.classification == "AMBIGUOUS":
                self.registry.diagnose(values, cues[key])
        # Actual unresolved coverage is retained. Only a later complete model plan and
        # independent source coverage can resolve it; this wrapper never edits a decision.
        return result


class PostCompileCueReferenceBuilder(BoundaryCoverageVerifiedReferenceBuilder):
    def __init__(self, output: Path, *, compile_record: dict,
                 seed_reports: list[Path] | None = None,
                 supported_round_seeds: list[Path] | None = None, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.cue_registry = TestSourceCueRegistry(output / "test-only-cue-source",
                                                compile_record=compile_record, seed_reports=seed_reports or [],
                                                supported_round_seeds=supported_round_seeds)
        for predictor, directory in ((self.drafts.annotator.inner, self.drafts.output),
                                     (self.drafts.reviewer.inner, self.drafts.output),
                                     (self.corrector.inner, output)):
            predictor.planner = TestCuePlanner(predictor.planner, directory, self.cue_registry)
            predictor.coverage = DiagnosingTestCueCoverage(predictor.coverage, self.cue_registry)

    def build(self, inputs: dict[str, str]) -> dict:
        reference = super().build(inputs)
        from rstv4.skeleton_endpoint_review import RELATION_ONTOLOGY

        claims, mapping = alias_claims(reference["claims"])
        values = {**inputs, "reference_claims": json_text(claims), "relation_ontology": RELATION_ONTOLOGY}
        constraints = self.cue_registry.constraints(values)
        path = self.output / "references" / f"{digest({'version': MAPPED_VERIFIED_VERSION, 'inputs': inputs})}.json"
        saved = read(path)
        full = {edge_key(edge): edge for item in saved["graph_review"]["connections"]
                for edge in item["outgoing_relations"]}
        for constraint in constraints:
            edge = copy.deepcopy(constraint)
            for name in ("source_reference_id", "target_reference_id"):
                edge[name] = mapping[edge[name]]
            if full.get(edge_key(edge)) != edge:
                raise SourceContractError("Final reference lost a verified test-only source cue relation")
        extra = {"version": TEST_CUE_REFERENCE_VERSION, "constraints": constraints,
                 "reports": [{"path": str(item), "digest": digest(record)}
                     for item, record in self.cue_registry.records(values)],
                 "supported_round_seeds": [{"path": str(item), "digest": digest(read(item))}
                     for item in self.cue_registry.supported_round_seeds],
                 "candidate_access": False, "held_out_source_access": True, "after_compile_only": True,
                 "selected_prompt_digest": digest(self.cue_registry.compile_record)}
        if "post_compile_cue_source" in saved and saved["post_compile_cue_source"] != extra:
            raise SourceContractError("Final test-only source cue provenance changed")
        if "post_compile_cue_source" not in saved:
            write_json(path, {**saved, "post_compile_cue_source": extra})
        return reference
