"""Full fresh-paper comparison of an immutable pre-existing ALL4 compile."""
from __future__ import annotations

import time
from pathlib import Path

from rstv4.skeleton_block_review import BLOCK_REVIEW_VERSION, aggregate_local_reports
from rstv4.skeleton_contract import chunk_document, digest
from rstv4.skeleton_dspy import PaperSkeletonProgram, apply_instructions, write_json
from rstv4.skeleton_mapped_experiment_v18 import (
    MappedSourceExperiment as CompiledExperiment,
)
from rstv4.skeleton_mapped_experiment_v18 import (
    read,
)
from rstv4.skeleton_mapped_experiment_v18 import (
    source_digests as compiled_source_digests,
)
from rstv4.skeleton_mapped_graph_v2 import MAPPED_VERIFIED_VERSION as SOURCE_REFERENCE_VERSION
from rstv4.skeleton_mapped_review import MAPPED_REVIEW_VERSION
from rstv4.skeleton_test_cue_reference_v2 import (
    TEST_CUE_REFERENCE_VERSION,
    PostCompileCueReferenceBuilder,
)


def source_digests() -> dict[str, str]:
    return {**compiled_source_digests(), **{name: digest(Path(__file__).with_name(name).read_text(encoding="utf-8"))
        for name in ("skeleton_cue_diagnosis.py", "skeleton_test_cue_reference.py", "skeleton_mapped_experiment_v19.py",
                     "skeleton_boundary_reference_v4.py", "skeleton_test_cue_reference_v2.py", "skeleton_mapped_experiment_v20.py")}}


class FrozenCompileTestExperiment(CompiledExperiment):
    def __init__(self, corpus: Path, output: Path, compile_parent: Path) -> None:
        parent_freeze = read(compile_parent / "development-freeze.json")
        selected = read(compile_parent / "optimized-prompts.json")
        summary = read(compile_parent / "optimization-summary.json")
        if (parent_freeze["execution_source_digests"] != compiled_source_digests()
                or selected["development_freeze_digest"] != digest(parent_freeze)
                or selected["test_papers_accessed_during_compile"] != 0
                or selected["changed_components"] != ["layer1", "layer2", "layer3", "layer4"]
                or summary["total_metric_calls"] != 80):
            raise ValueError("Immutable ALL4 compile/source provenance changed")
        for filename in ("baseline-prompts.json", "optimized-prompts.json", "development-freeze.json", "optimization-summary.json"):
            if (output / filename).read_bytes() != (compile_parent / filename).read_bytes():
                raise ValueError("Test-only successor changed an original compile artifact")
        super().__init__(corpus, output, compile_parent / "development-source")
        self.compile_parent = compile_parent
        self.test_reference_builder = PostCompileCueReferenceBuilder(
            output / "test-source-reference", actual_model="gemini-3.1-pro", compile_record=selected,
            seed_reports=[compile_parent.parent / "fresh-source-cue-diagnosis-v1/report.json"],
            supported_round_seeds=[output / "prior-supported-source-edges.json"],
        )

    def optimize(self, metric_calls: int = 80) -> None:
        raise RuntimeError("This declared test-only successor cannot compile or select prompts")

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
        if development_freeze["execution_source_digests"] != compiled_source_digests():
            raise ValueError("Execution changed after optimization")
        freeze = {
            "corpus_digest": self.manifest["manifest_digest"], "rubric_version": BLOCK_REVIEW_VERSION, "source_reference_version": SOURCE_REFERENCE_VERSION, "table_requirement_policy": "source-table-literal-field-requirements-v1", "block_review_protocol": MAPPED_REVIEW_VERSION,
            "execution_source_digests": source_digests(),
            "compiled_execution_source_digests": compiled_source_digests(),
            "test_execution_protocol": TEST_CUE_REFERENCE_VERSION,
            "test_pipeline_freeze_digest": digest(read(self.output / "pipeline-freeze.json")),
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

