"""Explicit, source-located Layer 3 output; free-text descriptions are not labels."""

from __future__ import annotations

from typing import get_args

from pydantic import Field

from .models import StrictModel
from .skeleton_contract import Intent

INTENT_VERSION = "skeleton-l3-v2-located-intent"
INTENT_LABELS = get_args(Intent)


class LocatedIntent(StrictModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=8000)
    evidence_quote: str = Field(min_length=1, max_length=24000)
    communicative_intent: str | None = Field(default=None, max_length=8000)
    qualifications: list[str] = Field(default_factory=list, max_length=100)


def validate_intent(result: dict, raw_text: str) -> dict:
    LocatedIntent.model_validate({k: v for k, v in result.items() if k != "_contract"})
    # Exact offsets are reproducible; do not normalize away signs, units or negation.
    if result["evidence_quote"] not in raw_text:
        raise ValueError("Layer 3 evidence_quote must be an exact contiguous source quotation")
    if any(not text.strip() or text not in raw_text for text in result.get("qualifications", [])):
        raise ValueError("Layer 3 qualifications must be exact source quotations")
    return result


def intent_coverage(sources: list[dict]) -> dict:
    typed = unknown = 0
    missing = []
    for source in sources:
        for unit in source["units"]:
            layer = unit.get("layer3") or {}
            value = str(layer.get("intent") or "").removeprefix("[Intent: ").removesuffix("]")
            if value in INTENT_LABELS or value in {"Claim", "Bold_Claim", "Result_Highlight", "Critical_Evaluation"}:
                typed += 1
                unknown += value == "UNKNOWN"
            else:
                missing.append({"skeleton_id": source["skeleton_id"], "unit_id": unit["unit_id"],
                                "raw_text": unit["raw_text"], "layer3": layer,
                                "reason": "MISSING_STRUCTURED_INTENT"})
    return {"typed_units": typed, "unknown_units": unknown, "unclassified_units": missing,
            "complete": not missing, "scientific_approval": False}
