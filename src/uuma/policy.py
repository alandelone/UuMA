from __future__ import annotations

from dataclasses import dataclass

from .models import AgentDefinition, RiskLevel, TaskContract

ORCHESTRATOR_ONLY_TOOLS = {
    "computer_control",
    "copycat",
    "xhs",
    "control_mcp",
    "agent_coordination",
}

PROHIBITED_CAPABILITIES = {
    "purchase",
    "delete_files",
    "send_message",
    "credential_change",
    "security_setting_change",
    "dangerous_hardware_action",
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_user_approval: bool = False
    reason: str = ""


class PolicyEngine:
    def authorize_task(
        self,
        agent: AgentDefinition,
        task: TaskContract,
        *,
        user_approved: bool = False,
    ) -> PolicyDecision:
        forbidden = task.required_capabilities & PROHIBITED_CAPABILITIES
        if task.risk_level is RiskLevel.PROHIBITED or forbidden:
            return PolicyDecision(False, reason="The task contains a permanently prohibited action.")

        orchestrator_tools = task.required_tools & ORCHESTRATOR_ONLY_TOOLS
        if orchestrator_tools and agent.agent_id != "orchestrator":
            return PolicyDecision(
                False,
                reason=f"Tools {sorted(orchestrator_tools)} are reserved for the Orchestrator.",
            )

        if task.required_capabilities - agent.capabilities:
            missing = sorted(task.required_capabilities - agent.capabilities)
            return PolicyDecision(False, reason=f"Agent lacks capabilities: {missing}.")

        if task.required_tools - agent.tools:
            missing = sorted(task.required_tools - agent.tools)
            return PolicyDecision(False, reason=f"Agent lacks tools: {missing}.")

        if task.risk_level.rank > agent.maximum_risk.rank:
            return PolicyDecision(
                False,
                reason=f"Task risk exceeds {agent.agent_id}'s maximum risk.",
            )

        if task.risk_level is RiskLevel.COMMITTING and not user_approved:
            return PolicyDecision(
                False,
                requires_user_approval=True,
                reason="Committing actions require explicit user approval.",
            )

        return PolicyDecision(True)

    def authorize_direct_run(self, agent: AgentDefinition, task: TaskContract) -> PolicyDecision:
        if task.source != "direct":
            return PolicyDecision(False, reason="Direct-run registration requires source=direct.")
        if task.risk_level not in {RiskLevel.READ_ONLY, RiskLevel.REVERSIBLE}:
            return PolicyDecision(False, reason="Direct runs are limited to safe domain work.")
        if task.user_visible_structure_change:
            return PolicyDecision(
                False,
                requires_user_approval=True,
                reason="User-visible structure changes must be proposed to the Orchestrator.",
            )
        return self.authorize_task(agent, task)


def default_agents() -> list[AgentDefinition]:
    return [
        AgentDefinition(
            agent_id="orchestrator",
            display_name="Orchestrator",
            description="Routes work, owns shared control state, monitors runs, and controls the computer.",
            capabilities={
                "orchestration",
                "routing",
                "agent_coordination",
                "computer_control",
                "copycat",
                "general_assistance",
            },
            tools={
                "control_mcp",
                "worker_mcp",
                "hermes_kanban",
                "hermes_runs",
                "computer_control",
                "copycat",
                "xhs",
            },
            maximum_risk=RiskLevel.COMMITTING,
            can_control_computer=True,
            can_use_copycat=True,
            can_coordinate_agents=True,
        ),
        AgentDefinition(
            agent_id="brainstormer",
            display_name="Brainstormer",
            description="Explores, challenges, converges, and produces build-ready reasoning artifacts.",
            capabilities={
                "brainstorming",
                "problem_framing",
                "decision_analysis",
                "product_design",
                "system_architecture",
                "artifact_design",
            },
            tools={"worker_mcp", "workspace_read", "workspace_write", "web_research"},
        ),
        AgentDefinition(
            agent_id="scholar",
            display_name="Scholar",
            description="Supports user-owned scientific research questions, methods, evidence, experiments, and claims.",
            capabilities={
                "research",
                "scientific_method",
                "evidence_synthesis",
                "experiment_design",
                "claim_evaluation",
            },
            tools={"worker_mcp", "rstv4_worker", "workspace_read", "workspace_write", "web_research"},
        ),
        AgentDefinition(
            agent_id="wisdom-oldman",
            display_name="Wisdom-Oldman",
            description="Forms durable, evidence-linked knowledge and identifies worthwhile knowledge gaps.",
            capabilities={
                "knowledge_research",
                "knowledge_formation",
                "knowledge_gap",
                "evidence_map",
                "best_current_answer",
            },
            tools={"worker_mcp", "workspace_read", "workspace_write", "web_research"},
        ),
        AgentDefinition(
            agent_id="forge-lab-bot",
            display_name="锻造Lab_Bot",
            description="Handles hardware-lab analysis, inventory, BOM, build traceability, and procurement advice.",
            capabilities={
                "hardware",
                "inventory",
                "bom_analysis",
                "build_traceability",
                "procurement_advice",
                "lab_worklog",
            },
            tools={"worker_mcp", "workspace_read", "workspace_write", "web_research"},
        ),
    ]
