"""Inspect actual within-claim proposition partition in source coverage review."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import dspy

from rstv4.skeleton_historical_reference import HistoricalVerifiedReferenceBuilder
from rstv4.skeleton_staged_reference import SourceCoverageReview

PARTITION_REFERENCE_VERSION = "source-cue-proposition-partition-before-interclaim-link-v1"

PARTITION_INSTRUCTIONS = (
    "\nBefore classifying each cue, identify its actual two propositions in the raw source "
    "and locate each in the COMPLETE supplied claim statements, quotes and qualifications. "
    "If both propositions are fully retained in ONE supplied claim, explain that exact "
    "claim alias and both propositions for WITHIN_ONE_CLAIM. Mere span overlap or shared "
    "block is insufficient. Do not turn a within-claim causal/comparative statement into "
    "a link to an unrelated neighboring claim. Rejection of such a wrong cross-claim link "
    "does not decide the cue's internal proposition partition. If the propositions are "
    "in distinct claims, examine their actual relation and evidence; an omitted warranted "
    "link remains AMBIGUOUS. Structural uses need their actual contextual explanation. "
    "Do not force any classification, change claim granularity or infer certainty merely "
    "to pass validation. Independently inspect other missing source relations too."
)


class PartitionVerifiedReferenceBuilder(HistoricalVerifiedReferenceBuilder):
    """Keep all existing source/edge/history gates and unchanged bounded attempt limits."""

    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        signature = SourceCoverageReview.with_instructions(
            SourceCoverageReview.instructions + PARTITION_INSTRUCTIONS,
        )
        self.corrector.inner.coverage = dspy.Predict(signature)
        self.drafts.annotator.inner.coverage = dspy.Predict(signature)
        self.drafts.reviewer.inner.coverage = dspy.Predict(signature)
