"""Deterministic arithmetic for a provisional production and unit-economics plan.

Inputs are assumptions, not market or agronomic evidence. The caller must establish their
provenance before presenting a result as a real-world forecast.
"""

from __future__ import annotations

from math import ceil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_DAYS_PER_MONTH = 30.0
_SQUARE_FEET_PER_SQUARE_METRE = 10.7639104167
_SQUARE_FEET_PER_ACRE = 43_560.0


class CapacityScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    target_monthly_profit: float = Field(ge=0)
    realized_price_per_kg: float = Field(gt=0)
    variable_cost_per_sold_kg: float = Field(ge=0)
    fixed_cost_per_month: float = Field(ge=0)
    growth_days: float = Field(gt=0)
    turnaround_days: float = Field(ge=0)
    harvest_interval_days: float = Field(gt=0)
    row_spacing_cm: float = Field(gt=0)
    plant_spacing_cm: float = Field(gt=0)
    harvested_kg_per_planting_position: float = Field(gt=0)
    sellable_fraction: float = Field(gt=0, le=1)
    planted_area_fraction: float = Field(gt=0, le=1)
    deliveries_per_week: float = Field(gt=0)
    planned_blocks: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_positive_contribution(self) -> CapacityScenario:
        if self.realized_price_per_kg <= self.variable_cost_per_sold_kg:
            raise ValueError("Realized price must exceed variable cost per sold kg.")
        return self


def calculate_capacity(scenario: CapacityScenario) -> dict[str, Any]:
    """Reverse profit into sales, harvest, space, and delivery cadence without market defaults."""
    contribution = scenario.realized_price_per_kg - scenario.variable_cost_per_sold_kg
    sold_kg_month = (scenario.target_monthly_profit + scenario.fixed_cost_per_month) / contribution
    harvested_kg_month = sold_kg_month / scenario.sellable_fraction
    batches_month = _DAYS_PER_MONTH / scenario.harvest_interval_days
    sold_kg_batch = sold_kg_month / batches_month
    harvested_kg_batch = harvested_kg_month / batches_month
    square_metres_per_position = (
        scenario.row_spacing_cm * scenario.plant_spacing_cm / 10_000
    )
    harvested_kg_square_metre = (
        scenario.harvested_kg_per_planting_position / square_metres_per_position
    )
    net_square_metres_block = harvested_kg_batch / harvested_kg_square_metre
    minimum_blocks = ceil(
        (scenario.growth_days + scenario.turnaround_days) / scenario.harvest_interval_days
    )
    net_square_metres_total = net_square_metres_block * minimum_blocks
    gross_square_metres = net_square_metres_total / scenario.planted_area_fraction
    delivery_kg = sold_kg_month / (_DAYS_PER_MONTH / 7 * scenario.deliveries_per_week)
    return {
        "scenario": scenario.model_dump(),
        "basis": (
            "Scenario arithmetic only; inputs are not verified prices, costs, or yields. "
            "Profit excludes tax, finance, and capital recovery unless included in input costs."
        ),
        "planning_month_days": _DAYS_PER_MONTH,
        "contribution_per_sold_kg": round(contribution, 4),
        "profit_check_per_month": round(
            sold_kg_month * contribution - scenario.fixed_cost_per_month, 3
        ),
        "required_sold_kg_per_month": round(sold_kg_month, 3),
        "required_harvested_kg_per_month": round(harvested_kg_month, 3),
        "sold_kg_per_harvest_batch": round(sold_kg_batch, 3),
        "harvested_kg_per_harvest_batch": round(harvested_kg_batch, 3),
        "minimum_blocks": minimum_blocks,
        "planned_blocks_suffice": (
            scenario.planned_blocks >= minimum_blocks
            if scenario.planned_blocks is not None else None
        ),
        "net_planting_square_metres_per_block": round(net_square_metres_block, 3),
        "net_planting_square_feet_per_block": round(
            net_square_metres_block * _SQUARE_FEET_PER_SQUARE_METRE, 3
        ),
        "net_planting_square_metres_total": round(net_square_metres_total, 3),
        "gross_land_square_metres": round(gross_square_metres, 3),
        "gross_land_square_feet": round(
            gross_square_metres * _SQUARE_FEET_PER_SQUARE_METRE, 3
        ),
        "gross_land_acres": round(
            gross_square_metres * _SQUARE_FEET_PER_SQUARE_METRE / _SQUARE_FEET_PER_ACRE,
            5,
        ),
        "sold_kg_per_delivery": round(delivery_kg, 3),
    }
