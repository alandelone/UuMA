"""Registry of the 63 known Librarian data sources across server and workstation.

Provides immutable source definitions, ownership mapping, privacy tiers,
default memory categories, and adapter archetypes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DeviceType = Literal["server", "workstation"]
MemoryCategory = Literal["Knowledge", "Experience", "Decision", "Work & Artifacts", "History"]
PrivacyTier = Literal["public", "internal", "restricted", "honc_private"]
AdapterArchetype = Literal["deterministic", "conversational", "domain", "private"]


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    device: DeviceType
    owner_agent: str
    category_default: MemoryCategory
    privacy_tier: PrivacyTier
    adapter_archetype: AdapterArchetype
    description: str


REGISTERED_SOURCES: dict[str, SourceDefinition] = {
    # Server sources (44 sources)
    "brainstormer-audit-files": SourceDefinition(
        source_id="brainstormer-audit-files",
        device="server",
        owner_agent="brainstormer",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="deterministic",
        description="Brainstormer audit log files and decision receipts",
    ),
    "brainstormer-cron-files": SourceDefinition(
        source_id="brainstormer-cron-files",
        device="server",
        owner_agent="brainstormer",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Brainstormer scheduled task definitions",
    ),
    "brainstormer-logs-files": SourceDefinition(
        source_id="brainstormer-logs-files",
        device="server",
        owner_agent="brainstormer",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Brainstormer execution and runtime logs",
    ),
    "brainstormer-memories-files": SourceDefinition(
        source_id="brainstormer-memories-files",
        device="server",
        owner_agent="brainstormer",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Brainstormer memory markdown files",
    ),
    "brainstormer-native": SourceDefinition(
        source_id="brainstormer-native",
        device="server",
        owner_agent="brainstormer",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Brainstormer native session state database",
    ),
    "brainstormer-navigation": SourceDefinition(
        source_id="brainstormer-navigation",
        device="server",
        owner_agent="brainstormer",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Brainstormer topic navigation state",
    ),
    "brainstormer-receipt-files": SourceDefinition(
        source_id="brainstormer-receipt-files",
        device="server",
        owner_agent="brainstormer",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="deterministic",
        description="Brainstormer immutable proposal and review receipts",
    ),
    "brainstormer-structured-files": SourceDefinition(
        source_id="brainstormer-structured-files",
        device="server",
        owner_agent="brainstormer",
        category_default="Decision",
        privacy_tier="internal",
        adapter_archetype="deterministic",
        description="Brainstormer structured state.json topics and checkpoints",
    ),
    "forge-commerce-files": SourceDefinition(
        source_id="forge-commerce-files",
        device="server",
        owner_agent="forge",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Forge hardware component procurement and commerce receipts",
    ),
    "forge-cron-files": SourceDefinition(
        source_id="forge-cron-files",
        device="server",
        owner_agent="forge",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Forge scheduled task definitions",
    ),
    "forge-design": SourceDefinition(
        source_id="forge-design",
        device="server",
        owner_agent="forge",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Forge electrical and mechanical design specifications",
    ),
    "forge-design-files": SourceDefinition(
        source_id="forge-design-files",
        device="server",
        owner_agent="forge",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Forge schematic and PCB CAD design assets",
    ),
    "forge-hardware-workspace": SourceDefinition(
        source_id="forge-hardware-workspace",
        device="server",
        owner_agent="forge",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Hardware Lab shared live workspace files and BOMs",
    ),
    "forge-lab": SourceDefinition(
        source_id="forge-lab",
        device="server",
        owner_agent="forge",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Forge hardware lab experiment and bench notes",
    ),
    "forge-logs-files": SourceDefinition(
        source_id="forge-logs-files",
        device="server",
        owner_agent="forge",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Forge runtime execution logs",
    ),
    "forge-memories-files": SourceDefinition(
        source_id="forge-memories-files",
        device="server",
        owner_agent="forge",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Forge persistent memory files",
    ),
    "forge-native": SourceDefinition(
        source_id="forge-native",
        device="server",
        owner_agent="forge",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Forge native session state database",
    ),
    "forge-relay-files": SourceDefinition(
        source_id="forge-relay-files",
        device="server",
        owner_agent="forge",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Forge Notion synchronization relay files",
    ),
    "honc-cron-files": SourceDefinition(
        source_id="honc-cron-files",
        device="server",
        owner_agent="honc",
        category_default="Work & Artifacts",
        privacy_tier="restricted",
        adapter_archetype="private",
        description="Honc scheduled personal habits and life reminders",
    ),
    "honc-database": SourceDefinition(
        source_id="honc-database",
        device="server",
        owner_agent="honc",
        category_default="Experience",
        privacy_tier="honc_private",
        adapter_archetype="private",
        description="Honc life tracking SQLite database (habits, diary, health)",
    ),
    "honc-logs-files": SourceDefinition(
        source_id="honc-logs-files",
        device="server",
        owner_agent="honc",
        category_default="Experience",
        privacy_tier="restricted",
        adapter_archetype="private",
        description="Honc personal agent execution logs",
    ),
    "honc-memories-files": SourceDefinition(
        source_id="honc-memories-files",
        device="server",
        owner_agent="honc",
        category_default="Knowledge",
        privacy_tier="honc_private",
        adapter_archetype="private",
        description="Honc personal reflections and long-term notes",
    ),
    "honc-native": SourceDefinition(
        source_id="honc-native",
        device="server",
        owner_agent="honc",
        category_default="History",
        privacy_tier="restricted",
        adapter_archetype="conversational",
        description="Honc native Hermes session database",
    ),
    "librarian-config": SourceDefinition(
        source_id="librarian-config",
        device="server",
        owner_agent="librarian",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Librarian daemon configuration and profile definitions",
    ),
    "librarian-cron-files": SourceDefinition(
        source_id="librarian-cron-files",
        device="server",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Librarian backup and capture schedule definitions",
    ),
    "librarian-logs-files": SourceDefinition(
        source_id="librarian-logs-files",
        device="server",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Librarian capture and recovery operational logs",
    ),
    "librarian-native": SourceDefinition(
        source_id="librarian-native",
        device="server",
        owner_agent="librarian",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Librarian native session state database",
    ),
    "librarian-semantic-index": SourceDefinition(
        source_id="librarian-semantic-index",
        device="server",
        owner_agent="librarian",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="deterministic",
        description="Librarian published catalog and semantic index files",
    ),
    "librarian-soul": SourceDefinition(
        source_id="librarian-soul",
        device="server",
        owner_agent="librarian",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Librarian SOUL policy and identity definition",
    ),
    "notion-cache": SourceDefinition(
        source_id="notion-cache",
        device="server",
        owner_agent="hermes",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Cached Notion workspace pages and block hierarchy",
    ),
    "printer-bttcb1-config": SourceDefinition(
        source_id="printer-bttcb1-config",
        device="server",
        owner_agent="forge",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="private",
        description="BTT CB1 Klipper 3D printer configuration files",
    ),
    "printer-vcore-config": SourceDefinition(
        source_id="printer-vcore-config",
        device="server",
        owner_agent="forge",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="private",
        description="RatRig V-Core 3D printer firmware and macro configurations",
    ),
    "uuma-control": SourceDefinition(
        source_id="uuma-control",
        device="server",
        owner_agent="hermes",
        category_default="Decision",
        privacy_tier="internal",
        adapter_archetype="deterministic",
        description="UuMA control plane database (mission gates and dispatch events)",
    ),
    "wisdom-content-files": SourceDefinition(
        source_id="wisdom-content-files",
        device="server",
        owner_agent="wisdom",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Wisdom authored research notes and knowledge markdown files",
    ),
    "wisdom-cron-files": SourceDefinition(
        source_id="wisdom-cron-files",
        device="server",
        owner_agent="wisdom",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Wisdom orbit research schedules",
    ),
    "wisdom-database": SourceDefinition(
        source_id="wisdom-database",
        device="server",
        owner_agent="wisdom",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Wisdom-Oldman knowledge base SQLite database (wisdom.db)",
    ),
    "wisdom-logs-files": SourceDefinition(
        source_id="wisdom-logs-files",
        device="server",
        owner_agent="wisdom",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Wisdom reasoning and research orbit logs",
    ),
    "wisdom-memories-files": SourceDefinition(
        source_id="wisdom-memories-files",
        device="server",
        owner_agent="wisdom",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Wisdom long-term memory files",
    ),
    "wisdom-native": SourceDefinition(
        source_id="wisdom-native",
        device="server",
        owner_agent="wisdom",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Wisdom native session state database",
    ),
    "yonc-cron-files": SourceDefinition(
        source_id="yonc-cron-files",
        device="server",
        owner_agent="yonc",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Yonc project manager recurring job definitions",
    ),
    "yonc-graph": SourceDefinition(
        source_id="yonc-graph",
        device="server",
        owner_agent="yonc",
        category_default="Decision",
        privacy_tier="internal",
        adapter_archetype="deterministic",
        description="Yonc task and goal dependency graph SQLite database (graph.db)",
    ),
    "yonc-logs-files": SourceDefinition(
        source_id="yonc-logs-files",
        device="server",
        owner_agent="yonc",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Yonc project manager execution logs",
    ),
    "yonc-memories-files": SourceDefinition(
        source_id="yonc-memories-files",
        device="server",
        owner_agent="yonc",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Yonc project manager memory files",
    ),
    "yonc-native": SourceDefinition(
        source_id="yonc-native",
        device="server",
        owner_agent="yonc",
        category_default="History",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Yonc native session state database",
    ),
    # Workstation sources (19 sources)
    "antigravity-backups": SourceDefinition(
        source_id="antigravity-backups",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Antigravity local conversation and brain backup archives",
    ),
    "antigravity-core": SourceDefinition(
        source_id="antigravity-core",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Antigravity IDE conversations, tool execution transcripts, and artifacts",
    ),
    "antigravity-logs": SourceDefinition(
        source_id="antigravity-logs",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Antigravity IDE diagnostic and runtime logs",
    ),
    "antigravity-user": SourceDefinition(
        source_id="antigravity-user",
        device="workstation",
        owner_agent="librarian",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Antigravity user configurations, custom skills, and user rules",
    ),
    "chatgpt-bridge-state": SourceDefinition(
        source_id="chatgpt-bridge-state",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="ChatGPT bridge sync state and session cursor",
    ),
    "codex-app-local": SourceDefinition(
        source_id="codex-app-local",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Codex desktop local app cache and storage",
    ),
    "codex-app-openai": SourceDefinition(
        source_id="codex-app-openai",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Codex desktop OpenAI authentication and runtime tokens",
    ),
    "codex-app-roaming": SourceDefinition(
        source_id="codex-app-roaming",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Codex desktop roaming application data cache",
    ),
    "codex-archived": SourceDefinition(
        source_id="codex-archived",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Archived historical Codex conversation sessions",
    ),
    "codex-attachments": SourceDefinition(
        source_id="codex-attachments",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Codex conversation file attachments and code snippets",
    ),
    "codex-sessions": SourceDefinition(
        source_id="codex-sessions",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="conversational",
        description="Active Codex conversation sessions and rollouts",
    ),
    "codex-state": SourceDefinition(
        source_id="codex-state",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="private",
        description="Codex desktop local state files",
    ),
    "phoenix": SourceDefinition(
        source_id="phoenix",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Phoenix project directory and workspace artifacts",
    ),
    "probe": SourceDefinition(
        source_id="probe",
        device="workstation",
        owner_agent="librarian",
        category_default="Experience",
        privacy_tier="internal",
        adapter_archetype="private",
        description="System probe and hardware environment diagnostic snapshot",
    ),
    "project-chatgpt-watchdog": SourceDefinition(
        source_id="project-chatgpt-watchdog",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="ChatGPT watchdog monitoring project source and configs",
    ),
    "project-watchdog-inventory-p00001": SourceDefinition(
        source_id="project-watchdog-inventory-p00001",
        device="workstation",
        owner_agent="librarian",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Watchdog inventory project partition 00001",
    ),
    "project-yonc-graph-p00001": SourceDefinition(
        source_id="project-yonc-graph-p00001",
        device="workstation",
        owner_agent="yonc",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Yonc graph project partition 00001 workspace files",
    ),
    "project-yonc-graph-p00002": SourceDefinition(
        source_id="project-yonc-graph-p00002",
        device="workstation",
        owner_agent="yonc",
        category_default="Work & Artifacts",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Yonc graph project partition 00002 workspace files",
    ),
    "scholar": SourceDefinition(
        source_id="scholar",
        device="workstation",
        owner_agent="wisdom",
        category_default="Knowledge",
        privacy_tier="internal",
        adapter_archetype="domain",
        description="Scholar research tracks, literature notes, and manuscripts",
    ),
}

TOTAL_SOURCES_COUNT = 63
assert len(REGISTERED_SOURCES) == TOTAL_SOURCES_COUNT, f"Expected 63 sources, got {len(REGISTERED_SOURCES)}"


def get_source(source_id: str) -> SourceDefinition:
    """Retrieve source definition by unique source_id, raising KeyError if absent."""
    if source_id not in REGISTERED_SOURCES:
        raise KeyError(f"Unknown data source: {source_id}")
    return REGISTERED_SOURCES[source_id]


def is_registered_source(source_id: str) -> bool:
    """Check whether a given source_id is part of the 63 registered sources."""
    return source_id in REGISTERED_SOURCES


def list_sources(
    *,
    device: DeviceType | None = None,
    owner_agent: str | None = None,
    privacy_tier: PrivacyTier | None = None,
    adapter_archetype: AdapterArchetype | None = None,
) -> list[SourceDefinition]:
    """Filter registered sources matching the provided criteria."""
    results: list[SourceDefinition] = []
    for source in REGISTERED_SOURCES.values():
        if device is not None and source.device != device:
            continue
        if owner_agent is not None and source.owner_agent != owner_agent:
            continue
        if privacy_tier is not None and source.privacy_tier != privacy_tier:
            continue
        if adapter_archetype is not None and source.adapter_archetype != adapter_archetype:
            continue
        results.append(source)
    return results


def count_sources() -> int:
    """Return total count of registered data sources."""
    return len(REGISTERED_SOURCES)
