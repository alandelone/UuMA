from __future__ import annotations

import pytest
from pydantic import ValidationError

from uuma import mcp_worker
from uuma.brainstormer_planning import CapacityScenario, calculate_capacity
from uuma.brainstormer_state import BrainstormerStore


def scenario(**changes) -> CapacityScenario:
    values = {
        "target_monthly_profit": 10_000,
        "realized_price_per_kg": 11,
        "variable_cost_per_sold_kg": 2,
        "fixed_cost_per_month": 5_000,
        "growth_days": 60,
        "turnaround_days": 5,
        "harvest_interval_days": 15,
        "row_spacing_cm": 20,
        "plant_spacing_cm": 12,
        "harvested_kg_per_planting_position": 0.1,
        "sellable_fraction": 0.8,
        "planted_area_fraction": 0.75,
        "deliveries_per_week": 2,
        "planned_blocks": 4,
    }
    return CapacityScenario.model_validate(values | changes)


def test_reverse_profit_to_batches_area_and_delivery_without_invented_defaults() -> None:
    result = calculate_capacity(scenario())
    assert result["required_sold_kg_per_month"] == pytest.approx(1666.667, abs=0.001)
    assert result["required_harvested_kg_per_month"] == pytest.approx(2083.333, abs=0.001)
    assert result["sold_kg_per_harvest_batch"] == pytest.approx(833.333, abs=0.001)
    assert result["minimum_blocks"] == 5  # 60 days growing plus 5 days turnaround
    assert result["planned_blocks_suffice"] is False
    assert result["net_planting_square_metres_per_block"] == pytest.approx(250)
    assert result["gross_land_square_metres"] == pytest.approx(1666.667, abs=0.001)
    assert result["sold_kg_per_delivery"] == pytest.approx(194.444, abs=0.001)
    assert result["profit_check_per_month"] == 10_000
    assert "not verified" in result["basis"]


def test_harvest_and_delivery_cadences_are_independent() -> None:
    baseline = calculate_capacity(scenario())
    more_deliveries = calculate_capacity(scenario(deliveries_per_week=4))
    assert more_deliveries["sold_kg_per_delivery"] == pytest.approx(
        baseline["sold_kg_per_delivery"] / 2, abs=0.001
    )
    assert more_deliveries["net_planting_square_metres_per_block"] == (
        baseline["net_planting_square_metres_per_block"]
    )


def test_missing_or_nonviable_inputs_fail_instead_of_filling_guess() -> None:
    values = scenario().model_dump()
    del values["realized_price_per_kg"]
    with pytest.raises(ValidationError, match="realized_price_per_kg"):
        CapacityScenario.model_validate(values)
    with pytest.raises(ValidationError, match="exceed variable cost"):
        scenario(realized_price_per_kg=2)
    with pytest.raises(ValidationError):
        scenario(row_spacing_cm=float("nan"))


def test_worker_tool_is_brainstormer_only(monkeypatch) -> None:
    payload = scenario().model_dump()
    monkeypatch.setenv("UUMA_AGENT_ID", "scholar")
    with pytest.raises(PermissionError, match="restricted to Brainstormer"):
        mcp_worker.brainstormer_calculate_capacity(**payload)
    monkeypatch.setenv("UUMA_AGENT_ID", "brainstormer")
    result = mcp_worker.brainstormer_calculate_capacity(**payload)
    assert result["minimum_blocks"] == 5


def test_initial_discussion_tool_proposes_structure_without_committing(tmp_path, monkeypatch):
    store = BrainstormerStore(tmp_path)
    monkeypatch.setenv("UUMA_AGENT_ID", "brainstormer")
    monkeypatch.setattr(mcp_worker, "_brainstormer_store", lambda: store)
    proposal = mcp_worker.brainstormer_propose_project_topic(
        project_title="Malaysia scallion farm",
        project_objective="Assess a monthly operating profit target",
        topic_title="Production area and harvest cadence",
        topic_problem="How much land is needed for a tested sales target?",
        source_ref="conversation:telegram-test",
    )
    assert proposal["status"] == "PROPOSED"
    assert proposal["review_required"] is True
    assert proposal["project_id"].startswith("project-")
    assert proposal["topic_id"].startswith("topic-")
    assert not (tmp_path / "projects" / proposal["project_id"] / "state.json").exists()
    assert store.get_proposal(proposal["proposal_id"])["transaction"]["source_refs"] == [
        "conversation:telegram-test"
    ]
    same = mcp_worker.brainstormer_propose_project_topic(
        project_title="Malaysia scallion farm",
        project_objective="Assess a monthly operating profit target",
        topic_title="Production area and harvest cadence",
        topic_problem="How much land is needed for a tested sales target?",
        source_ref="conversation:telegram-test",
    )
    assert same["proposal_id"] == proposal["proposal_id"]
    store.review(proposal["proposal_id"], actor_id="orchestrator", approve=True, note="accepted")
    existing = mcp_worker.brainstormer_propose_project_topic(
        project_title="Malaysia scallion farm",
        project_objective="Assess a monthly operating profit target",
        topic_title="Production area and harvest cadence",
        topic_problem="How much land is needed for a tested sales target?",
        source_ref="conversation:telegram-test",
    )
    assert existing["status"] == "ALREADY_EXISTS"
