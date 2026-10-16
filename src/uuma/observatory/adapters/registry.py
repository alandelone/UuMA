"""Registry for discovering and managing agent source adapters."""
from __future__ import annotations

from pathlib import Path

from ...colleague_directory import ROLE_GUIDANCE
from ..models import AgentWorkspace, SourceFreshness
from .base import ObservatorySourceAdapter
from .brainstormer import BrainstormerAdapter
from .forge import ForgeAdapter
from .generic import GenericHermesAdapter
from .honc import HoncAdapter
from .orchestrator import OrchestratorAdapter
from .scholar import ScholarAdapter
from .wisdom import WisdomAdapter
from .yonc import YoncAdapter


class AdapterRegistry:
    """Manages adapter instances for all UuMA registered agents."""

    def __init__(
        self,
        data_dir: Path | str,
        uuma_db_path: Path | str | None = None,
        knowledge_db_path: Path | str | None = None,
        hermes_dir: Path | str | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.uuma_db = Path(uuma_db_path) if uuma_db_path else (self.data_dir / "uuma.db")
        self.knowledge_db = Path(knowledge_db_path) if knowledge_db_path else None
        self.hermes_dir = Path(hermes_dir) if hermes_dir else Path("C:/Users/Alandelone/AppData/Local/hermes")

        self._adapters: dict[str, ObservatorySourceAdapter] = {}
        self._init_defaults()

    def _init_defaults(self) -> None:
        self._adapters["forge-lab-bot"] = ForgeAdapter(self.data_dir)
        self._adapters["wisdom-oldman"] = WisdomAdapter(self.data_dir, self.knowledge_db, self.uuma_db)
        self._adapters["scholar"] = ScholarAdapter(self.uuma_db)
        self._adapters["brainstormer"] = BrainstormerAdapter(self.data_dir, self.hermes_dir)
        self._adapters["yonc"] = YoncAdapter(self.hermes_dir, self.uuma_db)
        self._adapters["honc"] = HoncAdapter(self.data_dir)
        self._adapters["orchestrator"] = OrchestratorAdapter(self.uuma_db)

    def get_adapter(self, agent_id: str) -> ObservatorySourceAdapter:
        norm = agent_id.strip().lower()
        if norm in self._adapters:
            return self._adapters[norm]

        # Check aliases
        aliases = {
            "forge": "forge-lab-bot",
            "lab_bot": "forge-lab-bot",
            "labbot": "forge-lab-bot",
            "wisdom": "wisdom-oldman",
            "default": "orchestrator",
        }
        if norm in aliases and aliases[norm] in self._adapters:
            return self._adapters[aliases[norm]]

        # Fallback to Generic
        guidance = ROLE_GUIDANCE.get(norm, {})
        role = guidance.get("role") or "通用智能体工作区"
        return GenericHermesAdapter(norm, role=role)

    def list_all_adapters(self) -> list[ObservatorySourceAdapter]:
        # Return canonical ordered 7 agents
        order = [
            "forge-lab-bot",
            "wisdom-oldman",
            "scholar",
            "brainstormer",
            "yonc",
            "honc",
            "orchestrator",
        ]
        res: list[ObservatorySourceAdapter] = []
        for k in order:
            if k in self._adapters:
                res.append(self._adapters[k])
        # Add any other registered
        for k, v in self._adapters.items():
            if k not in order:
                res.append(v)
        return res

    def get_fleet_workspaces(self) -> list[AgentWorkspace]:
        workspaces: list[AgentWorkspace] = []
        for adapter in self.list_all_adapters():
            items = adapter.list_items(limit=15)
            health = adapter.probe_health()
            status = "IDLE"
            if items:
                status = items[0].status

            workspaces.append(
                AgentWorkspace(
                    agent_id=adapter.agent_id,
                    name=adapter.display_name,
                    role=adapter.role,
                    source_name=adapter.source_name,
                    status=status,
                    health="HEALTHY" if health.is_available else "WARNING",
                    items=items,
                    total_items=len(items),
                )
            )
        return workspaces

    def probe_all_sources(self) -> dict[str, SourceFreshness]:
        res: dict[str, SourceFreshness] = {}
        for adapter in self.list_all_adapters():
            freshness = adapter.probe_health()
            res[adapter.agent_id] = freshness
        return res
