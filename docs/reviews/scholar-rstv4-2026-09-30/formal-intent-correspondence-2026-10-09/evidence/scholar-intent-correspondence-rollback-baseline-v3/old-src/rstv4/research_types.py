from __future__ import annotations

from typing import Any

from .models import ResearchType

REQUIRED_BLOCKS: dict[ResearchType, tuple[str, ...]] = {
    ResearchType.EXPERIMENTAL: (
        "hypothesis",
        "experiment_design",
        "data",
        "evaluation",
        "reproducibility",
    ),
    ResearchType.ENGINEERING_SYSTEM: (
        "requirements",
        "system_design",
        "implementation",
        "validation",
    ),
    ResearchType.METHOD_ALGORITHM: (
        "method",
        "comparison",
        "datasets",
        "evaluation",
        "implementation",
    ),
    ResearchType.SYSTEMATIC_REVIEW: (
        "review_question",
        "search_protocol",
        "eligibility",
        "screening",
        "extraction",
        "quality_assessment",
        "synthesis",
    ),
    ResearchType.SOTA_REVIEW: (
        "landscape",
        "temporal_analysis",
        "comparison",
        "synthesis",
        "feasibility",
    ),
    ResearchType.CRITICAL_REVIEW: (
        "central_argument",
        "evidence_structure",
        "critique",
        "synthesis",
    ),
    ResearchType.BIBLIOMETRIC_REVIEW: ("dataset", "metrics", "network_analysis", "clustering"),
    ResearchType.CONCEPTUAL_FRAMEWORK: (
        "concepts",
        "theory",
        "relationships",
        "framework",
        "validation_plan",
    ),
    ResearchType.CASE_STUDY: ("case", "questions", "evidence", "analysis", "generalization"),
}


def validate_type_payload(research_type: ResearchType, payload: dict[str, Any]) -> None:
    missing = [block for block in REQUIRED_BLOCKS[research_type] if block not in payload]
    if missing:
        raise ValueError(
            f"{research_type.value} requires blocks: {', '.join(missing)}. "
            "Use empty objects for blocks that will be completed later."
        )
