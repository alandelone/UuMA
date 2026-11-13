"""Unit tests for Honc Privacy Firewall and Habit Adapter."""

from __future__ import annotations

from uuma.librarian_honc_adapter import HoncPrivacyAdapter


def test_honc_privacy_firewall_quarantines_diary_and_allows_habits():
    adapter = HoncPrivacyAdapter()

    sample_data = [
        {
            "id": "h101",
            "type": "habit",
            "title": "Morning Running 5km",
            "content": "Running at 6:30 AM every Tuesday and Thursday.",
            "timestamp": "2026-11-12T06:30:00Z",
        },
        {
            "id": "h102",
            "type": "diary",
            "title": "Private Reflection",
            "content": "Personal diary feeling anxious about medical doctor appointment.",
            "timestamp": "2026-11-12T21:00:00Z",
        },
    ]

    records = adapter.extract(sample_data)
    assert len(records) == 2

    # Habit entry
    habit_rec = records[0]
    assert habit_rec.privacy_tier == "restricted"
    assert "Morning Running" in habit_rec.title
    assert "Running at 6:30 AM" in habit_rec.full_content
    assert "orchestrator" in habit_rec.readers

    # Private diary entry
    diary_rec = records[1]
    assert diary_rec.privacy_tier == "honc_private"
    assert "quarantined" in diary_rec.full_content.lower()
    assert "medical" not in diary_rec.full_content
    assert diary_rec.readers == ["honc_owner"]
    assert "orchestrator" not in diary_rec.readers
