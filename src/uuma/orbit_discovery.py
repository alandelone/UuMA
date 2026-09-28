from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .knowledge_service import KnowledgeService
from .safe_web import SafeWebFetcher

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveryArtifact:
    locator: str
    title: str
    provider: str
    snippet: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryResponse:
    artifacts: list[DiscoveryArtifact]
    request_id: str | None = None


_GENERIC_CJK = {
    "针对", "关于", "请问", "研究", "了解", "知道", "什么", "如何", "怎么", "怎样",
    "细节", "核心", "构建", "要素", "方法", "技术", "问题", "系统", "主要",
    "核心构建要素", "这个", "那个", "可以", "是否", "以及",
}
_GENERIC_ENGLISH = {
    "about", "what", "which", "when", "where", "does", "with", "from", "that",
    "this", "these", "those", "please", "research", "explain", "detail", "details",
    "core", "system", "systems", "technical", "method", "methods", "topic",
    "cultivation", "growing", "agriculture", "plant", "plants",
}
_CJK_FILLER = re.compile(
    r"我想了解|我想知道|针对|关于|请研究|请问|细节|核心|构建|要素|"
    r"怎么做|如何做|是什么|以及|与|和|的"
)


def relevance_terms(question: str) -> set[str]:
    """Conservative lexical anchors used to reject obviously unrelated search hits."""
    text = question.casefold()
    terms = {
        token for token in re.findall(r"[a-z][a-z0-9-]{3,}", text)
        if token not in _GENERIC_ENGLISH
    }
    for run in re.findall(r"[\u3400-\u9fff]+", _CJK_FILLER.sub(" ", text)):
        if run in _GENERIC_CJK:
            continue
        if len(run) == 2:
            terms.add(run)
            continue
        terms.add(run)
        if run.endswith("法") and len(run) == 3:
            terms.add(run[:-1])
        for width in (3, 4):
            terms.update(
                part for index in range(len(run) - width + 1)
                if (part := run[index:index + width]) not in _GENERIC_CJK
            )
    if "青葱" in text or "香葱" in text or "小葱" in text:
        terms.update({
            "allium fistulosum", "scallion", "green onion", "bunching onion", "welsh onion",
            "onions, green bunching",
        })
    return terms


def discovery_query(question: str) -> str:
    """Remove conversational filler before querying academic search providers."""
    runs = []
    for run in re.findall(r"[\u3400-\u9fff]+", _CJK_FILLER.sub(" ", question)):
        if len(run) > 1 and run not in _GENERIC_CJK:
            runs.append(run)
    words = [
        word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}", question)
        if word.casefold() not in _GENERIC_ENGLISH
    ]
    return " ".join(dict.fromkeys([*runs, *words]))[:200] or question[:200]


def discovery_queries(question: str) -> list[str]:
    """Search a named crop in its original language and scientific-name form."""
    primary = discovery_query(question)
    alternatives = [primary]
    if any(name in question for name in ("青葱", "香葱", "小葱")):
        if any(term in question for term in ("缓苗", "成活率", "病害管理")):
            alternatives.extend([
                "Allium fistulosum division transplant establishment survival",
                "Welsh onion vegetative propagation transplant recovery disease",
            ])
        if any(term in question for term in ("喷雾间隔", "喷头", "雾化间隔")):
            alternatives.extend([
                "Allium fistulosum aeroponic mist interval nutrient solution nozzle",
                "Welsh onion fogoponic misting nutrient solution",
            ])
        methods = []
        if "气雾" in question or "雾培" in question:
            methods.append("aeroponics")
        if "分株" in question:
            methods.append("division propagation")
        alternatives.append("Allium fistulosum " + " ".join(methods or ["cultivation"]))
    return list(dict.fromkeys(alternatives))


