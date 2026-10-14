from __future__ import annotations

from threading import Barrier

from rstv4 import sources
from rstv4.models import CollectionSearchInput, SourceCandidate


def test_provider_searches_run_concurrently_and_preserve_order(monkeypatch) -> None:
    barrier = Barrier(2, timeout=2)

    def first(query: str, limit: int) -> list[SourceCandidate]:
        barrier.wait()
        return [SourceCandidate(source_provider="first", title="First result")]

    def second(query: str, limit: int) -> list[SourceCandidate]:
        barrier.wait()
        raise ValueError("provider unavailable")

    monkeypatch.setitem(sources.PROVIDERS, "first", first)
    monkeypatch.setitem(sources.PROVIDERS, "second", second)
    results = sources.search_all("test query", providers=["first", "second"])

    assert [result.provider for result in results] == ["first", "second"]
    assert results[0].candidates[0].title == "First result"
    assert results[1].error == "provider unavailable"


def test_collection_search_accepts_all_registered_providers() -> None:
    payload = CollectionSearchInput(
        query="all sky imager solar irradiance nowcasting",
        providers=list(sources.PROVIDERS),
        idempotency_key="all-provider-probe",
    )
    assert len(payload.providers) == 7


def test_bibliographic_lookup_rejects_wrong_title_or_year(monkeypatch) -> None:
    def fake_get_json(url: str) -> dict:
        assert "query.bibliographic=" in url
        return {"message": {"items": [
            {
                "DOI": "10.1234/unrelated", "title": ["A different desalination study"],
                "author": [{"family": "Greenlee"}],
                "published": {"date-parts": [[2009]]},
            },
            {
                "DOI": "10.1234/right", "title": [(
                    "Reverse osmosis desalination: water sources, technology, "
                    "and today's challenges"
                )],
                "author": [{"family": "Greenlee"}],
                "published": {"date-parts": [[2009]]},
            },
            {
                "DOI": "10.1234/wrong-year", "title": [(
                    "Reverse osmosis desalination: water sources, technology, "
                    "and today's challenges"
                )],
                "author": [{"family": "Greenlee"}],
                "published": {"date-parts": [[2012]]},
            },
        ]}}

    monkeypatch.setattr(sources, "_get_json", fake_get_json)
    result = sources.lookup_bibliographic_reference(
        "Greenlee LF, Lawler DF. Reverse osmosis desalination: water sources, "
        "technology, and today's challenges. Water Res. 2009;43:2317-2348."
    )
    assert [candidate.doi for candidate in result.candidates] == ["10.1234/right"]


def test_bibliographic_lookup_keeps_ambiguous_identity_unresolved(monkeypatch) -> None:
    title = "Reverse osmosis desalination and its practical challenges"
    monkeypatch.setattr(sources, "_get_json", lambda url: {"message": {"items": [
        {"DOI": doi, "title": [title], "author": [{"family": "Greenlee"}],
         "published": {"date-parts": [[2009]]}}
        for doi in ("10.1234/version-one", "10.1234/version-two")
    ]}})
    result = sources.lookup_bibliographic_reference(
        f"Greenlee LF. {title}. Water Research. 2009;43:2317-2348."
    )
    assert result.candidates == []


def test_datacite_search_keeps_publications_and_maps_metadata(monkeypatch) -> None:
    def fake_get_json(url: str) -> dict:
        assert "types.resourceTypeGeneral" in url
        return {"data": [
            {"id": "10.1234/data", "attributes": {
                "types": {"resourceTypeGeneral": "Dataset"},
                "titles": [{"title": "Solar irradiation data"}],
            }},
            {"id": "10.1234/preprint", "attributes": {
                "types": {"resourceTypeGeneral": "Preprint"},
                "titles": [{"title": "Solar irradiance forecasting with sky images"}],
                "creators": [{"name": "Lee, Kim"}],
                "publicationYear": 2024,
                "descriptions": [{"descriptionType": "Abstract", "description": "A method."}],
                "url": "https://example.org/preprint",
            }},
        ]}

    monkeypatch.setattr(sources, "_get_json", fake_get_json)
    results = sources.datacite("solar irradiance forecasting", 10)
    assert [(item.doi, item.title) for item in results] == [
        ("10.1234/preprint", "Solar irradiance forecasting with sky images")
    ]
    assert results[0].abstract == "A method."


