"""All-component DSPy experiment using coverage-reviewed independent source graphs."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import time
from pathlib import Path
from typing import Any

import dspy

from rstv4.skeleton_block_review import (
    BLOCK_REVIEW_VERSION,
    aggregate_local_reports,
)
from rstv4.skeleton_contract import chunk_document, digest
from rstv4.skeleton_dspy import (
    PaperSkeletonProgram,
    apply_instructions,
    instructions,
    json_text,
    write_json,
)
from rstv4.skeleton_experiment import Experiment
from rstv4.skeleton_mapped_graph_v2 import (
    MAPPED_VERIFIED_VERSION as SOURCE_REFERENCE_VERSION,
)
from rstv4.skeleton_mapped_review import (
    MAPPED_REVIEW_VERSION,
)
from rstv4.skeleton_mapped_review import (
    MappedLocalSourceReviewer as LocalSourceReviewer,
)
from rstv4.skeleton_source_reference import validate_source_relations
from rstv4.skeleton_staged_reference import (
    StagedVerifiedReferenceBuilder as SourceReferenceBuilder,
)

EXPERIMENT_VERSION = "staged-source-repair-all-components-fresh-test-v11"
EXECUTION_FILES = (
    "skeleton_contract.py", "skeleton_dspy.py", "skeleton_experiment.py",
    "skeleton_grounded_review.py", "skeleton_endpoint_review.py",
    "skeleton_source_reference.py", "skeleton_block_review.py", "skeleton_local_experiment.py",
    "skeleton_graph_reference.py", "skeleton_verified_experiment.py",
    "skeleton_verified_reference.py", "skeleton_table_reference.py", "skeleton_table_experiment.py",
    "skeleton_context_reference.py", "skeleton_mapped_review.py", "skeleton_mapped_graph.py",
    "skeleton_mapped_experiment.py", "skeleton_mapped_graph_v2.py",
    "skeleton_mapped_experiment_v2.py", "skeleton_cached_reference.py",
    "skeleton_mapped_experiment_v3.py", "skeleton_preserved_reference.py",
    "skeleton_mapped_experiment_v4.py", "skeleton_transactional_reference.py",
    "skeleton_mapped_experiment_v5.py", "skeleton_transactional_reference_v2.py",
    "skeleton_mapped_experiment_v6.py", "skeleton_staged_reference.py",
    "skeleton_mapped_experiment_v7.py",
)


class SourceEvaluationError(RuntimeError):
    """A source/evaluator defect cannot be treated as learner optimization feedback."""


class SourceEvaluationAbort(BaseException):
    """Stop GEPA: its DSPy adapter converts ordinary metric Exceptions to zero scores."""


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_digests() -> dict[str, str]:
    return {name: digest(Path(__file__).with_name(name).read_text(encoding="utf-8"))
            for name in EXECUTION_FILES}


def actionable_feedback(report: dict[str, Any], reference: dict[str, Any], candidate: dict[str, Any]) -> dict:
    """Expose actual source-local error examples, without unrelated reference edge indices."""
    review = report.get("grounded_review") or {}
    claims = {claim["reference_id"]: claim for claim in reference["claims"]}
    atoms = {atom["atom_id"]: atom for record in candidate["block_atoms"] for atom in record["atoms"]}
    intents = {item["atom_id"]: item["primary"] for item in candidate["intents"]}
    return {
        "claim_matches": [{"reference": claims[match["reference_id"]], "match": match,
                           "candidate_atom": atoms.get(match["atom_id"]),
                           "actual_intent": intents.get(match["atom_id"])}
                          for match in review.get("matches", [])
                          if not match["meaning_preserved"] or not match["qualifications_preserved"]
                          or intents.get(match["atom_id"]) != claims[match["reference_id"]]["intent"]],
        "unsupported_or_uncertain_atoms": [item for item in review.get("atom_verdicts", [])
                                            if item["verdict"] != "SUPPORTED"],
        "unsupported_or_uncertain_edges": [
            {"candidate_edge": candidate["relations"][item["relation_index"]],
             "source_atom": atoms[candidate["relations"][item["relation_index"]]["source_id"]],
             "target_atom": atoms[candidate["relations"][item["relation_index"]]["target_id"]],
             "source_verdict": item}
            for item in review.get("edge_verdicts", []) if item["verdict"] != "SUPPORTED"
        ],
        "missing_reference_edges": [
            {"reference_edge": reference["relations"][item["reference_relation_index"]],
             "source_claim": claims[reference["relations"][item["reference_relation_index"]]["source_reference_id"]],
             "target_claim": claims[reference["relations"][item["reference_relation_index"]]["target_reference_id"]]}
            for item in report.get("assessment", {}).get("relation_matches", [])
            if item["predicted_relation_index"] is None
        ],
        "role_pairs": report["role_pairs"],
    }


class MappedSourceExperiment(Experiment):
    def __init__(self, corpus: Path, output: Path, development_source: Path) -> None:
        super().__init__(corpus, output, fixed_models=True)
        self.development_source = development_source
        self.source_freeze = read(development_source / "freeze.json")
        if self.source_freeze["held_out_source_access"] is not False:
            raise ValueError("Development references must be source-only and exclude test papers")
        self.local_reviewer = LocalSourceReviewer(output / "source-review", actual_model="gemini-3.1-pro")
        self.test_reference_builder = SourceReferenceBuilder(output / "test-source-reference", actual_model="gemini-3.1-pro")

    def reference(self, inputs: dict[str, str]) -> dict[str, Any]:
        key = digest({"version": SOURCE_REFERENCE_VERSION, "inputs": inputs})
        path = self.development_source / "references" / f"{key}.json"
        if not path.exists():
            raise SourceEvaluationError("Complete source-only development references before optimization")
        saved = read(path)
        if saved["inputs_digest"] != digest(inputs):
            raise ValueError("Refined development reference input changed")
        reference = saved["reference"]
        before = digest(reference)
        validate_source_relations(reference, json.loads(inputs["source_blocks"]))
        if digest(reference) != before:
            raise ValueError("Refined development quote changed")
        return reference

    def assess(self, inputs: dict[str, str], reference: dict[str, Any], candidate: dict[str, Any]) -> dict:
        return self.local_reviewer.assess(inputs, reference, candidate)

    def metric(self, gold: dspy.Example, pred: dspy.Prediction, trace: Any = None,
               pred_name: str | None = None, pred_trace: Any = None) -> dspy.Prediction:
        candidate = dict(pred)
        report = self.assess({"document_context": gold.document_context,
                              "source_blocks": gold.source_blocks}, gold.reference, candidate)
        if report.get("evaluation_contract_failure") or report["reference_defects"]:
            raise SourceEvaluationAbort("Source/evaluator review needs repair; see preserved assessment")
        metrics = {key: report[key] for key in (
            "score", "reference_claims", "predicted_atoms", "covered_claims", "qualified_claims",
            "unsupported_claims", "unassessed_atoms", "layer1_coverage", "qualification_recall",
            "unsupported_claim_rate", "layer2_macro_f1", "layer3_macro_f1", "layer4_accuracy",
        ) if key in report}
        feedback = report["feedback"]
        if not candidate.get("error"):
            feedback += "\nSource-local discrepancies: " + json_text(actionable_feedback(report, gold.reference, candidate))
        return dspy.Prediction(score=report["score"], feedback=(
            f"Component {pred_name or 'all four layers'}. " + feedback + "\nMetrics: " + json_text(metrics)
        ))

    def optimize(self, metric_calls: int = 80) -> None:
        if (self.output / "optimized-prompts.json").exists():
            raise FileExistsError("Prompts already frozen; reuse them or create a new experiment")
        source_report = read(self.development_source / "report.json")
        if source_report["status"] != "COMPLETE" or source_report["completed_windows"] != 12:
            raise SourceEvaluationError("All twelve source development windows are required")
        program = PaperSkeletonProgram()
        baseline = instructions(program)
        train, validation = self.examples("train"), self.examples("validation")
        freeze = {
            "version": EXPERIMENT_VERSION, "rubric_version": BLOCK_REVIEW_VERSION, "source_reference_version": SOURCE_REFERENCE_VERSION, "table_requirement_policy": "source-table-literal-field-requirements-v1", "block_review_protocol": MAPPED_REVIEW_VERSION,
            "corpus_digest": self.manifest["manifest_digest"], "execution_source_digests": source_digests(),
            "development_source_freeze_digest": digest(self.source_freeze),
            "development_source_report_digest": digest(source_report),
            "train": [{"paper_id": item.paper_id, "inputs_digest": digest(dict(item.inputs())),
                       "reference_digest": digest(item.reference)} for item in train],
            "validation": [{"paper_id": item.paper_id, "inputs_digest": digest(dict(item.inputs())),
                            "reference_digest": digest(item.reference)} for item in validation],
            "all_predictors": list(baseline), "held_out_test_access": 0,
            "actual_model_policy": {"student": "gemini-3.7-flash", "teacher": "gemini-3.1-pro"},
            "library_versions": {name: importlib.metadata.version(name) for name in ("dspy", "gepa")},
            "max_metric_calls": metric_calls,
        }
        path = self.output / "development-freeze.json"
        if path.exists() and read(path) != freeze:
            raise ValueError("Development execution/reference changed after freeze")
        write_json(path, freeze)
        write_json(self.output / "baseline-prompts.json", {"instructions": baseline,
                   "corpus_digest": self.manifest["manifest_digest"]})
        optimizer = dspy.GEPA(
            metric=self.metric, max_metric_calls=metric_calls, reflection_lm=self.teacher,
            reflection_minibatch_size=2, instruction_proposer=self.propose_instructions,
            component_selector="all", skip_perfect_score=False, num_threads=1,
            add_format_failure_as_feedback=True, use_merge=False,
            log_dir=str(self.output / "gepa"), track_stats=True, seed=20261002,
        )
        optimized = optimizer.compile(program, trainset=train, valset=validation)
        selected, details = instructions(optimized), optimized.detailed_results
        write_json(self.output / "optimization-summary.json", {
            "best_candidate_index": details.best_idx, "validation_scores": details.val_aggregate_scores,
            "total_metric_calls": details.total_metric_calls,
            "candidate_instructions": [instructions(item) for item in details.candidates],
        })
        write_json(self.output / "optimized-prompts.json", {
            "instructions": selected, "instruction_digest": digest(selected),
            "changed_components": [name for name in baseline if selected[name] != baseline[name]],
            "corpus_digest": self.manifest["manifest_digest"], "version": EXPERIMENT_VERSION,
            "rubric_version": BLOCK_REVIEW_VERSION, "source_reference_version": SOURCE_REFERENCE_VERSION, "table_requirement_policy": "source-table-literal-field-requirements-v1", "block_review_protocol": MAPPED_REVIEW_VERSION, "optimizer": "DSPy-3.4-GEPA-all-components",
            "max_metric_calls": metric_calls, "test_papers_accessed_during_compile": 0,
            "development_freeze_digest": digest(freeze), "completed_at_unix": time.time(),
            "reference_status": "AI_SOURCE_REVIEWED_NOT_EXPERT_GOLD",
        })
        print("LOCAL_ALL_COMPONENT_OPTIMIZATION_COMPLETE", flush=True)

    def test(self) -> None:
        artifacts = {name: read(self.output / f"{name}-prompts.json") for name in ("baseline", "optimized")}
        programs = {}
        for name, artifact in artifacts.items():
            if artifact["corpus_digest"] != self.manifest["manifest_digest"]:
                raise ValueError("Prompt artifact belongs to another corpus")
            program = PaperSkeletonProgram()
            apply_instructions(program, artifact["instructions"])
            programs[name] = program
        documents = self.documents("test")
        if len(documents) < 10 or len({document["source_pdf_sha256"] for document in documents}) != len(documents):
            raise ValueError("Require at least ten distinct full test PDFs")
        if {document["paper_id"] for document in documents} & set(self.manifest["excluded_previous_paper_ids"]):
            raise ValueError("Fresh test corpus overlaps previously inspected papers")
        development_freeze = read(self.output / "development-freeze.json")
        if development_freeze["execution_source_digests"] != source_digests():
            raise ValueError("Execution changed after optimization")
        freeze = {
            "corpus_digest": self.manifest["manifest_digest"], "rubric_version": BLOCK_REVIEW_VERSION, "source_reference_version": SOURCE_REFERENCE_VERSION, "table_requirement_policy": "source-table-literal-field-requirements-v1", "block_review_protocol": MAPPED_REVIEW_VERSION,
            "execution_source_digests": source_digests(),
            "prompt_digests": {name: digest(artifact["instructions"]) for name, artifact in artifacts.items()},
            "test_paper_ids": [document["paper_id"] for document in documents],
            "full_test_document_digests": {document["paper_id"]: digest(document) for document in documents},
            "actual_model_policy": development_freeze["actual_model_policy"],
            "optimization_freeze_digest": digest(development_freeze),
            "expected_test_windows": sum(len(chunk_document(document["blocks"])) for document in documents),
        }
        path = self.output / "test-freeze.json"
        if path.exists() and read(path) != freeze:
            raise ValueError("Fresh test freeze changed")
        write_json(path, freeze)
        papers, all_reports = [], {name: [] for name in programs}
        for document in documents:
            chunks = chunk_document(document["blocks"])
            per_paper, units = {name: [] for name in programs}, {name: [] for name in programs}
            for index, chunk in enumerate(chunks):
                inputs = self.inputs(document, chunk)
                # This independent reference builder never receives candidate programs/output.
                reference = self.test_reference_builder.build(inputs)
                for name, program in programs.items():
                    target = self.output / "test" / document["paper_id"] / name / f"chunk-{index:03d}.json"
                    lineage = {"inputs_digest": digest(inputs), "instruction_digest": freeze["prompt_digests"][name],
                               "paper_id": document["paper_id"], "chunk_index": index,
                               "source_blocks": [block["block_id"] for block in chunk],
                               "reference_digest": digest(reference)}
                    if target.exists():
                        stored = read(target)
                        if any(stored[key] != value for key, value in lineage.items()):
                            raise ValueError("Fresh test checkpoint lineage changed")
                        candidate = stored["candidate"]
                    else:
                        candidate = dict(program(**inputs))
                        write_json(target, {**lineage, "candidate": candidate,
                                            "completed_at_unix": time.time()})
                    report = self.assess(inputs, reference, candidate)
                    per_paper[name].append(report)
                    units[name].extend(candidate["units"])
                    write_json(target.with_name(target.stem + ".assessment.json"), report)
                    print(f"FRESH_LOCAL_TEST {document['paper_id']} {name} {index + 1}/{len(chunks)} "
                          f"score={report['score']:.3f}", flush=True)
            paper = {"paper_id": document["paper_id"], "title": document["title"], "models": {},
                     "source_blocks": len(document["blocks"]), "chunks": len(chunks),
                     "parser_quality": document["parser_quality"]}
            for name in programs:
                all_reports[name].extend(per_paper[name])
                summary = aggregate_local_reports(per_paper[name])
                expected = {block["block_id"] for chunk in chunks for block in chunk}
                observed = [unit["block_id"] for unit in units[name]]
                summary["source_block_coverage"] = len(set(observed) & expected) / len(expected)
                summary["duplicate_block_ids"] = len(observed) - len(set(observed))
                links = self.assemble(document, units[name], name)
                summary["argument_links"] = len(links)
                summary["argument_contract_failures"] = sum(bool(read(item).get("contract_failure"))
                    for item in (self.output / "test" / document["paper_id"] / name).glob("argument-*.json"))
                summary["semantic_gate_passed_against_model_reference"] &= (
                    summary["source_block_coverage"] == 1.0 and not summary["duplicate_block_ids"]
                    and not summary["argument_contract_failures"]
                )
                paper["models"][name] = summary
                write_json(self.output / "test" / document["paper_id"] / name / "paper.json", {
                    "paper_id": document["paper_id"], "source_pdf_sha256": document["source_pdf_sha256"],
                    "units": units[name], "argument_links": links, "summary": summary,
                    "status": "RESEARCH_CANDIDATE_REVIEW_REQUIRED",
                })
            papers.append(paper)
            write_json(self.output / "test-progress.json", {
                "complete_papers": len(papers), "required_papers": len(documents), "papers": papers,
            })
        write_json(self.output / "test-report.json", {
            **freeze, "complete_papers": len(papers), "papers": papers,
            "overall": {name: aggregate_local_reports(values) for name, values in all_reports.items()},
            "reference_status": "AI_SOURCE_REVIEWED_NOT_EXPERT_GOLD",
            "test_scope": "All normalized body windows, both variants, fresh papers excluded from development",
        })
        print("FRESH_LOCAL_FULL_TEST_COMPLETE", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["optimize", "test"])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development-source", type=Path, required=True)
    parser.add_argument("--metric-calls", type=int, default=80)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080/v1")
    args = parser.parse_args()
    os.environ["UNLIMITED_LLMAPI_BASE_URL"] = args.base_url
    experiment = MappedSourceExperiment(args.corpus.resolve(), args.output.resolve(), args.development_source.resolve())
    if args.mode == "optimize":
        experiment.optimize(args.metric_calls)
    else:
        experiment.test()


if __name__ == "__main__":
    main()