def artifact_is_relevant(question: str, artifact: DiscoveryArtifact) -> bool:
    if artifact.provider == "user-url":
        return True
    crop = _scallion_variants(question)
    if crop:
        canonical_excerpt = artifact.snippet if artifact.provider == "canonical" else ""
        haystack = f"{artifact.title} {artifact.locator} {canonical_excerpt}".casefold()
        if not any(term in haystack for term in crop):
            return False
        if any(term in question for term in ("喷雾间隔", "喷头", "雾化间隔")) and not any(
            term in haystack for term in ("气雾", "雾培", "aeroponic", "fogoponic")
        ):
            return False
        if any(term in question for term in ("缓苗", "成活率", "病害管理")):
            recovery_terms = (
                "缓苗", "移栽", "成活", "病害", "分株", "恢复", "定植",
                "transplant", "survival", "establishment", "division",
                "disease", "vegetative propagation", "recovery",
            )
            return any(term in haystack for term in recovery_terms)
        if any(term in question for term in ("气雾", "雾培", "分株", "栽培", "种植")) or (
            re.search(r"种(?:青葱|香葱|小葱)", question)
        ):
            methods = (
                "气雾", "雾培", "分株", "分蘖", "栽培", "种植", "繁殖",
                "aeroponic", "fogoponic", "hydroponic", "cultivation",
                "propagation", "division", "tiller", "bunching", "horticulture", "growing",
            )
            return any(term in haystack for term in methods)
        return True
    terms = relevance_terms(question)
    if not terms:
        return False
    haystack = f"{artifact.title} {artifact.locator}".casefold()
    return any(term in haystack for term in terms)


def artifact_priority(question: str, artifact: DiscoveryArtifact) -> int:
    """Prefer a source about the named subject over a general method source."""
    title = artifact.title.casefold()
    query_terms = discovery_query(question).casefold().split()
    score = sum(2 for term in query_terms if term in title)
    if "青葱" in question and any(
        crop in title for crop in ("青葱", "小葱", "香葱", "葱", "scallion", "green onion")
    ):
        score += 4
    return score


def _subject_variants(question: str) -> tuple[str, ...]:
    crop = _scallion_variants(question)
    if crop:
        return crop
    runs = discovery_query(question).split()
    if not runs or not re.fullmatch(r"[\u3400-\u9fff]+", runs[0]):
        return ()
    first = runs[0]
    for method in ("气雾栽培", "水培", "分株", "栽培", "种植"):
        position = first.find(method)
        if position > 0:
            first = first[:position]
            break
    if first.startswith("种") and len(first) > 2:
        first = first[1:]
    if not 2 <= len(first) <= 5:
        return ()
    return (first,)


def _scallion_variants(question: str) -> tuple[str, ...]:
    if not any(name in question for name in ("青葱", "小葱", "香葱")):
        return ()
    return (
        "青葱", "小葱", "香葱", "scallion", "green onion",
        "bunching onion", "welsh onion", "allium fistulosum",
        "onions, green bunching",
    )


def citations_fit_question(
    knowledge: KnowledgeService, question: str, citations: list[dict[str, object]]
) -> bool:
    """A citation only grounds an answer when its canonical source matches the question."""
    if not citations:
        return False
    subject = _subject_variants(question)
    subject_found = not subject
    for citation in citations:
        source_id = citation.get("source_id") if isinstance(citation, dict) else None
        source = knowledge.store.get_record("sources", str(source_id)) if source_id else None
        if not source:
            return False
        evidence_id = citation.get("evidence_id")
        evidence = (
            knowledge.store.get_record("evidence", str(evidence_id)) if evidence_id else None
        )
        chunk_id = citation.get("chunk_id")
        chunk = knowledge.store.get_record("chunks", str(chunk_id)) if chunk_id else None
        artifact = DiscoveryArtifact(
            locator=str(source.get("locator") or ""),
            title=str(source.get("title") or ""),
            provider="canonical",
            snippet=f"{(evidence or {}).get('excerpt') or ''} {(chunk or {}).get('text') or ''}",
        )
        if not artifact_is_relevant(question, artifact):
            return False
        if any(variant in artifact.title.casefold() for variant in subject):
            subject_found = True
    return subject_found


class DiscoveryProvider(Protocol):
    name: str

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse: ...


def artifact_identity(artifact: DiscoveryArtifact) -> str:
    doi = str(artifact.metadata.get("doi") or "").strip().casefold()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
    parsed = urlsplit(artifact.locator)
    if not doi and (parsed.hostname or "").casefold() in {"doi.org", "dx.doi.org"}:
        doi = parsed.path.lstrip("/").casefold()
    if doi:
        return f"doi:{doi}"
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    netloc = hostname
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in {"gclid", "fbclid"}
        )
    )
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))


