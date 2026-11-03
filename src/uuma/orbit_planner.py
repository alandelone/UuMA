"""Adaptive research planner for Question Orbit discovery.

Provides dynamic query reformulation, tiered source escalation, and white-box
decision chain tracing as required by docs/architecture/agent-research-tools.md.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .orbit_discovery import (
    CycleExplanation,
    DiscoveryArtifact,
    DiscoveryAttempt,
    DiscoveryOutcome,
    DiscoveryProvider,
    artifact_identity,
    artifact_is_relevant,
    artifact_priority,
    discovery_queries,
)

LOGGER = logging.getLogger(__name__)

# Specialized domain term substitutions (Chinese <-> English / Scientific)
_DOMAIN_SYNONYMS: dict[str, list[str]] = {
    "青葱": ["Allium fistulosum", "Welsh onion", "scallion"],
    "大葱": ["Allium fistulosum", "scallion", "spring onion"],
    "四季葱": ["Allium fistulosum", "Welsh onion"],
    "分株": ["plant division", "vegetative propagation", "splitting"],
    "缓苗": ["rooting recovery", "transplant acclimation", "seedling recovery"],
    "缓苗期": ["transplant recovery period", "acclimation duration", "root establishment"],
    "气雾培": ["aeroponics", "fogponics", "mist cultivation"],
    "气雾耕": ["aeroponics", "fogponics", "high pressure aeroponics"],
    "喷雾参数": ["misting cycle", "spray interval", "droplet size"],
    "营养液": ["nutrient solution", "EC pH electrical conductivity", "Hoagland solution"],
}


def reformulate_queries(question: str, attempted_queries: list[str] | None = None) -> list[str]:
    """Generate focused, alternative and cross-lingual queries for tough knowledge gaps."""
    attempted = set(attempted_queries or [])
    candidates: list[str] = []

    # 1. Base query list from standard heuristics
    base_queries = discovery_queries(question)
    for q in base_queries:
        if q not in attempted and q not in candidates:
            candidates.append(q)

    # 2. Extract key domain terms and build technical cross-lingual queries
    extracted_terms: list[str] = []
    for term, syns in _DOMAIN_SYNONYMS.items():
        if term in question:
            extracted_terms.extend(syns)

    if extracted_terms:
        # Build concise scientific query
        tech_q = " ".join(extracted_terms[:4])
        if tech_q not in attempted and tech_q not in candidates:
            candidates.append(tech_q)

    # 3. Strip conversational noise and build concise core phrase
    cleaned = re.sub(
        r"我想了解|我想知道|针对|关于|请研究|请问|细节|核心|构建|要素|怎么做|如何做|是什么|以及|与|和|的|具体运行参数|有何具体来源或试验数据",
        " ",
        question,
    )
    cleaned_tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 2]
    if len(cleaned_tokens) >= 2:
        concise_q = " ".join(cleaned_tokens[:6])
        if concise_q not in attempted and concise_q not in candidates:
            candidates.append(concise_q)

    return candidates or [question]


@dataclass
class RouteAttempt:
    tier: int
    provider: str
    query: str
    status: str
    result_count: int
    reason: str
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    outcome: DiscoveryOutcome = DiscoveryOutcome.SUCCESS
    error_detail: str | None = None

    def __post_init__(self) -> None:
        if self.error_detail is None and self.outcome != DiscoveryOutcome.SUCCESS:
            self.error_detail = self.reason

    def to_discovery_attempt(self) -> DiscoveryAttempt:
        return DiscoveryAttempt(
            provider=self.provider,
            query=self.query,
            outcome=self.outcome,
            tier=self.tier,
            artifacts_found=self.result_count,
            error_detail=self.error_detail,
            duration_ms=self.duration_ms,
            request_id=self.request_id,
            metadata={"tier": self.tier, **self.metadata},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "provider": self.provider,
            "query": self.query,
            "status": self.status,
            "result_count": self.result_count,
            "reason": self.reason,
            "request_id": self.request_id,
            "error_detail": self.error_detail,
            "metadata": self.metadata,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome.value if hasattr(self.outcome, "value") else str(self.outcome),
        }


class AdaptiveResearchPlanner:
    """Orchestrates multi-tier discovery with dynamic fallback and white-box traces."""

    def __init__(self, providers: list[DiscoveryProvider]) -> None:
        self.providers = providers
        self.scholarly_providers = [
            p for p in providers
            if p.name in {"canonical-citations", "openalex", "crossref", "ddgs-academic"}
        ]
        self.web_providers = [
            p for p in providers
            if p.name in {"ddgs", "brave"}
        ]
        self.chatgpt_providers = [
            p for p in providers
            if p.name == "chatgpt-bridge"
        ]
        self.supplementary_providers = [
            p for p in providers
            if p.name not in {
                "canonical-citations", "openalex", "crossref",
                "ddgs", "ddgs-academic", "brave", "chatgpt-bridge"
            }
        ]

    def execute_discovery(
        self,
        question: str,
        *,
        limit: int = 10,
        pending_request_id: str | None = None,
        pending_provider: str | None = None,
        deep_research_allowed: bool = True,
        is_provider_throttled: Any | None = None,
        start_tier: int = 1,
    ) -> tuple[list[DiscoveryArtifact], list[RouteAttempt], str | None]:
        """Research first, then academic, web and supplemental sources.

        A result batch returns to the runner for ingestion and independent critique.
        The persisted start_tier advances after an insufficient critique. Empty or
        irrelevant results may fall through immediately; a pending request never does.
        """
        from .research_quota import quota_delay
        from .safe_web import RetryAfterError

        traces: list[RouteAttempt] = []
        queries = reformulate_queries(question)
        if not 1 <= start_tier <= 4:
            raise ValueError("Discovery tier must be between 1 and 4")

        def invoke(provider, query, tier, *, pending=None):
            started = time.monotonic()
            phase = "poll" if pending else "submit"
            try:
                kwargs = {"limit": limit}
                if pending:
                    kwargs["pending_request_id"] = pending
                if tier == 1:
                    kwargs["mode"] = (
                        "deep_research" if deep_research_allowed
                        else getattr(provider, "mode", "search")
                    )
                response = provider.discover(query, **kwargs)
                artifacts = []
                seen = set()
                for artifact in response.artifacts:
                    identity = artifact_identity(artifact)
                    if identity not in seen and artifact_is_relevant(question, artifact):
                        artifacts.append(artifact)
                        seen.add(identity)
                outcome = response.resolve_outcome()
                if not artifacts and not response.in_progress and outcome == DiscoveryOutcome.SUCCESS:
                    outcome = DiscoveryOutcome.NO_MATCH
                status = "IN_PROGRESS" if response.in_progress else (
                    "SUCCESS" if artifacts else "EMPTY"
                )
                traces.append(RouteAttempt(
                    tier, provider.name, query, status, len(artifacts),
                    response.error_detail or (
                        "Waiting for asynchronous Deep Research" if response.in_progress
                        else "Collected a batch for independent coverage review"
                    ),
                    request_id=response.request_id or pending,
                    metadata={"request_phase": phase},
                    duration_ms=(time.monotonic() - started) * 1000,
                    outcome=outcome,
                    error_detail=response.error_detail,
                ))
                return artifacts, response.request_id if response.in_progress else None
            except RetryAfterError as exc:
                traces.append(RouteAttempt(
                    tier, provider.name, query, "RETRY_AFTER", 0,
                    f"Retry after {exc.retry_after_seconds}s",
                    request_id=pending,
                    metadata={"retry_after_seconds": exc.retry_after_seconds,
                              "quota_wait": quota_delay(exc) is not None,
                              "request_phase": phase},
                    duration_ms=(time.monotonic() - started) * 1000,
                    outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                ))
            except Exception as exc:  # noqa: BLE001 - isolate optional provider failures
                delay = quota_delay(exc)
                traces.append(RouteAttempt(
                    tier, provider.name, query, "RETRY_AFTER" if delay else "FAILED", 0,
                    type(exc).__name__, request_id=pending,
                    metadata={"request_phase": phase,
                              **({"retry_after_seconds": delay, "quota_wait": True} if delay else {})},
                    duration_ms=(time.monotonic() - started) * 1000,
                    outcome=(DiscoveryOutcome.AUTH_REQUIRED if isinstance(exc, PermissionError)
                             else DiscoveryOutcome.TRANSIENT_FAILURE),
                ))
            return [], pending

        if pending_request_id:
            owner = next((p for p in self.providers
                          if p.name == (pending_provider or "chatgpt-bridge")), None)
            if owner is None:
                raise PermissionError("The pending research request has no configured provider")
            pending_tier = 1 if owner in self.chatgpt_providers else 4
            artifacts, pending = invoke(owner, question, pending_tier, pending=pending_request_id)
            # A poll failure is ambiguous. Preserve the request instead of submitting a duplicate.
            if pending or artifacts:
                return artifacts, traces, pending
            if traces[-1].outcome in {
                DiscoveryOutcome.TRANSIENT_FAILURE, DiscoveryOutcome.AUTH_REQUIRED,
            } and not (traces[-1].error_detail and "PAUSED" in str(traces[-1].error_detail)):
                return [], traces, pending_request_id
            if pending_tier == 4:
                return [], traces, None
            start_tier = max(2, start_tier)

        stages = (
            (1, self.chatgpt_providers, [question]),
            (2, self.scholarly_providers, queries[:2]),
            (3, self.web_providers, queries[:3]),
            (4, self.supplementary_providers, queries[:2]),
        )
        for tier, providers, stage_queries in stages:
            if tier < start_tier:
                continue
            artifacts = []
            for provider in providers:
                if callable(is_provider_throttled) and is_provider_throttled(provider.name):
                    traces.append(RouteAttempt(
                        tier, provider.name, stage_queries[0], "THROTTLED", 0,
                        "Provider limit reached", outcome=DiscoveryOutcome.BUDGET_REACHED,
                    ))
                    continue
                for query in stage_queries:
                    batch, pending = invoke(provider, query, tier)
                    if pending:
                        return [], traces, pending
                    artifacts.extend(batch)
                    if batch or traces[-1].outcome in {
                        DiscoveryOutcome.TRANSIENT_FAILURE, DiscoveryOutcome.AUTH_REQUIRED,
                    }:
                        break
                if len(artifacts) >= limit:
                    break
            if artifacts:
                unique = {artifact_identity(artifact): artifact for artifact in artifacts}
                ranked = sorted(unique.values(), key=lambda a: artifact_priority(question, a),
                                reverse=True)
                return ranked[:limit], traces, None
        return [], traces, None

    def compute_cycle_explanation(
        self,
        question: str,
        traces: list[RouteAttempt],
        status: str,
    ) -> CycleExplanation:
        all_providers = [p.name for p in self.providers]
        attempted_providers = {
            t.provider for t in traces
            if t.outcome not in {DiscoveryOutcome.SKIPPED}
        }
        blocked_providers = {
            t.provider for t in traces
            if t.outcome in {DiscoveryOutcome.AUTH_REQUIRED, DiscoveryOutcome.BUDGET_REACHED}
            or t.status in {"THROTTLED"}
        }
        untried_paths = [
            p for p in all_providers
            if p not in attempted_providers and p not in blocked_providers
        ]

        attempts = [t.to_discovery_attempt() for t in traces]
        success_cnt = sum(1 for a in attempts if a.outcome == DiscoveryOutcome.SUCCESS)
        no_match_cnt = sum(1 for a in attempts if a.outcome == DiscoveryOutcome.NO_MATCH)
        blocked_cnt = sum(
            1 for a in attempts
            if a.outcome in {DiscoveryOutcome.AUTH_REQUIRED, DiscoveryOutcome.BUDGET_REACHED}
        )

        summary_parts = [
            f"本轮共执行 {len(attempts)} 次检索尝试（{success_cnt} 次成功，{no_match_cnt} 次无直接匹配，{blocked_cnt} 次受阻）。"
        ]
        if untried_paths:
            summary_parts.append(f"尚有待探索途径：{', '.join(untried_paths)}。")
        if blocked_providers:
            summary_parts.append(f"受阻途径：{', '.join(blocked_providers)}。")

        if untried_paths:
            next_step = f"下阶段将调度待探索途径（{untried_paths[0]} 等）继续深入挖掘。"
        elif blocked_providers and not success_cnt:
            next_step = "待配置必要凭据或配额恢复后解除阻断。"
        else:
            next_step = "已完成全部已授权途径探索。"

        return CycleExplanation(
            status=status,
            summary=" ".join(summary_parts),
            attempts=attempts,
            untried_paths=untried_paths,
            blocked_paths=list(blocked_providers),
            next_step=next_step,
        )
