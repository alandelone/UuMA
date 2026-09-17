from __future__ import annotations

from pathlib import Path

BOOTSTRAP = Path(__file__).parents[1] / "deploy" / "kag" / "bootstrap.ps1"


def test_kag_bootstrap_bounds_wsl_memory_and_preserves_idle_stop() -> None:
    script = BOOTSTRAP.read_text(encoding="utf-8")

    assert "-Xmx4096m" in script
    assert "NEO4J_server_memory_heap_max__size=2G" in script
    assert "NEO4J_server_memory_pagecache_size=512M" in script
    assert "restart: unless-stopped" in script


def test_kag_bootstrap_seeds_a_host_durable_neo4j_config_directory() -> None:
    script = BOOTSTRAP.read_text(encoding="utf-8")

    assert 'Join-Path $resolvedRuntime "neo4j-conf"' in script
    assert '"${seedContainer}:/var/lib/neo4j/conf/."' in script
    assert "${neo4jConfigMount}:/var/lib/neo4j/conf" in script
