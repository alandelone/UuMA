"""Keep directed source-boundary provenance and bounded independent coverage repair."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from rstv4.skeleton_boundary_reference_v2 import (
    BoundaryCoverageVerifiedReferenceBuilder as PreviousBuilder,
)
from rstv4.skeleton_partition_reference_v3 import ProtocolIndependentCoveragePredictor


class BoundaryCoverageVerifiedReferenceBuilder(PreviousBuilder):
    def __init__(self, output: Path, **kwargs: Any) -> None:
        super().__init__(output, **kwargs)
        self.corrector.inner.coverage = ProtocolIndependentCoveragePredictor(output)
        self.drafts.annotator.inner.coverage = ProtocolIndependentCoveragePredictor(self.drafts.output)
        self.drafts.reviewer.inner.coverage = ProtocolIndependentCoveragePredictor(self.drafts.output)
