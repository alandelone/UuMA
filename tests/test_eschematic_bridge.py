from __future__ import annotations

import json
from pathlib import Path

import pytest

from uuma.eschematic_bridge import ESchematicBridge


def _bridge(tmp_path):
    root = tmp_path / "eschematic"
    skill = root / "skills" / "eschematic"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: eschematic\ndescription: test\n---\n")
    for parent in [root / "skills", skill, scripts]:
        (parent / "__init__.py").write_text("")
    return ESchematicBridge(root, tmp_path / "python", tmp_path / "data", tmp_path / "output")


def test_status_reports_missing_runtime(tmp_path):
    bridge = _bridge(tmp_path)
    status = bridge.status()
    assert status["available"] is False
    assert status["skill_file"].endswith("SKILL.md")


def test_bom_resolution_uses_exact_and_generic_catalog_identity(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path)
    catalog = {
        "components": [
            {
                "id": "cmp-exact",
                "identity_type": "exact",
                "manufacturer": "TI",
                "mpn": "TPS5430",
                "category": "Regulator",
            },
            {
                "id": "cmp-generic",
                "identity_type": "generic",
                "internal_id": "GEN-RES-10K-0805",
                "category": "Resistor",
                "value": "10k",
                "package": "0805",
            },
        ]
    }
    monkeypatch.setattr(
        ESchematicBridge,
        "list_components",
        lambda _self, category="", limit=200: catalog,
    )
    result = bridge.resolve_normalized_bom(
        {
            "status": "valid",
            "items": [
                {
                    "identity_type": "exact",
                    "manufacturer": "ti",
                    "mpn": "tps5430",
                    "quantity": 1,
                },
                {
                    "identity_type": "generic",
                    "category": "resistor",
                    "value": "10K",
                    "package": "0805",
                    "quantity": 2,
                },
            ],
            "findings": [],
        }
    )
    assert result["status"] == "resolved"
    assert [item["component_id"] for item in result["resolved_items"]] == [
        "cmp-exact",
        "cmp-generic",
    ]


def test_commit_candidate_requires_approval(tmp_path):
    bridge = _bridge(tmp_path)
    with pytest.raises(PermissionError, match="explicit approval"):
        bridge.commit_candidate("cand-1", approved=False)


def test_list_components_uses_full_catalog_export(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path)
    bridge.data_dir.mkdir(parents=True)
    components = [
        {"id": "cmp-a", "category": "Sensor"},
        {"id": "cmp-b", "category": "Sensor"},
        {"id": "cmp-c", "category": "Timer"},
    ]

    def fake_run(_self, _module, arguments):
        output = arguments[arguments.index("--output-path") + 1]
        Path(output).write_text(
            json.dumps({"catalog_hash": "hash-1", "components": components}),
            encoding="utf-8",
        )
        return {"status": "ok", "path": output}

    monkeypatch.setattr(ESchematicBridge, "_run", fake_run)

    result = bridge.list_components(category="sensor", limit=1)

    assert result["catalog_hash"] == "hash-1"
    assert result["total_count"] == 2
    assert result["count"] == 1
    assert result["components"] == [{"id": "cmp-a", "category": "Sensor"}]


def test_design_manifest_is_hashed_and_idempotently_immutable(tmp_path):
    bridge = _bridge(tmp_path)
    result = bridge.export_design_manifest(
        "motor-controller",
        "REV-A",
        [{"component_id": "cmp-a", "quantity": 2, "designators": ["U2", "U1"]}],
    )
    repeated = bridge.export_design_manifest(
        "motor-controller",
        "REV-A",
        [{"component_id": "cmp-a", "quantity": 2, "designators": ["U1", "U2"]}],
    )
    assert result["manifest_hash"] == repeated["manifest_hash"]
    assert result["manifest_path"] == repeated["manifest_path"]
