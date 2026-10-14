from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .models import SourceCandidate


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    candidates: list[SourceCandidate]
    error: str | None = None
    elapsed_s: float | None = None


def _get_json(url: str, *, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(
        url, headers={"User-Agent": "RSTV4/0.1 (research assistant)", **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return None


def _clean_title(value: str) -> str:
    return " ".join(re.sub(r"</?[A-Za-z][^>]*>", "", html.unescape(value)).split())


def _crossref_candidate(item: dict[str, Any]) -> SourceCandidate:
    return SourceCandidate(
        source_provider="crossref",
        external_id=item.get("DOI"),
        doi=item.get("DOI"),
        title=_text(item.get("title")) or "Untitled",
        authors=[
            " ".join(filter(None, [author.get("given"), author.get("family")]))
            for author in item.get("author", [])
        ],
        published_year=item.get("published", {}).get("date-parts", [[None]])[0][0],
        abstract=_text(item.get("abstract")),
        landing_url=item.get("URL"),
        raw=item,
    )


def _datacite_candidate(item: dict[str, Any]) -> SourceCandidate | None:
    attributes = item.get("attributes") or {}
    kind = (attributes.get("types") or {}).get("resourceTypeGeneral")
    if kind not in {"Text", "Preprint", "JournalArticle"}:
        return None
    titles = attributes.get("titles") or []
    title = titles[0].get("title") if titles else None
    if not title:
        return None
    descriptions = attributes.get("descriptions") or []
    abstract = next(
        (
            row.get("description") for row in descriptions
            if row.get("descriptionType") == "Abstract" and row.get("description")
        ),
        None,
    )
    return SourceCandidate(
        source_provider="datacite",
        external_id=item.get("id"),
        doi=attributes.get("doi") or item.get("id"),
        title=_clean_title(title),
        authors=[
            creator["name"] for creator in attributes.get("creators") or []
            if isinstance(creator, dict) and creator.get("name")
        ],
        published_year=attributes.get("publicationYear"),
        abstract=abstract,
        landing_url=attributes.get("url") or (
            f"https://doi.org/{item['id']}" if item.get("id") else None
        ),
        raw=item,
    )


def _openaire_candidate(item: dict[str, Any]) -> SourceCandidate | None:
    title = item.get("mainTitle")
    if not title:
        return None
    doi = next(
        (
            pid.get("value") for pid in item.get("pids") or []
            if isinstance(pid, dict)
            and str(pid.get("scheme") or "").casefold() == "doi"
            and pid.get("value")
        ),
        None,
    )
    publication_date = str(item.get("publicationDate") or "")
    year = int(publication_date[:4]) if publication_date[:4].isdigit() else None
    descriptions = item.get("descriptions") or []
    urls = [
        url
        for instance in item.get("instances") or []
        if isinstance(instance, dict)
        for url in instance.get("urls") or []
        if isinstance(url, str)
    ]
    return SourceCandidate(
        source_provider="openaire",
        external_id=item.get("id"),
        doi=doi,
        title=_clean_title(title),
        authors=[
            author["fullName"] for author in item.get("authors") or []
            if isinstance(author, dict) and author.get("fullName")
        ],
        published_year=year,
        abstract=next((value for value in descriptions if isinstance(value, str)), None),
        landing_url=(f"https://doi.org/{doi}" if doi else None) or next(iter(urls), None),
        raw=item,
    )


def resolve_doi(doi: str) -> ProviderResult:
    """Resolve one DOI through ordered metadata providers without hiding failures."""
    normalized = doi.casefold().removeprefix("https://doi.org/").removeprefix("doi:")
    attempts: list[str] = []
    try:
        item = _get_json(
            "https://api.crossref.org/works/" + urllib.parse.quote(normalized, safe="")
        ).get("message", {})
        if item.get("title"):
            return ProviderResult(provider="crossref", candidates=[_crossref_candidate(item)])
    except Exception as exc:  # noqa: BLE001 - one source cannot block DOI fallbacks
        attempts.append(f"crossref: {exc}")
    try:
        item = _get_json(
            "https://api.datacite.org/dois/" + urllib.parse.quote(normalized, safe="")
        ).get("data", {})
        candidate = _datacite_candidate(item)
        if candidate and candidate.doi and candidate.doi.casefold() == normalized:
            return ProviderResult(provider="datacite", candidates=[candidate])
    except Exception as exc:  # noqa: BLE001 - one source cannot block DOI fallbacks
        attempts.append(f"datacite: {exc}")
    try:
        item = _get_json(
            "https://api.openalex.org/works/https://doi.org/"
            + urllib.parse.quote(normalized, safe="")
        )
        if item.get("title"):
            candidate = SourceCandidate(
                source_provider="openalex",
                external_id=item.get("id"),
                doi=normalized,
                title=item["title"],
                authors=[
                    author.get("author", {}).get("display_name", "")
                    for author in item.get("authorships", [])
                ],
                published_year=item.get("publication_year"),
                abstract=None,
                landing_url=item.get("doi") or item.get("id"),
                pdf_url=(item.get("best_oa_location") or {}).get("pdf_url"),
                raw=item,
            )
            return ProviderResult(provider="openalex", candidates=[candidate])
    except Exception as exc:  # noqa: BLE001 - one source cannot block DOI fallbacks
        attempts.append(f"openalex: {exc}")
    try:
        item = _get_json(
            "https://api.openaire.eu/graph/v3/research-products?"
            + urllib.parse.urlencode({"pid": normalized, "type": "publication", "pageSize": 3})
        )
        matches = [
            candidate for row in item.get("results") or []
            if (candidate := _openaire_candidate(row))
            and candidate.doi and candidate.doi.casefold() == normalized
        ]
        if len(matches) == 1:
            return ProviderResult(provider="openaire", candidates=matches)
    except Exception as exc:  # noqa: BLE001 - one source cannot block DOI fallbacks
        attempts.append(f"openaire: {exc}")
    return ProviderResult(provider="doi_resolution", candidates=[], error="; ".join(attempts))


def locate_open_access_pdf(doi: str) -> ProviderResult:
    normalized = doi.casefold().removeprefix("https://doi.org/").removeprefix("doi:")
    email = os.environ.get("UNPAYWALL_EMAIL") or os.environ.get("CROSSREF_EMAIL")
    if not email:
        return ProviderResult(
            provider="unpaywall", candidates=[], error="UNPAYWALL_EMAIL is not configured"
        )
    try:
        item = _get_json(
            "https://api.unpaywall.org/v2/"
            + urllib.parse.quote(normalized, safe="")
            + "?"
            + urllib.parse.urlencode({"email": email})
        )
        location = item.get("best_oa_location") or {}
        url = location.get("url_for_pdf")
        if not url:
            return ProviderResult(provider="unpaywall", candidates=[], error=None)
        candidate = SourceCandidate(
            source_provider="unpaywall",
            external_id=normalized,
            doi=normalized,
            title=item.get("title") or f"DOI {normalized}",
            authors=[],
            published_year=item.get("year"),
            landing_url=location.get("url") or item.get("doi_url"),
            pdf_url=url,
            raw=item,
        )
        return ProviderResult(provider="unpaywall", candidates=[candidate])
    except Exception as exc:  # noqa: BLE001 - report optional provider failure
        return ProviderResult(provider="unpaywall", candidates=[], error=str(exc))


def crossref(query: str, limit: int) -> list[SourceCandidate]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query": query, "rows": limit}
    )
    items = _get_json(url).get("message", {}).get("items", [])
    return [_crossref_candidate(item) for item in items if _text(item.get("title"))]


def datacite(query: str, limit: int) -> list[SourceCandidate]:
    publication_types = "types.resourceTypeGeneral:(Text OR Preprint OR JournalArticle)"
    url = "https://api.datacite.org/dois?" + urllib.parse.urlencode(
        {"query": f"{query} AND {publication_types}", "page[size]": limit,
         "sort": "relevance"}
    )
    items = _get_json(url).get("data") or []
    return [candidate for item in items if (candidate := _datacite_candidate(item))]


def openaire(query: str, limit: int) -> list[SourceCandidate]:
    url = "https://api.openaire.eu/graph/v3/research-products?" + urllib.parse.urlencode(
        {"search": query, "type": "publication", "pageSize": limit}
    )
    items = _get_json(url).get("results") or []
    return [candidate for item in items if (candidate := _openaire_candidate(item))]


def _crossref_reference_candidates(raw_text: str) -> list[SourceCandidate]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {
            "query.bibliographic": raw_text[:500],
            "rows": 3,
            "select": "DOI,title,author,published,URL",
        }
    )
    items = _get_json(url).get("message", {}).get("items", [])
    return [_crossref_candidate(item) for item in items if _text(item.get("title"))]


def _reference_words(value: str) -> list[str]:
    return re.findall(r"\w+", value.casefold(), flags=re.UNICODE)


def _reference_candidate_matches(raw_text: str, candidate: SourceCandidate) -> bool:
    if not candidate.doi or not candidate.published_year:
        return False
    title_words = _reference_words(candidate.title)
    citation = " ".join(_reference_words(raw_text))
    if len(title_words) < 5 or " ".join(title_words) not in citation:
        return False
    if str(candidate.published_year) not in raw_text:
        return False
    if not candidate.authors:
        return False
    first_author = candidate.authors[0]
    surname = first_author.split(",", 1)[0] if "," in first_author else first_author
    surname_words = _reference_words(surname)
    if "," not in first_author:
        surname_words = surname_words[-1:]
    author_prefix = citation.split(" ".join(title_words), 1)[0]
    return bool(surname_words and " ".join(surname_words) in author_prefix)


def _reference_title_query(raw_text: str, candidates: list[SourceCandidate]) -> str | None:
    for candidate in candidates:
        if len(_reference_words(candidate.title)) >= 5:
            title = " ".join(_reference_words(candidate.title))
            if title in " ".join(_reference_words(raw_text)):
                return candidate.title
    fragments = re.split(r"(?<=[.!?])\s+", raw_text)
    fragments = [
        fragment.strip(" .;,:") for fragment in fragments
        if 5 <= len(_reference_words(fragment)) <= 35
        and not re.search(r"https?://|\b10\.\d{4,9}/", fragment, re.IGNORECASE)
    ]
    return max(fragments, key=lambda value: len(_reference_words(value)), default=None)


def lookup_bibliographic_reference(raw_text: str) -> ProviderResult:
    """Resolve a DOI-free citation with strict identity checks and bounded fallbacks."""
    provider = "bibliographic_reference"
    if len(raw_text) < 60 or not re.search(r"\b(?:19|20)\d{2}\b", raw_text):
        return ProviderResult(provider=provider, candidates=[])

    errors: list[str] = []
    try:
        crossref_candidates = _crossref_reference_candidates(raw_text)
    except (OSError, ValueError) as exc:
        crossref_candidates = []
        errors.append(f"crossref: {exc}")

    matches = {
        candidate.doi.casefold(): candidate
        for candidate in crossref_candidates
        if candidate.doi and _reference_candidate_matches(raw_text, candidate)
    }
    if len(matches) == 1:
        return ProviderResult(provider=provider, candidates=list(matches.values()))
    if len(matches) > 1:
        return ProviderResult(provider=provider, candidates=[])

    title_query = _reference_title_query(raw_text, crossref_candidates)
    if not title_query:
        return ProviderResult(provider=provider, candidates=[], error="; ".join(errors) or None)

    # A full citation is too restrictive for title search APIs. The original
    # citation is still used for the final title, author and year checks.
    lookup_sources = (
        ("openaire", lambda: openaire(title_query, 3)),
        ("openalex", lambda: openalex(" ".join(_reference_words(title_query)[:5]), 3)),
    )
    def search_one(source: tuple[str, Callable[[], list[SourceCandidate]]]) -> tuple[
        str, list[SourceCandidate], str | None
    ]:
        source_name, lookup = source
        try:
            return source_name, lookup(), None
        except (OSError, ValueError) as exc:
            return source_name, [], str(exc)

    with ThreadPoolExecutor(max_workers=len(lookup_sources)) as pool:
        results = list(pool.map(search_one, lookup_sources))
    for source_name, candidates, error in results:
        if error:
            errors.append(f"{source_name}: {error}")
            continue
        for candidate in candidates:
            if candidate.doi and _reference_candidate_matches(raw_text, candidate):
                matches.setdefault(candidate.doi.casefold(), candidate)
        if len(matches) > 1:
            return ProviderResult(provider=provider, candidates=[])

    if len(matches) == 1:
        return ProviderResult(provider=provider, candidates=list(matches.values()))
    return ProviderResult(provider=provider, candidates=[], error="; ".join(errors) or None)


def openalex(query: str, limit: int) -> list[SourceCandidate]:
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": query, "per-page": limit}
    )
    items = _get_json(url).get("results", [])
    return [
        SourceCandidate(
            source_provider="openalex",
            external_id=item.get("id"),
            doi=(item.get("doi") or "").replace("https://doi.org/", "") or None,
            title=item.get("title") or "Untitled",
            authors=[
                author.get("author", {}).get("display_name", "")
                for author in item.get("authorships", [])
            ],
            published_year=item.get("publication_year"),
            landing_url=item.get("doi") or item.get("id"),
            pdf_url=item.get("open_access", {}).get("oa_url"),
            raw=item,
        )
        for item in items
        if item.get("title")
    ]