def test_semantic_scholar_sends_configured_key_in_header(monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")

    def fake_get_json(url: str, *, headers: dict[str, str]) -> dict:
        assert "test-key" not in url
        assert headers == {"x-api-key": "test-key"}
        return {"data": []}

    monkeypatch.setattr(sources, "_get_json", fake_get_json)
    assert sources.semantic_scholar("solar forecasting", 2) == []


def test_openaire_search_maps_publication_without_inventing_pdf(monkeypatch) -> None:
    monkeypatch.setattr(sources, "_get_json", lambda url: {"results": [{
        "id": "oa-1", "mainTitle": "Sky camera <scp>irradiance</scp> forecasting",
        "publicationDate": "2024-03-01",
        "pids": [{"scheme": "doi", "value": "10.1234/sky"}],
        "authors": [{"fullName": "Lee, Kim"}],
        "descriptions": ["A forecasting study."],
        "instances": [{"urls": ["https://example.org/landing"]}],
    }]})
    result = sources.openaire("sky camera", 3)[0]
    assert result.title == "Sky camera irradiance forecasting"
    assert result.doi == "10.1234/sky"
    assert result.published_year == 2024
    assert result.authors == ["Lee, Kim"]
    assert result.abstract == "A forecasting study."
    assert result.pdf_url is None


def test_doi_resolution_uses_exact_openaire_fallback(monkeypatch) -> None:
    def fake_get_json(url: str) -> dict:
        if "api.crossref.org" in url:
            return {"message": {}}
        if "api.datacite.org" in url:
            return {"data": {}}
        if "api.openalex.org" in url:
            return {}
        assert "api.openaire.eu" in url
        return {"results": [
            {"id": "wrong", "mainTitle": "A different paper", "publicationDate": "2024",
             "pids": [{"scheme": "doi", "value": "10.1234/wrong"}]},
            {"id": "right", "mainTitle": "The requested paper", "publicationDate": "2023",
             "pids": [{"scheme": "doi", "value": "10.1234/right"}]},
        ]}

    monkeypatch.setattr(sources, "_get_json", fake_get_json)
    result = sources.resolve_doi("10.1234/right")
    assert result.provider == "openaire"
    assert [item.doi for item in result.candidates] == ["10.1234/right"]


def test_reference_lookup_falls_back_to_openaire_when_crossref_misses(monkeypatch) -> None:
    title = "Reverse osmosis desalination: Water sources, technology, and today's challenges"
    reference = (
        "Greenlee LF, Lawler DF. Reverse osmosis desalination: water sources, "
        "technology, and today's challenges. Water Res. 2009;43:2317-2348."
    )
    monkeypatch.setattr(sources, "_crossref_reference_candidates", lambda text: [])
    monkeypatch.setattr(sources, "openaire", lambda query, limit: [
        SourceCandidate(
            source_provider="openaire", doi="10.1016/j.watres.2009.03.010",
            title=title, authors=["Greenlee, Lauren F."], published_year=2009,
        )
    ])
    monkeypatch.setattr(sources, "openalex", lambda query, limit: [])
    result = sources.lookup_bibliographic_reference(reference)
    assert [item.doi for item in result.candidates] == ["10.1016/j.watres.2009.03.010"]


def test_reference_lookup_rejects_conflicting_provider_dois(monkeypatch) -> None:
    title = "Reverse osmosis desalination and its practical challenges"
    reference = f"Greenlee LF. {title}. Water Research. 2009;43:2317-2348."
    monkeypatch.setattr(sources, "_crossref_reference_candidates", lambda text: [])
    monkeypatch.setattr(sources, "openaire", lambda query, limit: [
        SourceCandidate(
            source_provider="openaire", doi="10.1234/one", title=title,
            authors=["Greenlee, Lauren F."], published_year=2009,
        )
    ])
    monkeypatch.setattr(sources, "openalex", lambda query, limit: [
        SourceCandidate(
            source_provider="openalex", doi="10.1234/two", title=title,
            authors=["Lauren F. Greenlee"], published_year=2009,
        )
    ])
    assert sources.lookup_bibliographic_reference(reference).candidates == []
