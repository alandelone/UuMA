from __future__ import annotations

import copy
from pathlib import Path

import pytest

pytest.importorskip("dspy", reason="Optional skeleton-optimization dependency")

import dspy
from rstv4.skeleton_local_experiment import (
    LocalSourceExperiment,
    SourceEvaluationAbort,
    actionable_feedback,
)
from rstv4.skeleton_mapped_experiment import (
    MappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment import (
    SourceEvaluationAbort as MappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v2 import (
    MappedSourceExperiment as LosslessMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v2 import (
    SourceEvaluationAbort as LosslessMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v3 import (
    MappedSourceExperiment as CachedMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v3 import (
    SourceEvaluationAbort as CachedMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v4 import (
    MappedSourceExperiment as PreservedMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v4 import (
    SourceEvaluationAbort as PreservedMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v5 import (
    MappedSourceExperiment as TransactionalMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v5 import (
    SourceEvaluationAbort as TransactionalMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v6 import (
    MappedSourceExperiment as SpecificMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v6 import (
    SourceEvaluationAbort as SpecificMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v7 import (
    MappedSourceExperiment as StagedMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v7 import (
    SourceEvaluationAbort as StagedMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v8 import (
    MappedSourceExperiment as CompleteMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v8 import (
    SourceEvaluationAbort as CompleteMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v9 import (
    MappedSourceExperiment as DiagnosticMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v9 import (
    SourceEvaluationAbort as DiagnosticMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v10 import (
    MappedSourceExperiment as AugmentedMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v10 import (
    SourceEvaluationAbort as AugmentedMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v11 import (
    MappedSourceExperiment as ProjectionMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v11 import (
    SourceEvaluationAbort as ProjectionMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v12 import (
    MappedSourceExperiment as RetentionMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v12 import (
    SourceEvaluationAbort as RetentionMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v13 import (
    MappedSourceExperiment as HistoricalMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v13 import (
    SourceEvaluationAbort as HistoricalMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v14 import (
    MappedSourceExperiment as SeparatedCoverageMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v14 import (
    SourceEvaluationAbort as SeparatedCoverageMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v15 import (
    MappedSourceExperiment as BoundaryMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v15 import (
    SourceEvaluationAbort as BoundaryMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v16 import (
    MappedSourceExperiment as ProtocolMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v16 import (
    SourceEvaluationAbort as ProtocolMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v17 import (
    MappedSourceExperiment as ContextualMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v17 import (
    SourceEvaluationAbort as ContextualMappedSourceEvaluationAbort,
)
from rstv4.skeleton_mapped_experiment_v18 import (
    MappedSourceExperiment as AdjudicatedMappedSourceExperiment,
)
from rstv4.skeleton_mapped_experiment_v18 import (
    SourceEvaluationAbort as AdjudicatedMappedSourceEvaluationAbort,
)
from rstv4.skeleton_table_experiment import (
    SourceEvaluationAbort as TableSourceEvaluationAbort,
)
from rstv4.skeleton_table_experiment import (
    VerifiedTableExperiment,
)
from rstv4.skeleton_verified_experiment import (
    SourceEvaluationAbort as VerifiedSourceEvaluationAbort,
)
from rstv4.skeleton_verified_experiment import (
    VerifiedSourceExperiment,
)


class FixedProgram(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layer = dspy.Predict("x -> y")

    def forward(self, x: str) -> dspy.Prediction:
        return dspy.Prediction(block_atoms=[], relations=[], intents=[], roles=[], units=[], error=None)


@pytest.mark.parametrize("defect", ["evaluator", "reference"])
@pytest.mark.parametrize("experiment_type,abort_type", [
    (LocalSourceExperiment, SourceEvaluationAbort),
    (VerifiedSourceExperiment, VerifiedSourceEvaluationAbort),
    (VerifiedTableExperiment, TableSourceEvaluationAbort),
    (MappedSourceExperiment, MappedSourceEvaluationAbort),
    (LosslessMappedSourceExperiment, LosslessMappedSourceEvaluationAbort),
    (CachedMappedSourceExperiment, CachedMappedSourceEvaluationAbort),
    (PreservedMappedSourceExperiment, PreservedMappedSourceEvaluationAbort),
    (TransactionalMappedSourceExperiment, TransactionalMappedSourceEvaluationAbort),
    (SpecificMappedSourceExperiment, SpecificMappedSourceEvaluationAbort),
    (StagedMappedSourceExperiment, StagedMappedSourceEvaluationAbort),
    (CompleteMappedSourceExperiment, CompleteMappedSourceEvaluationAbort),
    (DiagnosticMappedSourceExperiment, DiagnosticMappedSourceEvaluationAbort),
    (AugmentedMappedSourceExperiment, AugmentedMappedSourceEvaluationAbort),
    (ProjectionMappedSourceExperiment, ProjectionMappedSourceEvaluationAbort),
    (RetentionMappedSourceExperiment, RetentionMappedSourceEvaluationAbort),
    (HistoricalMappedSourceExperiment, HistoricalMappedSourceEvaluationAbort),
    (SeparatedCoverageMappedSourceExperiment, SeparatedCoverageMappedSourceEvaluationAbort),
    (BoundaryMappedSourceExperiment, BoundaryMappedSourceEvaluationAbort),
    (ProtocolMappedSourceExperiment, ProtocolMappedSourceEvaluationAbort),
    (ContextualMappedSourceExperiment, ContextualMappedSourceEvaluationAbort),
    (AdjudicatedMappedSourceExperiment, AdjudicatedMappedSourceEvaluationAbort),
])
def test_gepa_cannot_convert_source_failures_into_learner_zero_scores(
    tmp_path: Path, defect: str, experiment_type, abort_type,
) -> None:
    experiment = experiment_type.__new__(experiment_type)
    report = {"evaluation_contract_failure": defect == "evaluator",
              "reference_defects": ["Source number is incorrect"] if defect == "reference" else []}
    experiment.assess = lambda *args: report
    example = dspy.Example(x="unused", document_context="{}", source_blocks="[]", reference={}).with_inputs("x")
    optimizer = dspy.GEPA(
        metric=experiment.metric, max_metric_calls=4, reflection_lm=object(),
        component_selector="all", num_threads=1, log_dir=str(tmp_path),
    )
    with pytest.raises(abort_type, match="needs repair"):
        optimizer.compile(FixedProgram(), trainset=[example], valset=[example])


def test_feedback_uses_actual_candidate_edge_and_actual_endpoint_statements() -> None:
    candidate = {
        "block_atoms": [{"block_id": "b", "atoms": [
            {"atom_id": "b:a1", "statement": "The study aims to reduce costs."},
            {"atom_id": "b:a2", "statement": "An optimization method was used."},
        ]}],
        "relations": [{"source_id": "b:a1", "target_id": "b:a2", "relation": "Support"}],
        "intents": [{"atom_id": "b:a1", "primary": "Paper_Objective"},
                    {"atom_id": "b:a2", "primary": "Method_Overview"}],
    }
    reference = {"claims": [], "relations": []}
    report = {"grounded_review": {"matches": [], "atom_verdicts": [], "edge_verdicts": [
        {"relation_index": 0, "verdict": "UNSUPPORTED", "evidence_span_ids": ["b:s1", "b:s2"],
         "rationale": "The objective is not evidence for the methodological action."},
    ]}, "assessment": {"relation_matches": []}, "role_pairs": []}
    before = copy.deepcopy((candidate, reference, report))
    feedback = actionable_feedback(report, reference, candidate)
    edge = feedback["unsupported_or_uncertain_edges"][0]
    assert edge["candidate_edge"] == candidate["relations"][0]
    assert edge["source_atom"]["statement"] == "The study aims to reduce costs."
    assert edge["target_atom"]["statement"] == "An optimization method was used."
    assert (candidate, reference, report) == before


def test_gepa_cannot_turn_source_adjudication_protocol_errors_into_learner_scores(tmp_path):
    from rstv4.skeleton_contract import SourceContractError

    experiment = AdjudicatedMappedSourceExperiment.__new__(AdjudicatedMappedSourceExperiment)

    def failed_source(*args):
        raise SourceContractError("Actual source-only stage lacks a required reference ID")

    experiment.assess = failed_source
    example = dspy.Example(x="unused", document_context="{}", source_blocks="[]", reference={}).with_inputs("x")
    optimizer = dspy.GEPA(metric=experiment.metric, max_metric_calls=4, reflection_lm=object(),
                          component_selector="all", num_threads=1, log_dir=str(tmp_path))
    with pytest.raises(AdjudicatedMappedSourceEvaluationAbort, match="protocol needs repair"):
        optimizer.compile(FixedProgram(), trainset=[example], valset=[example])
