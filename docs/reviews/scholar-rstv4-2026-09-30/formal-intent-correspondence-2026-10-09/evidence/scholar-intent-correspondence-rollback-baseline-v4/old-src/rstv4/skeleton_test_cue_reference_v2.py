"""Test-only unique claim IDs with all original cue and scientific source gates."""
from __future__ import annotations

from typing import Any

from rstv4.skeleton_boundary_reference_v4 import BoundarySourceReferenceBuilder
from rstv4.skeleton_test_cue_reference import PostCompileCueReferenceBuilder as PreviousBuilder

TEST_CUE_REFERENCE_VERSION = "post-compile-source-cue-and-explicit-unique-claim-id-v2"


class PostCompileCueReferenceBuilder(PreviousBuilder):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        original = self.drafts.atomic.original
        self.boundary_atomic = BoundarySourceReferenceBuilder(
            original.output, actual_model=kwargs["actual_model"],
            parent_references=original.parent_references,
        )
        self.drafts.atomic.original = self.boundary_atomic
