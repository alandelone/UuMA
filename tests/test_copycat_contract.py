from __future__ import annotations

import unittest

from pydantic import ValidationError

from uuma.copycat_contract import CopyCatAction, CopyCatActionHealth, UnavailableCopyCatClient
from uuma.models import RiskLevel


class CopyCatContractTests(unittest.TestCase):
    def test_contract_keeps_health_review_and_risk(self) -> None:
        action = CopyCatAction(
            action_id="daily-report",
            name="Download daily report",
            description="Downloads the reviewed daily report.",
            version="1.0.0",
            health=CopyCatActionHealth.VALID,
            risk_level=RiskLevel.REVERSIBLE,
            reviewed=True,
            replay_enabled=True,
            contract_hash="abc123",
        )
        self.assertTrue(action.reviewed)
        self.assertEqual(action.health, CopyCatActionHealth.VALID)

    def test_unknown_contract_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CopyCatAction(
                action_id="unsafe",
                name="Unsafe",
                description="Invalid contract.",
                version="1",
                health=CopyCatActionHealth.VALID,
                risk_level=RiskLevel.PROHIBITED,
                reviewed=False,
                replay_enabled=False,
                contract_hash="abc",
                hidden_override=True,
            )

    def test_unavailable_client_never_executes(self) -> None:
        client = UnavailableCopyCatClient()
        self.assertEqual(client.list_actions(), [])
        with self.assertRaises(RuntimeError):
            client.execute_action("daily-report", {}, idempotency_key="once")


if __name__ == "__main__":
    unittest.main()