def semantic_scholar(query: str, limit: int) -> list[SourceCandidate]:
    fields = "title,authors,year,abstract,externalIds,url,openAccessPdf"
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
        {"query": query, "limit": limit, "fields": fields}
    )
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    response = _get_json(url, headers={"x-api-key": api_key}) if api_key else _get_json(url)
    items = response.get("data", [])
    return [
        SourceCandidate(
            source_provider="semantic_scholar",
            external_id=item.get("paperId"),
            doi=item.get("externalIds", {}).get("DOI"),
            title=item.get("title") or "Untitled",
            authors=[author.get("name", "") for author in item.get("authors", [])],
            published_year=item.get("year"),
            abstract=item.get("abstract"),
            landing_url=item.get("url"),
            pdf_url=(item.get("openAccessPdf") or {}).get("url"),
            raw=item,
        )
        for item in items
        if item.get("title")
    ]


def europe_pmc(query: str, limit: int) -> list[SourceCandidate]:
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(
        {"query": query, "pageSize": limit, "format": "json"}
    )
    items = _get_json(url).get("resultList", {}).get("result", [])
    return [
        SourceCandidate(
            source_provider="europe_pmc",
            external_id=item.get("id"),
            doi=item.get("doi"),
            title=item.get("title") or "Untitled",
            authors=(item.get("authorString") or "").split(", "),
            published_year=int(item["pubYear"]) if str(item.get("pubYear", "")).isdigit() else None,
            abstract=item.get("abstractText"),
            landing_url=item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url"),
            raw=item,
        )
        for item in items
        if item.get("title")
    ]