class _JsonProvider:
    name: str

    def __init__(self, fetcher: SafeWebFetcher | None = None) -> None:
        self.fetcher = fetcher or SafeWebFetcher(maximum_bytes=5 * 1024 * 1024)

    def _json(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[dict, dict[str, str]]:
        fetched = self.fetcher.fetch(
            url,
            accept="application/json",
            allowed_content_types={"application/json", "application/vnd.api+json"},
            check_robots=False,
            extra_headers=headers,
        )
        payload = json.loads(fetched.body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"{self.name} returned a non-object JSON response.")
        return payload, fetched.headers


class CanonicalCitationProvider:
    name = "canonical-citations"

    def __init__(self, knowledge: KnowledgeService) -> None:
        self.knowledge = knowledge

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        artifacts: list[DiscoveryArtifact] = []
        seen: set[str] = set()
        for result in self.knowledge.search(query, limit=25)["results"]:
            record = result["record"]
            candidates: list[str] = []
            locator = record.get("locator")
            if isinstance(locator, str):
                candidates.append(locator)
            text = " ".join(
                str(record.get(field) or "")
                for field in ("text", "excerpt", "surrounding_context", "statement")
            )
            candidates.extend(re.findall(r"https?://[^\s<>\]\[)]+", text))
            candidates.extend(
                f"https://doi.org/{doi}"
                for doi in re.findall(
                    r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.IGNORECASE
                )
            )
            for candidate in candidates:
                artifact = DiscoveryArtifact(
                    candidate.rstrip(".,;"),
                    str(record.get("title") or candidate),
                    self.name,
                    metadata={"canonical_ref": result.get("kind")},
                )
                identity = artifact_identity(artifact)
                if identity in seen:
                    continue
                seen.add(identity)
                artifacts.append(artifact)
                if len(artifacts) >= limit:
                    return DiscoveryResponse(artifacts)
        return DiscoveryResponse(artifacts)


class OpenAlexProvider(_JsonProvider):
    name = "openalex"

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        params = {"search": query, "per-page": max(1, min(limit, 20))}
        mailto = os.environ.get("UUMA_OPENALEX_MAILTO", "").strip()
        if mailto:
            params["mailto"] = mailto
        payload, headers = self._json(f"https://api.openalex.org/works?{urlencode(params)}")
        artifacts: list[DiscoveryArtifact] = []
        for work in payload.get("results", []):
            if not isinstance(work, dict):
                continue
            best = work.get("best_oa_location") or work.get("primary_location") or {}
            locator = (
                best.get("pdf_url")
                or best.get("landing_page_url")
                or work.get("doi")
                or work.get("id")
            )
            title = str(work.get("title") or "Untitled OpenAlex work")
            if not isinstance(locator, str) or not locator.startswith(("http://", "https://")):
                continue
            abstract = self._abstract(work.get("abstract_inverted_index"))
            artifacts.append(
                DiscoveryArtifact(
                    locator=locator,
                    title=title,
                    provider=self.name,
                    snippet=abstract,
                    metadata={"openalex_id": work.get("id"), "doi": work.get("doi")},
                )
            )
        return DiscoveryResponse(artifacts, headers.get("x-request-id"))

    @staticmethod
    def _abstract(index: object) -> str:
        if not isinstance(index, dict):
            return ""
        positions: list[tuple[int, str]] = []
        for word, offsets in index.items():
            if isinstance(offsets, list):
                positions.extend((int(offset), str(word)) for offset in offsets)
        return " ".join(word for _, word in sorted(positions))


class CrossrefProvider(_JsonProvider):
    name = "crossref"

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        params = {
            "query": query,
            "rows": max(1, min(limit, 20)),
            "select": "DOI,title,URL,abstract,published,author",
        }
        payload, headers = self._json(f"https://api.crossref.org/works?{urlencode(params)}")
        message = payload.get("message") or {}
        artifacts: list[DiscoveryArtifact] = []
        for work in message.get("items", []):
            if not isinstance(work, dict):
                continue
            locator = work.get("URL")
            titles = work.get("title") or []
            title = str(titles[0]) if titles else str(work.get("DOI") or "Untitled Crossref work")
            if not isinstance(locator, str) or not locator.startswith(("http://", "https://")):
                continue
            abstract = re.sub(r"<[^>]+>", " ", str(work.get("abstract") or ""))
            artifacts.append(
                DiscoveryArtifact(
                    locator=locator,
                    title=title,
                    provider=self.name,
                    snippet=re.sub(r"\s+", " ", abstract).strip(),
                    metadata={"doi": work.get("DOI")},
                )
            )
        return DiscoveryResponse(artifacts, headers.get("x-request-id"))


class BraveSearchProvider(_JsonProvider):
    name = "brave"

    def __init__(self, api_key: str, fetcher: SafeWebFetcher | None = None) -> None:
        super().__init__(fetcher)
        self.api_key = api_key

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        params = {"q": query, "count": max(1, min(limit, 20))}
        payload, headers = self._json(
            f"https://api.search.brave.com/res/v1/web/search?{urlencode(params)}",
            headers={"X-Subscription-Token": self.api_key},
        )
        artifacts = []
        for result in (payload.get("web") or {}).get("results", []):
            locator = result.get("url") if isinstance(result, dict) else None
            if not isinstance(locator, str) or not locator.startswith(("http://", "https://")):
                continue
            artifacts.append(
                DiscoveryArtifact(
                    locator=locator,
                    title=str(result.get("title") or locator),
                    provider=self.name,
                    snippet=str(result.get("description") or ""),
                )
            )
        return DiscoveryResponse(artifacts, headers.get("x-request-id"))


class DdgsSearchProvider:
    def __init__(self, *, academic: bool = False) -> None:
        self.academic = academic
        self.name = "ddgs-academic" if academic else "ddgs"

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        from ddgs import DDGS

        cjk_terms = re.findall(r"[\u3400-\u9fff]+", query)
        search_query = (
            f"{max(cjk_terms, key=len)} site:edu.cn" if self.academic and cjk_terms
            else f"{query} site:edu" if self.academic
            else query
        )
        artifacts = []
        for result in DDGS(timeout=12).text(search_query, max_results=max(1, min(limit, 10))):
            locator = result.get("href") if isinstance(result, dict) else None
            if not isinstance(locator, str) or not locator.startswith(("http://", "https://")):
                continue
            artifacts.append(DiscoveryArtifact(
                locator=locator,
                title=str(result.get("title") or locator),
                provider=self.name,
                snippet=str(result.get("body") or ""),
            ))
        return DiscoveryResponse(artifacts)


class FeedSitemapProvider:
    name = "feed-sitemap"

    def __init__(self, seeds: list[str], fetcher: SafeWebFetcher | None = None) -> None:
        self.seeds = list(dict.fromkeys(seeds))
        self.fetcher = fetcher or SafeWebFetcher(maximum_bytes=5 * 1024 * 1024)

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        terms = {term.casefold() for term in re.findall(r"[\w-]{3,}", query)}
        artifacts: list[DiscoveryArtifact] = []
        for seed in self.seeds:
            fetched = self.fetcher.fetch(
                seed,
                accept="application/rss+xml,application/atom+xml,application/xml,text/xml",
                allowed_content_types={
                    "application/atom+xml",
                    "application/rss+xml",
                    "application/xml",
                    "text/xml",
                },
            )
            upper_prefix = fetched.body[:4096].upper()
            if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
                raise ValueError("Feed and sitemap XML must not declare document types or entities.")
            root = ET.fromstring(fetched.body)
            for element in root.iter():
                local = element.tag.rsplit("}", 1)[-1].lower()
                if local not in {"item", "entry", "url"}:
                    continue
                title = self._child_text(element, "title") or "Feed or sitemap result"
                locator = self._child_text(element, "loc") or self._child_text(element, "link")
                if not locator:
                    for child in element:
                        if child.tag.rsplit("}", 1)[-1].lower() == "link":
                            locator = child.attrib.get("href")
                            if locator:
                                break
                if not locator or not locator.startswith(("http://", "https://")):
                    continue
                summary = self._child_text(element, "summary") or self._child_text(
                    element, "description"
                )
                haystack = f"{title} {summary} {locator}".casefold()
                if terms and not any(term in haystack for term in terms):
                    continue
                artifacts.append(
                    DiscoveryArtifact(locator, title, self.name, summary, {"seed": seed})
                )
                if len(artifacts) >= limit:
                    return DiscoveryResponse(artifacts)
        return DiscoveryResponse(artifacts[:limit])

    @staticmethod
    def _child_text(element: ET.Element, name: str) -> str:
        for child in element:
            if child.tag.rsplit("}", 1)[-1].lower() == name:
                return (child.text or "").strip()
        return ""


class ChatGPTDiscoveryProvider:
    name = "chatgpt-bridge"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8787",
        *,
        agent: str = "wisdom-oldman",
        token: str | None = None,
        mode: str = "search",
        project: str = "orbit",
        run_id: str | None = None,
        run_id_getter: Callable[[], str | None] | None = None,
        timeout: float = 60.0,
        poll_interval: float = 2.0,
        opener: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent = agent
        self.token = token
        self.mode = mode
        self.project = project
        self.run_id = run_id
        self.run_id_getter = run_id_getter
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._opener = opener

    def _open(self, request: Request, timeout: float = 15.0) -> dict[str, Any]:
        if self._opener is not None:
            res = self._opener.open(request, timeout)
            raw = res.read() if hasattr(res, "read") else res
            return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def discover(self, query: str, *, limit: int = 5) -> DiscoveryResponse:
        token = self.token
        if not token:
            try:
                from .settings import Settings

                token = Settings.from_env().load_tokens().get(self.agent)
            except Exception:  # noqa: BLE001
                token = None
        if not token:
            LOGGER.info("ChatGPT discovery skipped: no token configured for %s", self.agent)
            return DiscoveryResponse([])

        run_id = self.run_id
        if not run_id and self.run_id_getter:
            try:
                run_id = self.run_id_getter()
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("ChatGPT discovery skipped: run_id lookup failed: %s", exc)
                return DiscoveryResponse([])
        if not run_id:
            LOGGER.info("ChatGPT discovery skipped: no active run_id available")
            return DiscoveryResponse([])

        idempotency_key = f"orbit-{uuid.uuid4().hex[:16]}"
        clean_thread = re.sub(r"[^a-zA-Z0-9_-]", "_", query)[:30] or "orbit-main"
        thread = f"orbit-{clean_thread}"
        payload = {
            "run_id": run_id,
            "prompt": query,
            "idempotency_key": idempotency_key,
            "mode": self.mode,
            "project": self.project,
            "thread": thread,
            "sites": [],
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "X-UuMA-Identity": self.agent,
            "Content-Type": "application/json",
        }

        submit_url = f"{self.base_url}/agent/requests"
        req = Request(
            submit_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            created = self._open(req, timeout=15.0)
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            LOGGER.warning("ChatGPT discovery unavailable at %s: %s", submit_url, exc)
            return DiscoveryResponse([])

        req_id = created.get("id")
        if not req_id:
            return DiscoveryResponse([])

        status_url = f"{self.base_url}/agent/requests/{req_id}"
        deadline = time.monotonic() + self.timeout
        result_payload = None

        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            poll_req = Request(status_url, headers=headers, method="GET")
            try:
                state = self._open(poll_req, timeout=10.0)
            except (URLError, HTTPError, TimeoutError, OSError) as exc:
                LOGGER.warning("ChatGPT discovery poll failed for %s: %s", req_id, exc)
                break

            status = state.get("status")
            if status == "COMPLETED":
                result_payload = state.get("result")
                break
            if status in {"FAILED", "CANCELLED", "PAUSED", "NEEDS_REVIEW"}:
                LOGGER.warning(
                    "ChatGPT discovery request %s ended with status %s", req_id, status
                )
                break

        if not result_payload or not isinstance(result_payload, dict):
            return DiscoveryResponse([], request_id=req_id)

        raw_citations = result_payload.get("citations") or []
        artifacts: list[DiscoveryArtifact] = []
        for item in raw_citations:
            if isinstance(item, dict):
                loc = str(item.get("url") or "").strip()
                title = str(item.get("title") or loc).strip()
            elif isinstance(item, str):
                loc = item.strip()
                title = loc
            else:
                continue

            if not loc.startswith(("http://", "https://")):
                continue

            artifacts.append(
                DiscoveryArtifact(
                    locator=loc,
                    title=title or loc,
                    provider=self.name,
                    snippet=str(result_payload.get("answer") or "")[:300],
                    metadata={
                        "chatgpt_request_id": req_id,
                        "mode": self.mode,
                        "thread": thread,
                    },
                )
            )
            if len(artifacts) >= limit:
                break

        return DiscoveryResponse(artifacts, request_id=req_id)


def configured_providers(
    fetcher: SafeWebFetcher | None = None,
    *,
    chatgpt_provider: DiscoveryProvider | None = None,
) -> list[DiscoveryProvider]:
    providers: list[DiscoveryProvider] = []
    if chatgpt_provider is not None:
        providers.append(chatgpt_provider)
    seeds = [
        value.strip()
        for value in os.environ.get("UUMA_ORBIT_FEED_URLS", "").split(",")
        if value.strip()
    ]
    if seeds:
        providers.append(FeedSitemapProvider(seeds, fetcher))
    providers.extend([
        OpenAlexProvider(fetcher), CrossrefProvider(fetcher),
        DdgsSearchProvider(academic=True), DdgsSearchProvider(),
    ])
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if brave_key:
        providers.append(BraveSearchProvider(brave_key, fetcher))
    return providers


def urls_in_question(question: str) -> list[DiscoveryArtifact]:
    return [
        DiscoveryArtifact(url, url, "user-url")
        for url in dict.fromkeys(re.findall(r"https?://[^\s<>\]\[)]+", question))
    ]
