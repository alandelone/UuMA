"""Tests for Librarian Source Registry (63 registered data sources)."""

import pytest

from uuma.librarian_source_registry import (
    REGISTERED_SOURCES,
    TOTAL_SOURCES_COUNT,
    count_sources,
    get_source,
    is_registered_source,
    list_sources,
)


def test_registered_sources_count() -> None:
    assert count_sources() == 63
    assert len(REGISTERED_SOURCES) == TOTAL_SOURCES_COUNT == 63


def test_registered_sources_device_split() -> None:
    server_sources = list_sources(device="server")
    workstation_sources = list_sources(device="workstation")

    assert len(server_sources) == 44
    assert len(workstation_sources) == 19
    assert len(server_sources) + len(workstation_sources) == 63


def test_registered_sources_field_integrity() -> None:
    valid_categories = {"Knowledge", "Experience", "Decision", "Work & Artifacts", "History"}
    valid_privacy = {"public", "internal", "restricted", "honc_private"}
    valid_archetypes = {"deterministic", "conversational", "domain", "private"}

    for source_id, defn in REGISTERED_SOURCES.items():
        assert defn.source_id == source_id
        assert defn.device in {"server", "workstation"}
        assert len(defn.owner_agent) > 0
        assert defn.category_default in valid_categories
        assert defn.privacy_tier in valid_privacy
        assert defn.adapter_archetype in valid_archetypes
        assert len(defn.description) > 0


def test_get_source_and_membership() -> None:
    assert is_registered_source("antigravity-core")
    assert is_registered_source("yonc-graph")
    assert not is_registered_source("non-existent-source")

    yonc = get_source("yonc-graph")
    assert yonc.source_id == "yonc-graph"
    assert yonc.device == "server"
    assert yonc.owner_agent == "yonc"
    assert yonc.adapter_archetype == "deterministic"

    with pytest.raises(KeyError, match="Unknown data source"):
        get_source("invalid_source_123")


def test_list_sources_filtering() -> None:
    honc_private = list_sources(privacy_tier="honc_private")
    assert len(honc_private) == 2
    assert {s.source_id for s in honc_private} == {"honc-database", "honc-memories-files"}

    librarian_sources = list_sources(owner_agent="librarian")
    assert len(librarian_sources) > 0
    for s in librarian_sources:
        assert s.owner_agent == "librarian"