def arxiv(query: str, limit: int) -> list[SourceCandidate]:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": f"all:{query}", "start": 0, "max_results": limit, "sortBy": "relevance"}
    )
    request = urllib.request.Request(url, headers={"User-Agent": "RSTV4/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    ns = {"a": "http://www.w3.org/2005/Atom"}
    result: list[SourceCandidate] = []
    for entry in root.findall("a:entry", ns):
        entry_id = entry.findtext("a:id", default="", namespaces=ns)
        title = " ".join((entry.findtext("a:title", default="", namespaces=ns)).split())
        if not title:
            continue
        result.append(
            SourceCandidate(
                source_provider="arxiv",
                external_id=entry_id.rsplit("/", 1)[-1],
                title=title,
                authors=[
                    node.findtext("a:name", default="", namespaces=ns)
                    for node in entry.findall("a:author", ns)
                ],
                published_year=int(
                    (entry.findtext("a:published", default="", namespaces=ns) or "0000")[:4]
                )
                or None,
                abstract=" ".join((entry.findtext("a:summary", default="", namespaces=ns)).split()),
                landing_url=entry_id,
                pdf_url=entry_id.replace("/abs/", "/pdf/"),
                raw={"id": entry_id},
            )
        )
    return result


PROVIDERS: dict[str, Callable[[str, int], list[SourceCandidate]]] = {
    "crossref": crossref,
    "openalex": openalex,
    "semantic_scholar": semantic_scholar,
    "arxiv": arxiv,
    "europe_pmc": europe_pmc,
    "datacite": datacite,
    "openaire": openaire,
}


def search_all(
    query: str, *, providers: list[str] | None = None, limit_per_provider: int = 10
) -> list[ProviderResult]:
    selected = providers or list(PROVIDERS)
    if not selected:
        return []

    def search_one(provider: str) -> ProviderResult:
        started = time.perf_counter()
        handler = PROVIDERS.get(provider)
        if handler is None:
            return ProviderResult(
                provider=provider, candidates=[], error="Unknown provider",
                elapsed_s=round(time.perf_counter() - started, 3),
            )
        try:
            return ProviderResult(
                provider=provider, candidates=handler(query, limit_per_provider),
                elapsed_s=round(time.perf_counter() - started, 3),
            )
        # Provider adapters are optional third-party boundaries. One arbitrary
        # provider failure must not invalidate results from the others.
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(
                provider=provider, candidates=[], error=str(exc),
                elapsed_s=round(time.perf_counter() - started, 3),
            )

    with ThreadPoolExecutor(max_workers=min(len(selected), len(PROVIDERS))) as pool:
        return list(pool.map(search_one, selected))
