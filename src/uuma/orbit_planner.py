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

    def to_discovery_attempt(self) -> DiscoveryAttempt:
        return DiscoveryAttempt(
            provider=self.provider,
            query=self.query,
            outcome=self.outcome,
            tier=self.tier,
            artifacts_found=self.result_count,
            error_detail=self.reason if self.outcome != DiscoveryOutcome.SUCCESS else None,
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
            if p.name in {"canonical-citations", "openalex", "crossref"}
        ]
        self.web_providers = [
            p for p in providers
            if p.name in {"ddgs", "ddgs-academic", "brave"}
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
        deep_research_allowed: bool = False,
        is_provider_throttled: Any | None = None,
    ) -> tuple[list[DiscoveryArtifact], list[RouteAttempt], str | None]:
        """Execute tiered adaptive research, collecting artifacts and full decision trace."""
        from .safe_web import RetryAfterError

        artifacts: list[DiscoveryArtifact] = []
        traces: list[RouteAttempt] = []
        active_req_id: str | None = pending_request_id

        # Phase 0: If there's an ongoing asynchronous request (e.g. Deep Research), check it first
        chatgpt = self.chatgpt_providers[0] if self.chatgpt_providers else None
        if chatgpt and pending_request_id and hasattr(chatgpt, "check_status"):
            t0 = time.monotonic()
            try:
                resp = chatgpt.discover(
                    question, limit=limit, pending_request_id=pending_request_id
                )
                dur = (time.monotonic() - t0) * 1000
                if resp.in_progress:
                    traces.append(
                        RouteAttempt(
                            tier=3,
                            provider=chatgpt.name,
                            query=question,
                            status="IN_PROGRESS",
                            result_count=0,
                            reason="ChatGPT consultation is actively executing in background",
                            request_id=pending_request_id,
                            duration_ms=dur,
                            outcome=DiscoveryOutcome.SUCCESS,
                        )
                    )
                    return [], traces, pending_request_id
                if resp.artifacts:
                    traces.append(
                        RouteAttempt(
                            tier=3,
                            provider=chatgpt.name,
                            query=question,
                            status="SUCCESS",
                            result_count=len(resp.artifacts),
                            reason="Asynchronous ChatGPT consultation completed and retrieved",
                            request_id=pending_request_id,
                            duration_ms=dur,
                            outcome=DiscoveryOutcome.SUCCESS,
                        )
                    )
                    return resp.artifacts, traces, None
                else:
                    outcome = resp.outcome or DiscoveryOutcome.NO_MATCH
                    traces.append(
                        RouteAttempt(
                            tier=3,
                            provider=chatgpt.name,
                            query=question,
                            status="EMPTY",
                            result_count=0,
                            reason="Prior ChatGPT consultation completed with 0 usable sources",
                            request_id=pending_request_id,
                            duration_ms=dur,
                            outcome=outcome,
                        )
                    )
                    active_req_id = None
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Checking pending ChatGPT request %s failed: %s", pending_request_id, exc)
                traces.append(
                    RouteAttempt(
                        tier=3,
                        provider=chatgpt.name,
                        query=question,
                        status="FAILED",
                        result_count=0,
                        reason=f"Status check failed: {exc}",
                        request_id=pending_request_id,
                        duration_ms=(time.monotonic() - t0) * 1000,
                        outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                    )
                )
                active_req_id = None

        # Build progressive queries
        queries = reformulate_queries(question)

        # Tier 1: Scholarly / Academic Sources
        for provider in self.scholarly_providers:
            if callable(is_provider_throttled) and is_provider_throttled(provider.name):
                traces.append(
                    RouteAttempt(
                        1, provider.name, queries[0] if queries else question,
                        "THROTTLED", 0, "Provider limit reached",
                        outcome=DiscoveryOutcome.BUDGET_REACHED,
                    )
                )
                continue
            for q in queries[:2]:
                t0 = time.monotonic()
                try:
                    resp = provider.discover(q, limit=limit)
                    dur = (time.monotonic() - t0) * 1000
                    count = len(resp.artifacts)
                    outcome = resp.resolve_outcome() if hasattr(resp, "resolve_outcome") else (
                        DiscoveryOutcome.SUCCESS if count > 0 else DiscoveryOutcome.NO_MATCH
                    )
                    st = "SUCCESS" if count > 0 else "EMPTY"
                    reason = f"Primary scholarly search on {provider.name}"
                    traces.append(
                        RouteAttempt(
                            1, provider.name, q, st, count, reason,
                            request_id=getattr(resp, "request_id", None),
                            duration_ms=dur,
                            outcome=outcome,
                        )
                    )
                    artifacts.extend(resp.artifacts)
                    if count > 0:
                        break  # Found good results on this provider; no need to burn reformulated queries immediately
                except RetryAfterError as exc:
                    dur = (time.monotonic() - t0) * 1000
                    traces.append(
                        RouteAttempt(
                            1, provider.name, q, "RETRY_AFTER", 0,
                            f"Retry after {exc.retry_after_seconds}s",
                            metadata={"retry_after_seconds": exc.retry_after_seconds},
                            duration_ms=dur,
                            outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                        )
                    )
                    break
                except PermissionError as exc:
                    dur = (time.monotonic() - t0) * 1000
                    traces.append(
                        RouteAttempt(
                            1, provider.name, q, "FAILED", 0, f"Permission error: {exc}",
                            duration_ms=dur, outcome=DiscoveryOutcome.AUTH_REQUIRED,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    dur = (time.monotonic() - t0) * 1000
                    traces.append(
                        RouteAttempt(
                            1, provider.name, q, "FAILED", 0, f"Error: {exc}",
                            duration_ms=dur, outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                        )
                    )

        # Tier 2: General Web Search (Escalation if Tier 1 yielded zero results)
        if not artifacts and self.web_providers:
            web_queries = queries[:3]
            for provider in self.web_providers:
                if callable(is_provider_throttled) and is_provider_throttled(provider.name):
                    traces.append(
                        RouteAttempt(
                            2, provider.name, web_queries[0] if web_queries else question,
                            "THROTTLED", 0, "Provider limit reached",
                            outcome=DiscoveryOutcome.BUDGET_REACHED,
                        )
                    )
                    continue
                for q in web_queries:
                    t0 = time.monotonic()
                    try:
                        resp = provider.discover(q, limit=limit)
                        dur = (time.monotonic() - t0) * 1000
                        count = len(resp.artifacts)
                        outcome = resp.resolve_outcome() if hasattr(resp, "resolve_outcome") else (
                            DiscoveryOutcome.SUCCESS if count > 0 else DiscoveryOutcome.NO_MATCH
                        )
                        st = "SUCCESS" if count > 0 else "EMPTY"
                        reason = "Escalated to web search with reformulated queries"
                        traces.append(
                            RouteAttempt(
                                2, provider.name, q, st, count, reason,
                                request_id=getattr(resp, "request_id", None),
                                duration_ms=dur,
                                outcome=outcome,
                            )
                        )
                        artifacts.extend(resp.artifacts)
                        if count > 0:
                            break
                        if len(artifacts) >= 5:
                            break
                    except RetryAfterError as exc:
                        dur = (time.monotonic() - t0) * 1000
                        traces.append(
                            RouteAttempt(
                                2, provider.name, q, "RETRY_AFTER", 0,
                                f"Retry after {exc.retry_after_seconds}s",
                                metadata={"retry_after_seconds": exc.retry_after_seconds},
                                duration_ms=dur,
                                outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                            )
                        )
                        break
                    except PermissionError as exc:
                        dur = (time.monotonic() - t0) * 1000
                        traces.append(
                            RouteAttempt(
                                2, provider.name, q, "FAILED", 0, f"Permission error: {exc}",
                                duration_ms=dur, outcome=DiscoveryOutcome.AUTH_REQUIRED,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        dur = (time.monotonic() - t0) * 1000
                        traces.append(
                            RouteAttempt(
                                2, provider.name, q, "FAILED", 0, f"Error: {exc}",
                                duration_ms=dur, outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                            )
                        )
                if len(artifacts) >= 5:
                    break

        # Tier 3: AI Consultation & Deep Research (Escalation if Tier 1 and 2 yielded zero results)
        if not artifacts and chatgpt and not active_req_id:
            if callable(is_provider_throttled) and is_provider_throttled(chatgpt.name):
                traces.append(
                    RouteAttempt(
                        3, chatgpt.name, queries[0] if queries else question,
                        "THROTTLED", 0, "Provider limit reached",
                        outcome=DiscoveryOutcome.BUDGET_REACHED,
                    )
                )
            else:
                mode = "deep_research" if deep_research_allowed else getattr(chatgpt, "mode", "search")
                q = queries[0] if queries else question
                t0 = time.monotonic()
                try:
                    resp = chatgpt.discover(q, limit=limit, mode=mode)
                    dur = (time.monotonic() - t0) * 1000
                    count = len(resp.artifacts)
                    outcome = resp.resolve_outcome() if hasattr(resp, "resolve_outcome") else (
                        DiscoveryOutcome.SUCCESS if count > 0 else DiscoveryOutcome.NO_MATCH
                    )
                    if resp.in_progress:
                        active_req_id = resp.request_id
                        traces.append(
                            RouteAttempt(
                                3, chatgpt.name, q, "IN_PROGRESS", 0,
                                f"Initiated {mode} consultation; waiting for async result",
                                request_id=resp.request_id,
                                duration_ms=dur,
                                outcome=DiscoveryOutcome.SUCCESS,
                            )
                        )
                    else:
                        st = "SUCCESS" if count > 0 else "EMPTY"
                        reason = resp.error_detail or f"Consulted ChatGPT in {mode} mode"
                        traces.append(
                            RouteAttempt(
                                3, chatgpt.name, q, st, count, reason,
                                request_id=resp.request_id,
                                duration_ms=dur,
                                outcome=outcome,
                            )
                        )
                        artifacts.extend(resp.artifacts)
                except RetryAfterError as exc:
                    dur = (time.monotonic() - t0) * 1000
                    traces.append(
                        RouteAttempt(
                            3, chatgpt.name, q, "RETRY_AFTER", 0,
                            f"Retry after {exc.retry_after_seconds}s",
                            metadata={"retry_after_seconds": exc.retry_after_seconds},
                            duration_ms=dur,
                            outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                        )
                    )
                except PermissionError as exc:
                    dur = (time.monotonic() - t0) * 1000
                    traces.append(
                        RouteAttempt(
                            3, chatgpt.name, q, "FAILED", 0, f"Permission error: {exc}",
                            duration_ms=dur, outcome=DiscoveryOutcome.AUTH_REQUIRED,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    dur = (time.monotonic() - t0) * 1000
                    traces.append(
                        RouteAttempt(
                            3, chatgpt.name, q, "FAILED", 0, f"Error: {exc}",
                            duration_ms=dur, outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                        )
                    )

        # Tier 4: Supplementary feeds / domain scrapers / mock providers if still sparse
        if not artifacts and self.supplementary_providers:
            for provider in self.supplementary_providers:
                if callable(is_provider_throttled) and is_provider_throttled(provider.name):
                    traces.append(
                        RouteAttempt(
                            4, provider.name, queries[0] if queries else question,
                            "THROTTLED", 0, "Provider limit reached",
                            outcome=DiscoveryOutcome.BUDGET_REACHED,
                        )
                    )
                    continue
                for q in queries[:2]:
                    t0 = time.monotonic()
                    try:
                        resp = provider.discover(q, limit=limit)
                        dur = (time.monotonic() - t0) * 1000
                        count = len(resp.artifacts)
                        outcome = resp.resolve_outcome() if hasattr(resp, "resolve_outcome") else (
                            DiscoveryOutcome.SUCCESS if count > 0 else DiscoveryOutcome.NO_MATCH
                        )
                        st = "SUCCESS" if count > 0 else "EMPTY"
                        traces.append(
                            RouteAttempt(
                                4, provider.name, q, st, count, "Supplementary domain search",
                                request_id=getattr(resp, "request_id", None),
                                duration_ms=dur,
                                outcome=outcome,
                            )
                        )
                        artifacts.extend(resp.artifacts)
                        if count > 0:
                            break
                    except RetryAfterError as exc:
                        dur = (time.monotonic() - t0) * 1000
                        traces.append(
                            RouteAttempt(
                                4, provider.name, q, "RETRY_AFTER", 0,
                                f"Retry after {exc.retry_after_seconds}s",
                                metadata={"retry_after_seconds": exc.retry_after_seconds},
                                duration_ms=dur,
                                outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                            )
                        )
                        break
                    except PermissionError as exc:
                        dur = (time.monotonic() - t0) * 1000
                        traces.append(
                            RouteAttempt(
                                4, provider.name, q, "FAILED", 0, f"Permission error: {exc}",
                                duration_ms=dur, outcome=DiscoveryOutcome.AUTH_REQUIRED,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        dur = (time.monotonic() - t0) * 1000
                        traces.append(
                            RouteAttempt(
                                4, provider.name, q, "FAILED", 0, f"Error: {exc}",
                                duration_ms=dur, outcome=DiscoveryOutcome.TRANSIENT_FAILURE,
                            )
                        )

        # Deduplicate and sort by relevance & priority
        seen: set[str] = set()
        deduped: list[DiscoveryArtifact] = []
        for art in artifacts:
            if not artifact_is_relevant(question, art):
                continue
            ident = artifact_identity(art)
            if ident not in seen:
                seen.add(ident)
                deduped.append(art)

        deduped.sort(key=lambda a: artifact_priority(question, a), reverse=True)
        return deduped, traces, active_req_id

    def compute_cycle_explanation(
        self,
        question: str,
        traces: list[RouteAttempt],
        status: str,
    ) -> CycleExplanation:
        all_providers = [p.name for p in self.providers]
        attempted_providers = {t.provider for t in traces}
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
