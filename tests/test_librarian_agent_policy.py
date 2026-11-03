from uuma.models import RiskLevel, TaskContract
from uuma.policy import PolicyEngine, default_agents


def test_librarian_is_read_only_and_cannot_gain_write_authority():
    agent = next(item for item in default_agents() if item.agent_id == "librarian")
    assert agent.maximum_risk == RiskLevel.READ_ONLY
    assert agent.tools == {"worker_mcp", "librarian_read"}
    assert not agent.enabled
    task = TaskContract(title="Read project history", objective="Find retained versions",
                        required_capabilities={"archive_retrieval"}, required_tools={"librarian_read"},
                        risk_level=RiskLevel.READ_ONLY)
    assert not PolicyEngine().authorize_task(agent, task).allowed
    agent.enabled = True
    assert PolicyEngine().authorize_task(agent, task).allowed
    task.risk_level = RiskLevel.REVERSIBLE
    assert not PolicyEngine().authorize_task(agent, task).allowed
