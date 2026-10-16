"""Generic fallback adapter for newly registered or unknown agents."""
from __future__ import annotations

from ..models import ObservatoryItem, SourceFreshness
from .base import ObservatorySourceAdapter


class GenericHermesAdapter(ObservatorySourceAdapter):
    def __init__(self, agent_id: str, display_name: str | None = None, role: str | None = None) -> None:
        self.agent_id = agent_id
        self.display_name = display_name or agent_id.capitalize()
        self.role = role or "通用智能体工作区"
        self.source_name = f"hermes:{agent_id}"

    def probe_health(self) -> SourceFreshness:
        return SourceFreshness(
            source_name=self.source_name,
            is_available=True,
            last_event_at=None,
        )

    def list_items(self, limit: int = 10, offset: int = 0) -> list[ObservatoryItem]:
        return [
            ObservatoryItem(
                agent_id=self.agent_id,
                item_id=f"{self.agent_id}_default",
                title=f"{self.display_name} 运行记录",
                kind="generic",
                status="IDLE",
                summary="通用 Hermes 工作区，自动收集运行时审计事件",
                source_ref=self.source_name,
                payload={},
            )
        ]

    def get_item(self, item_id: str) -> ObservatoryItem | None:
        items = self.list_items()
        for it in items:
            if it.item_id == item_id:
                return it
        return None
