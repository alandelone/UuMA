from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ReviewCriterion:
    name: str
    description: str
    weight: float


DEFAULT_CRITERIA = [
    ReviewCriterion(
        "novelty", "Is the research gap clearly validated against existing literature?", 0.25
    ),
    ReviewCriterion(
        "soundness", "Is the methodology theoretically sound and rigorously described?", 0.25
    ),
    ReviewCriterion(
        "empirical_evidence",
        "Are claims backed by reproducible experimental or literature evidence?",
        0.30,
    ),
    ReviewCriterion(
        "clarity_and_limitations",
        "Are assumptions, boundary conditions, and threats to validity transparently stated?",
        0.20,
    ),
]


class ReviewSimulator:
    """Simulates critical academic peer review (Phase 4) against the Research Blueprint."""

    @staticmethod
    def evaluate_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
        approved_nodes = blueprint.get("approved", [])

        gaps = [n for n in approved_nodes if n.get("kind") == "gap"]
        rqs = [n for n in approved_nodes if n.get("kind") == "research_question"]
        hypotheses = [n for n in approved_nodes if n.get("kind") == "hypothesis"]
        methods = [n for n in approved_nodes if n.get("kind") == "method"]
        claims = [n for n in approved_nodes if n.get("kind") == "claim"]

        strengths: list[str] = []
        weaknesses: list[str] = []
        recommendations: list[str] = []

        # Check Gap validation
        if gaps:
            evidence_count = sum(len(g.get("provenance", {}).get("evidence", [])) for g in gaps)
            if evidence_count > 0:
                strengths.append(f"Gaps are grounded in {evidence_count} explicit evidence items.")
            else:
                weaknesses.append("Research gaps lack direct supporting literature evidence.")
        else:
            weaknesses.append("No explicit research gap defined in current Blueprint.")

        rq_ids = {node["node_id"] for node in rqs}
        aligned_methods = [
            node
            for node in methods
            if rq_ids.intersection(node.get("payload", {}).get("upstream_node_ids", []))
        ]
        if rqs and len(aligned_methods) == len(methods) and methods:
            strengths.append(
                "Every approved Method explicitly references an approved Research Question."
            )
        elif rqs and not methods:
            weaknesses.append(
                "Research Questions defined but lacking concrete approved Method specification."
            )
        elif methods and not rqs:
            weaknesses.append(
                "Methods proposed without formal Research Questions guiding their evaluation."
            )
        elif methods:
            weaknesses.append(
                "One or more Methods lack an explicit dependency on a Research Question."
            )

        # Check Claim evidence backing
        unbacked_claims = 0
        unassessed_claims = 0
        for c in claims:
            evs = c.get("provenance", {}).get("evidence", [])
            if not evs:
                unbacked_claims += 1
            if not c.get("provenance", {}).get("assessments", []):
                unassessed_claims += 1

        if claims and unbacked_claims == 0:
            strengths.append("All approved claims have linked empirical or literature evidence.")
        elif unbacked_claims > 0:
            weaknesses.append(
                f"{unbacked_claims} claim(s) lack supporting evidence nodes in the dependency graph."
            )
            recommendations.append(
                "Conduct targeted experiments or literature extraction to back all claims before submission."
            )
        if unassessed_claims:
            weaknesses.append(
                f"{unassessed_claims} claim(s) have no recorded content-level evidence assessment."
            )
            recommendations.append(
                "Assess claim meaning against located excerpts, conditions, and counterevidence."
            )

        return {
            "structural_status": "COMPLETE" if not weaknesses else "INCOMPLETE",
            "scientific_status": "NEEDS_HUMAN_REVIEW",
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "node_breakdown": {
                "gaps": len(gaps),
                "research_questions": len(rqs),
                "hypotheses": len(hypotheses),
                "methods": len(methods),
                "claims": len(claims),
            },
        }


class RebuttalPlanner:
    """Plans revisions and re-openings based on reviewer weaknesses."""

    @staticmethod
    def plan_rebuttal(review_report: dict[str, Any]) -> list[dict[str, str]]:
        actions: list[dict[str, str]] = []
        weaknesses = review_report.get("weaknesses", [])

        for idx, w in enumerate(weaknesses, 1):
            if "evidence" in w.lower():
                actions.append(
                    {
                        "concern_id": f"W{idx}",
                        "concern": w,
                        "action_type": "COLLECT_EVIDENCE",
                        "proposal": "Extract additional evidence from literature catalog or run replication experiments.",
                    }
                )
            elif "method" in w.lower():
                actions.append(
                    {
                        "concern_id": f"W{idx}",
                        "concern": w,
                        "action_type": "REFINE_METHOD",
                        "proposal": "Propose an updated method revision detailing baselines, parameters, and boundary conditions.",
                    }
                )
            else:
                actions.append(
                    {
                        "concern_id": f"W{idx}",
                        "concern": w,
                        "action_type": "CLARIFY_TEXT",
                        "proposal": "Clarify assumptions and limitations in the manuscript discussion section.",
                    }
                )

        return actions
