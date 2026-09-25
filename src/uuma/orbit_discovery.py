from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .knowledge_service import KnowledgeService
from .safe_web import SafeWebFetcher


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


def configured_providers(fetcher: SafeWebFetcher | None = None) -> list[DiscoveryProvider]:
    providers: list[DiscoveryProvider] = []
    seeds = [
        value.strip()
        for value in os.environ.get("UUMA_ORBIT_FEED_URLS", "").split(",")
        if value.strip()
    ]
    if seeds:
        providers.append(FeedSitemapProvider(seeds, fetcher))
    providers.extend([OpenAlexProvider(fetcher), CrossrefProvider(fetcher)])
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if brave_key:
        providers.append(BraveSearchProvider(brave_key, fetcher))
    return providers


def urls_in_question(question: str) -> list[DiscoveryArtifact]:
    return [
        DiscoveryArtifact(url, url, "user-url")
        for url in dict.fromkeys(re.findall(r"https?://[^\s<>\]\[)]+", question))
    ]
