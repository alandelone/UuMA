from __future__ import annotations

from .models import AgentDefinition, RiskLevel, RouteDecision, TaskContract
from .policy import ORCHESTRATOR_ONLY_TOOLS, PROHIBITED_CAPABILITIES, PolicyEngine


class CapabilityRouter:
    """Graph-first filter with an explicit Orchestrator ambiguity boundary."""

    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy

    def route(
        self,
        task: TaskContract,
        agents: list[AgentDefinition],
        workload: dict[str, int] | None = None,
    ) -> RouteDecision:
        workload = workload or {}
        if task.risk_level is RiskLevel.PROHIBITED or (
            task.required_capabilities & PROHIBITED_CAPABILITIES
        ):
            return RouteDecision(
                task_id=task.task_id,
                selected_agent=None,
                denied=True,
                rationale=["A permanently prohibited capability or risk was requested."],
            )

        needs_orchestrator = bool(task.required_tools & ORCHESTRATOR_ONLY_TOOLS)
        if needs_orchestrator:
            orchestrator = next(
                (agent for agent in agents if agent.agent_id == "orchestrator" and agent.enabled),
                None,
            )
            if orchestrator is not None and self.policy.authorize_task(orchestrator, task).allowed:
                return RouteDecision(
                    task_id=task.task_id,
                    selected_agent="orchestrator",
                    candidates=["orchestrator"],
                    requires_orchestrator=True,
                    rationale=["The request needs an Orchestrator-only capability."],
                )
            return RouteDecision(
                task_id=task.task_id,
                selected_agent=None,
                candidates=[],
                requires_orchestrator=True,
                rationale=[
                    (
                        "The contract combines Orchestrator-only tools with capabilities the "
                        "Orchestrator does not own; it must be split into coordinated tasks."
                    )
                ],
            )

        candidates: list[AgentDefinition] = []
        for agent in agents:
            if not agent.enabled or agent.agent_id == "orchestrator":
                continue
            decision = self.policy.authorize_task(agent, task)
            if decision.allowed:
                candidates.append(agent)

        candidates.sort(
            key=lambda agent: (
                workload.get(agent.agent_id, 0),
                len(agent.capabilities - task.required_capabilities),
                agent.agent_id,
            )
        )
        candidate_ids = [agent.agent_id for agent in candidates]
        if len(candidates) == 1:
            return RouteDecision(
                task_id=task.task_id,
                selected_agent=candidates[0].agent_id,
                candidates=candidate_ids,
                rationale=["One enabled Agent satisfies capability, tool, and risk constraints."],
            )
        if len(candidates) > 1:
            return RouteDecision(
                task_id=task.task_id,
                selected_agent=None,
                candidates=candidate_ids,
                requires_orchestrator=True,
                rationale=["Multiple Agents qualify; the Orchestrator must resolve semantic ambiguity."],
            )
        return RouteDecision(
            task_id=task.task_id,
            selected_agent=None,
            candidates=[],
            requires_orchestrator=True,
            rationale=["No Agent fully satisfies the declared contract; the Orchestrator must revise or split it."],
        )
