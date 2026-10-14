"""Operational manual examples must stay valid against the advertised input models."""
import json
import re
from pathlib import Path

from uuma.honc.life_models import BodyRecordRequest, HabitCheckinRequest, ReminderRule


def test_life_manual_examples_match_current_schemas_and_required_scope():
    root = Path(__file__).parents[1] / "profiles/honc/skills"
    examples = {"honc-checkin":HabitCheckinRequest, "honc-body-tracker":BodyRecordRequest,
                "honc-life-settings":ReminderRule}
    for skill, model in examples.items():
        text = (root / skill / "SKILL.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```json\s*(.*?)```", text, re.DOTALL)
        assert blocks, skill
        for block in blocks:
            payload = json.loads(block)
            model.model_validate(payload.get("request", payload))
